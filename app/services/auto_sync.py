"""自动同步服务。

定时从 we-mp-rss 拉取新文章，自动抽取活动信息，同步到飞书。
"""

import contextlib
import logging
import threading
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import requests as http_requests
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.db import SessionLocal
from app.models import Article, Event, SyncRun
from app.services.article_service import ArticleService
from app.services.event_extractor import EventExtractor
from app.services.event_policy import EventPolicyService, event_time_status
from app.services.feishu import FeishuAdapter
from app.services.sync_run_service import SyncRunService
from app.utils.constants import EventStatus
from app.utils.cron import parse_cron

logger = logging.getLogger(__name__)

# SyncRun 卡死阈值：超过此时间仍为 running 则自动标记为 failed
STUCK_RUN_THRESHOLD = timedelta(minutes=30)


class AutoSyncService:
    """自动同步服务。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.scheduler = BackgroundScheduler()
        self._execution_lock = threading.Lock()
        self._status_lock = threading.Lock()
        self._sync_status = {
            "running": False,
            "status": "idle",
            "phase": "idle",       # idle | fetching | extracting | syncing | done | error
            "message": "",
            "result": None,
            "started_at": None,
        }
        self._last_retry_metrics: dict[str, int] = {}

    def start(self) -> None:
        """启动定时任务调度器。"""
        self.settings = get_settings()
        if self.scheduler.running:
            self.scheduler.remove_all_jobs()
        # 启动前恢复卡死的 SyncRun
        self._recover_stuck_runs()

        # 启动时延迟运行一次自动归档（不依赖同步流程）
        auto_archive_days = self.settings.auto_archive_expired_days
        if auto_archive_days > 0:
            from datetime import datetime, timedelta
            self.scheduler.add_job(
                self._run_archive_only,
                "date",
                run_date=datetime.now() + timedelta(seconds=30),
                id="startup_archive",
                name="启动时自动归档",
                replace_existing=True,
                misfire_grace_time=120,
            )
            logger.info("Scheduled startup auto-archive (delayed 30s)")

        sync_cron = self.settings.auto_sync_cron
        if sync_cron:
            try:
                trigger = parse_cron(sync_cron)
                self.scheduler.add_job(
                    self._run_sync,
                    trigger,
                    id="auto_sync",
                    name="自动同步",
                    replace_existing=True,
                )
                logger.info("Scheduled auto sync with cron: %s", sync_cron)
            except Exception as e:
                logger.warning("Invalid auto_sync_cron '%s': %s", sync_cron, e)
        else:
            logger.info("Auto sync disabled (AUTO_SYNC_CRON not set)")

        if self.settings.priority_collection_cron:
            try:
                self.scheduler.add_job(
                    self._run_priority_collection,
                    parse_cron(self.settings.priority_collection_cron),
                    id="priority_collection",
                    name="重点公众号主动采集",
                    replace_existing=True,
                    coalesce=True,
                    max_instances=1,
                )
            except ValueError as exc:
                logger.warning("Invalid priority collection cron: %s", exc)

        if self.settings.feishu_reconcile_enabled and self.settings.feishu_reconcile_cron:
            try:
                self.scheduler.add_job(
                    self._run_feishu_reconcile,
                    parse_cron(self.settings.feishu_reconcile_cron),
                    id="feishu_reconcile",
                    name="飞书每日对账",
                    replace_existing=True,
                    coalesce=True,
                    max_instances=1,
                )
            except ValueError as exc:
                logger.warning("Invalid Feishu reconcile cron: %s", exc)

        if not self.scheduler.running:
            self.scheduler.start()
        logger.info("Auto sync scheduler started")

    def shutdown(self) -> None:
        """关闭定时任务调度器。"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Auto sync scheduler stopped")

    def reload_settings(self) -> None:
        """重新加载配置并重建任务。"""
        self.settings = get_settings()
        self.start()

    def _check_rss_reachable(self) -> bool:
        """检查 we-mp-rss 是否可达。使用 /api/docs 端点（与 tray 管理器一致）。"""
        try:
            resp = http_requests.get(
                f"{self.settings.we_mp_rss_base_url}/api/docs", timeout=5
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _trigger_we_mp_rss_collection(self, db: "Session") -> list[dict]:
        """主动触发 we-mp-rss 的文章采集任务。

        当检测到长时间没有新文章时，调用此方法触发 we-mp-rss 采集。
        采集完成后返回新的文章候选。

        Returns:
            触发采集后拉取到的新候选列表；失败时返回空列表。
        """
        from app.adapters.we_mp_rss import WeMpRssClient

        try:
            client = WeMpRssClient()
            article_service = ArticleService(db)

            # 1. 获取所有启用的消息任务
            tasks = client.list_message_tasks()
            if not tasks:
                logger.warning("No active message tasks found in we-mp-rss")
                return []

            logger.info("Found %d active message tasks, triggering collection...", len(tasks))

            # 2. 触发每个任务执行
            total_triggered = 0
            for task in tasks:
                task_id = task.get("id")
                task_name = task.get("name", "unknown")
                try:
                    result = client.trigger_message_task(task_id)
                    mp_count = result.get("count", 0)
                    logger.info(
                        "Triggered task '%s' (id=%s): %d public accounts queued",
                        task_name, task_id, mp_count,
                    )
                    total_triggered += mp_count
                except Exception as e:
                    logger.warning("Failed to trigger task '%s' (id=%s): %s", task_name, task_id, e)

            if total_triggered <= 0:
                logger.warning("No public accounts were queued for collection")
                return []

            # 3. 等待采集完成（最多等待 10 分钟）
            # 采集结果先进入 we-mp-rss，自身不会自动写入本地库，因此需要轮询远端候选。
            logger.info("Waiting for we-mp-rss collection to complete (max 10 minutes)...")
            wait_start = datetime.now()
            max_wait = timedelta(minutes=10)
            check_interval = timedelta(seconds=30)

            while datetime.now() - wait_start < max_wait:
                _time.sleep(check_interval.total_seconds())
                new_candidates = article_service.fetch_candidates(
                    limit=50, include_no_content=True
                )
                if new_candidates:
                    logger.info(
                        "Collection progress: %d new candidates detected after %s",
                        len(new_candidates), datetime.now() - wait_start,
                    )
                    return new_candidates

            logger.warning("Collection trigger timed out without new candidates")
            return []

        except Exception as e:
            logger.error("Failed to trigger we-mp-rss collection: %s", e)
            return []

    def _detect_dry_spell(self, db: "Session") -> bool:
        """检测是否处于"空窗期"（长时间没有新文章入库）。

        如果最近 24 小时内没有新文章，返回 True。
        """
        cutoff = datetime.now() - timedelta(hours=24)
        recent_count = (
            db.query(Article)
            .filter(Article.created_at >= cutoff)
            .count()
        )

        if recent_count == 0:
            logger.warning("Dry spell detected: no new articles in the last 24 hours")
            return True

        return False

    def _recover_stuck_runs(self) -> None:
        """恢复卡在 running 状态超过阈值的 SyncRun。"""
        try:
            with contextlib.closing(SessionLocal()) as db:
                cutoff = datetime.now(timezone.utc) - STUCK_RUN_THRESHOLD
                stuck = (
                    db.query(SyncRun)
                    .filter(SyncRun.status == "running", SyncRun.started_at < cutoff)
                    .all()
                )
                for run in stuck:
                    run.status = "failed"
                    run.error_message = f"Auto-recovered: stuck in running since {run.started_at}"
                    run.completed_at = datetime.now(timezone.utc)
                    logger.warning(
                        "Recovered stuck SyncRun %s (started at %s)",
                        run.run_id, run.started_at,
                    )
                if stuck:
                    db.commit()
                    logger.info("Recovered %d stuck sync runs", len(stuck))
        except Exception as exc:
            logger.error("Failed to recover stuck runs: %s", exc)

    def _execute_sync(self, trigger: str = "scheduled") -> dict:
        """执行一次完整同步（拉取文章 + 同步到飞书）。

        Returns:
            包含 articles_fetched, events_synced, events_failed 的字典。
        """
        sync_start_time = datetime.now()
        self._last_retry_metrics = {}
        logger.info("=" * 60)
        logger.info("同步开始 | 时间: %s", sync_start_time.strftime("%Y-%m-%d %H:%M:%S"))

        with contextlib.closing(SessionLocal()) as db:
            run_service = SyncRunService(db)
            run = run_service.start_run("auto-sync", {"trigger": trigger})

            # 前置检查：we-mp-rss 是否可达（在创建 SyncRun 之后，确保失败也有记录）
            if not self._check_rss_reachable():
                error_msg = f"we-mp-rss 服务不可达 ({self.settings.we_mp_rss_base_url})"
                run_service.finish_failure(run, error_msg)
                logger.error("同步失败 | 原因: %s", error_msg)
                raise ConnectionError(error_msg)

            try:
                # 1. 从 we-mp-rss 拉取新文章候选（快速，仅 HTTP + DB 去重）
                self._sync_status["phase"] = "fetching"
                self._sync_status["message"] = "正在从 we-mp-rss 拉取文章…"
                logger.info("步骤1/6 | 从 we-mp-rss 拉取文章候选...")

                article_service = ArticleService(db)
                fetch_start = datetime.now()
                candidates = article_service.fetch_candidates(
                    limit=50, include_no_content=True
                )
                fetch_duration = (datetime.now() - fetch_start).total_seconds()
                logger.info(
                    "步骤1/6 完成 | 拉取 %d 篇文章候选 | 耗时: %.1f秒",
                    len(candidates), fetch_duration
                )

                # 1.5 空窗期检测：如果长时间没有新文章，主动触发 we-mp-rss 采集
                dry_spell_triggered = False
                if not candidates and self._detect_dry_spell(db):
                    logger.warning("空窗期检测 | 最近24小时无新文章，触发 we-mp-rss 采集...")
                    self._sync_status["message"] = "检测到空窗期，正在触发 we-mp-rss 采集…"
                    collect_start = datetime.now()
                    candidates = self._trigger_we_mp_rss_collection(db)
                    collect_duration = (datetime.now() - collect_start).total_seconds()

                    if candidates:
                        logger.info(
                            "空窗期采集完成 | 获取 %d 篇文章候选 | 耗时: %.1f秒",
                            len(candidates), collect_duration
                        )
                        dry_spell_triggered = True
                    else:
                        logger.warning("空窗期采集 | 未获取新文章 | 耗时: %.1f秒", collect_duration)

                # 2. 并行入库（图片下载 + Vision 抽取，耗时操作）
                self._sync_status["phase"] = "extracting"
                self._sync_status["message"] = f"已拉取 {len(candidates)} 篇文章，正在并行处理…"
                logger.info("步骤2/6 | 并行入库处理 %d 篇文章...", len(candidates))

                def _on_ingest_progress(completed: int, total: int):
                    self._sync_status["message"] = f"正在处理文章… ({completed}/{total})"

                ingest_start = datetime.now()
                articles = article_service.ingest_candidates_parallel(
                    candidates, on_progress=_on_ingest_progress
                )
                articles_created = sum(1 for item in articles if item.get("article_created"))
                articles_skipped = sum(1 for item in articles if item.get("article_skipped"))
                articles_failed = sum(1 for item in articles if item.get("ingest_failed"))
                ingest_duration = (datetime.now() - ingest_start).total_seconds()
                logger.info(
                    "步骤2/6 完成 | 尝试 %d 篇，入库 %d 篇，过滤 %d 篇，失败 %d 篇 | 耗时: %.1f秒",
                    len(candidates), articles_created, articles_skipped, articles_failed, ingest_duration
                )

                # 3. 重试失败的图片下载 + 重新抽取
                self._sync_status["phase"] = "extracting"
                self._sync_status["message"] = f"已处理 {len(articles)} 篇文章，正在重试图片下载…"
                logger.info("步骤3/6 | 重试图片下载...")
                retried = self._retry_image_downloads(db)
                logger.info("步骤3/6 完成 | 重试 %d 个事件", retried)

                # 3.3 重试 failed_extract 事件
                self._sync_status["message"] = "正在重试抽取失败的事件…"
                extract_retried = self._retry_failed_extracts(db)
                logger.info("步骤3.3 | 重试抽取 %d 个失败事件", extract_retried)

                # 3.5 回溯补提取缺少时间信息的事件
                self._sync_status["message"] = "正在补提取事件时间…"
                backfilled = self._backfill_missing_times(db)
                logger.info("步骤3.5 | 补提取 %d 个事件时间", backfilled)

                self._sync_status["message"] = "正在重试飞书同步失败的事件…"
                failed_sync_retried = self._retry_failed_syncs(db)

                # 4. 刷新已同步事件的时间状态（过期 → past 等）
                self._sync_status["message"] = "正在刷新事件时间状态…"
                refreshed = self._refresh_event_statuses(db)
                logger.info("步骤4/6 | 刷新 %d 个事件状态", refreshed)

                # 5. 并行同步新事件到飞书
                self._sync_status["phase"] = "syncing"
                self._sync_status["message"] = "正在同步到飞书…"
                events = (
                    db.query(Event)
                    .filter(
                        Event.status.in_([EventStatus.EXTRACTED, EventStatus.PENDING_AI]),
                        Event.feishu_record_id == "",
                    )
                    .all()
                )
                event_ids = [e.event_id for e in events]
                logger.info("步骤5/6 | 同步 %d 个事件到飞书...", len(event_ids))

                sync_start = datetime.now()
                synced = self._sync_event_ids_parallel(
                    event_ids, label="同步飞书", max_workers=3,
                )
                sync_duration = (datetime.now() - sync_start).total_seconds()
                failed = len(event_ids) - synced
                logger.info(
                    "步骤5/6 完成 | 成功: %d | 失败: %d | 耗时: %.1f秒",
                    synced, failed, sync_duration
                )

                result = {
                    **article_service.last_fetch_metrics,
                    "articles_processed": len(candidates),
                    "articles_created": articles_created,
                    "articles_skipped": articles_skipped,
                    "articles_failed": articles_failed,
                    "articles_fetched": articles_created,
                    "images_retried": retried,
                    "extracts_retried": extract_retried,
                    "times_backfilled": backfilled,
                    "statuses_refreshed": refreshed,
                    "events_synced": synced,
                    "events_failed": failed,
                    "failed_sync_retried": failed_sync_retried,
                    **self._last_retry_metrics,
                }

                # 6. 自动归档过期事件
                auto_archive_days = self.settings.auto_archive_expired_days
                if auto_archive_days > 0:
                    self._sync_status["message"] = "正在自动归档过期事件…"
                    from app.services.archive_service import ArchiveService
                    archive_service = ArchiveService(db)
                    archive_result = archive_service.auto_archive_expired(auto_archive_days)
                    result["auto_archived"] = archive_result.get("archived", 0)
                    logger.info("步骤6/6 | 自动归档 %d 个过期事件", result["auto_archived"])

                degraded_reasons = []
                if articles_failed:
                    degraded_reasons.append(f"文章处理失败 {articles_failed} 篇")
                if failed:
                    degraded_reasons.append(f"飞书写入失败 {failed} 条")
                if self._last_retry_metrics.get("image_retry_failed", 0):
                    degraded_reasons.append(
                        f"图片重试仍失败 {self._last_retry_metrics['image_retry_failed']} 条"
                    )
                if self._last_retry_metrics.get("extract_retry_failed", 0):
                    degraded_reasons.append(
                        f"抽取重试仍失败 {self._last_retry_metrics['extract_retry_failed']} 条"
                    )
                if self._last_retry_metrics.get("failed_sync_retry_failed", 0):
                    degraded_reasons.append(
                        f"飞书重试仍失败 {self._last_retry_metrics['failed_sync_retry_failed']} 条"
                    )
                result["run_status"] = "degraded" if degraded_reasons else "completed"

                if not degraded_reasons:
                    run_service.finish_success(run, imported_count=articles_created, results=[result])
                else:
                    run_service.finish_degraded(
                        run,
                        imported_count=articles_created,
                        results=[result],
                        error_message="；".join(degraded_reasons),
                    )
                # 7. 新活动通知
                self.notify_new_events(result)

                from app.services.automation_guard import AutomationGuardService
                result["alert"] = AutomationGuardService(db).send_alerts(sync_result=result)

                # 输出同步总结
                total_duration = (datetime.now() - sync_start_time).total_seconds()
                logger.info("-" * 60)
                logger.info("同步完成 | 总耗时: %.1f秒", total_duration)
                logger.info(
                    "同步结果 | 文章尝试: %d | 入库: %d | 飞书同步: %d | 失败: %d",
                    len(candidates), articles_created, synced, articles_failed + failed
                )
                if dry_spell_triggered:
                    logger.info("补救措施 | 空窗期触发采集成功")
                if retried > 0 or extract_retried > 0 or backfilled > 0:
                    logger.info(
                        "重试统计 | 图片重试: %d | 抽取重试: %d | 时间补提: %d",
                        retried, extract_retried, backfilled
                    )
                logger.info("=" * 60)

                return result
            except Exception as exc:
                total_duration = (datetime.now() - sync_start_time).total_seconds()
                run_service.finish_failure(run, str(exc))
                logger.error("同步异常 | 耗时: %.1f秒 | 错误: %s", total_duration, exc)
                raise

    def _run_sync(self, trigger: str = "scheduled") -> None:
        """定时任务回调：执行同步并记录日志。"""
        if not self._begin_run(trigger):
            logger.info("Sync skipped because another maintenance run is active (trigger=%s)", trigger)
            return
        try:
            result = self._execute_sync(trigger)
        except Exception as e:
            logger.error("定时同步失败: %s", e)
            self._finish_run("error", f"同步失败: {e}")
            try:
                from app.services.automation_guard import AutomationGuardService
                with contextlib.closing(SessionLocal()) as db:
                    AutomationGuardService(db).send_alerts(sync_result={"run_error": str(e)})
            except Exception as alert_exc:
                logger.error("Failed to send sync failure alert: %s", alert_exc)
        else:
            degraded = result.get("run_status") == "degraded"
            self._finish_run(
                "degraded" if degraded else "done",
                "同步完成（存在部分失败）" if degraded else "同步完成",
                result,
            )
        finally:
            self._execution_lock.release()

    def _run_archive_only(self) -> None:
        """独立运行自动归档（不依赖同步流程）。

        启动时运行一次，将过期且未保护的事件自动归档。
        """
        auto_archive_days = self.settings.auto_archive_expired_days
        if auto_archive_days <= 0:
            return

        if not self._execution_lock.acquire(blocking=False):
            logger.info("Standalone auto-archive skipped because a sync is active")
            return

        logger.info("Running standalone auto-archive (cutoff=%d days)...", auto_archive_days)
        with self._status_lock:
            self._sync_status.update({
                "running": True,
                "status": "running",
                "phase": "extracting",
                "message": "正在自动归档过期活动…",
                "result": None,
                "trigger": "startup_archive",
                "started_at": datetime.now(timezone.utc).isoformat(),
            })
        try:
            with contextlib.closing(SessionLocal()) as db:
                # 先刷新事件时间状态（确保 event_time_status 是最新的）
                self._refresh_event_statuses(db)

                from app.services.archive_service import ArchiveService
                archive_service = ArchiveService(db)
                result = archive_service.auto_archive_expired(auto_archive_days)
                from app.services.automation_guard import AutomationGuardService
                AutomationGuardService(db).record_maintenance_result("startup_archive", "completed", result)
                if result.get("archived", 0) > 0:
                    logger.info("Standalone auto-archive result: %s", result)
                else:
                    logger.info("Standalone auto-archive: no events to archive")
            self._finish_run("done", "启动归档完成", result)
        except Exception as e:
            logger.error("Standalone auto-archive failed: %s", e)
            try:
                from app.services.automation_guard import AutomationGuardService
                with contextlib.closing(SessionLocal()) as db:
                    AutomationGuardService(db).record_maintenance_result("startup_archive", "failed", error=str(e))
            except Exception as record_exc:
                logger.error("Failed to record standalone archive failure: %s", record_exc)
            self._finish_run("error", f"启动归档失败: {e}")
        finally:
            self._execution_lock.release()

    def _run_priority_collection(self) -> None:
        if not self._execution_lock.acquire(blocking=False):
            logger.info("Priority collection skipped because maintenance is active")
            return
        try:
            from app.services.automation_guard import AutomationGuardService
            with contextlib.closing(SessionLocal()) as db:
                self._set_maintenance_status("priority_collection", "正在触发重点公众号采集…")
                result = AutomationGuardService(db).trigger_priority_collection()
                logger.info("Priority collection result: %s", result)
                guard = AutomationGuardService(db)
                guard.record_maintenance_result(
                    "priority_collection",
                    "degraded" if result.get("failed") else "completed",
                    result,
                )
                guard.send_alerts(collection_result=result)
                if result.get("triggered"):
                    self.scheduler.add_job(
                        self._run_sync,
                        "date",
                        args=["priority_followup"],
                        run_date=datetime.now() + timedelta(minutes=2),
                        id="priority_collection_followup",
                        name="重点公众号采集后补偿同步",
                        replace_existing=True,
                        misfire_grace_time=300,
                    )
                self._finish_run(
                    "degraded" if result.get("failed") else "done",
                    "重点公众号采集完成（存在失败）" if result.get("failed") else "重点公众号采集完成",
                    result,
                )
        except Exception as exc:
            logger.error("Priority collection failed: %s", exc)
            try:
                with contextlib.closing(SessionLocal()) as db:
                    guard = AutomationGuardService(db)
                    guard.record_maintenance_result("priority_collection", "failed", error=str(exc))
                    guard.send_alerts(collection_result={"failed": [{"error": str(exc)[:200]}]})
            except Exception as alert_exc:
                logger.error("Failed to record priority collection failure: %s", alert_exc)
            self._finish_run("error", f"重点公众号采集失败: {exc}")
        finally:
            self._execution_lock.release()

    def _run_feishu_reconcile(self) -> None:
        if not self._execution_lock.acquire(blocking=False):
            logger.info("Feishu reconcile skipped because maintenance is active")
            return
        try:
            from app.services.automation_guard import AutomationGuardService
            with contextlib.closing(SessionLocal()) as db:
                self._set_maintenance_status("feishu_reconcile", "正在读取飞书记录并对账…")
                guard = AutomationGuardService(db)
                result = guard.reconcile_feishu(repair_missing=False)
                degraded = bool(
                    result.get("missing_record_ids")
                    or result.get("field_drift_event_ids")
                    or result.get("missing_attachment_event_ids")
                    or result.get("remote_only_record_ids")
                )
                guard.record_maintenance_result(
                    "feishu_reconcile",
                    "degraded" if degraded else "completed",
                    result,
                )
                guard.send_alerts(reconcile=result)
                logger.info("Feishu reconcile result: %s", result)
                self._finish_run(
                    "degraded" if degraded else "done",
                    "飞书对账完成（发现差异）" if degraded else "飞书对账完成",
                    result,
                )
        except Exception as exc:
            logger.error("Feishu reconcile failed: %s", exc)
            try:
                with contextlib.closing(SessionLocal()) as db:
                    guard = AutomationGuardService(db)
                    guard.record_maintenance_result("feishu_reconcile", "failed", error=str(exc))
                    guard.send_alerts(reconcile={"run_error": str(exc)})
            except Exception as alert_exc:
                logger.error("Failed to record Feishu reconcile failure: %s", alert_exc)
            self._finish_run("error", f"飞书对账失败: {exc}")
        finally:
            self._execution_lock.release()

    def _retry_image_downloads(self, db: "Session") -> int:
        """重试 needs_image_retry 状态的事件：重新下载图片并抽取。"""
        retry_events = (
            db.query(Event)
            .options(joinedload(Event.article))
            .filter(Event.status == EventStatus.NEEDS_IMAGE_RETRY)
            .all()
        )
        if not retry_events:
            self._last_retry_metrics.update({
                "image_retry_attempted": 0,
                "image_retry_failed": 0,
            })
            return 0

        retried = 0
        article_service = ArticleService(db)
        for event in retry_events:
            try:
                article_service.process_article_images(event.article_id)
                if event.status != "needs_image_retry":
                    # 图片下载成功，重新抽取
                    EventExtractor(db).extract(event)
                    db.commit()
                    retried += 1
                    logger.info("Retried images for event %s, new status: %s", event.event_id, event.status)
            except Exception as exc:
                logger.warning("Image retry failed for event %s: %s", event.event_id, exc)

        if retried:
            logger.info("Image retry: %d events re-processed", retried)
        self._last_retry_metrics.update({
            "image_retry_attempted": len(retry_events),
            "image_retry_failed": len(retry_events) - retried,
        })
        return retried

    def _retry_failed_extracts(self, db: "Session") -> int:
        """重试 failed_extract 状态的事件：重新执行 AI 抽取。"""
        from app.services.event_extractor import EventExtractor

        failed_events = (
            db.query(Event)
            .options(joinedload(Event.article))
            .filter(Event.status == EventStatus.FAILED_EXTRACT)
            .limit(20)  # 每次最多重试 20 个
            .all()
        )
        if not failed_events:
            self._last_retry_metrics.update({
                "extract_retry_attempted": 0,
                "extract_retry_failed": 0,
            })
            return 0

        retried = 0
        extractor = EventExtractor(db)
        for event in failed_events:
            try:
                result = extractor.extract(event)
                db.commit()
                if event.status != EventStatus.FAILED_EXTRACT:
                    retried += 1
                    logger.info("Retried extract for event %s, new status: %s", event.event_id, event.status)
                else:
                    logger.debug("Extract retry still failed for event %s", event.event_id)
            except Exception as exc:
                logger.warning("Extract retry failed for event %s: %s", event.event_id, exc)

        if retried:
            logger.info("Extract retry: %d events recovered", retried)
        self._last_retry_metrics.update({
            "extract_retry_attempted": len(failed_events),
            "extract_retry_failed": len(failed_events) - retried,
        })
        return retried

    def _retry_failed_syncs(self, db: "Session") -> int:
        """Retry due Feishu failures with persistent exponential backoff."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        events = (
            db.query(Event)
            .filter(
                Event.status == EventStatus.FAILED_SYNC,
                Event.feishu_retry_count < self.settings.feishu_sync_retry_max,
                (Event.feishu_next_retry_at.is_(None)) | (Event.feishu_next_retry_at <= now),
            )
            .order_by(Event.feishu_next_retry_at.asc())
            .limit(50)
            .all()
        )
        if not events:
            self._last_retry_metrics.update({
                "failed_sync_retry_attempted": 0,
                "failed_sync_retry_failed": 0,
            })
            return 0
        synced = self._sync_event_ids_parallel(
            [event.event_id for event in events],
            label="重试飞书同步",
            max_workers=2,
        )
        self._last_retry_metrics.update({
            "failed_sync_retry_attempted": len(events),
            "failed_sync_retry_failed": len(events) - synced,
        })
        return synced

    def _refresh_event_statuses(self, db: "Session") -> int:
        """刷新已同步到飞书的事件的时间状态。

        检查所有 feishu_record_id 非空的事件，重新计算 event_time_status。
        如果状态发生变化（如 upcoming → past），更新本地记录并同步到飞书。
        """
        synced_events = (
            db.query(Event)
            .options(joinedload(Event.article))
            .filter(
                Event.feishu_record_id != "",
                Event.status.notin_(EventStatus.TERMINAL_STATUSES),
            )
            .all()
        )
        if not synced_events:
            return 0

        # 筛选出时间状态变化的事件
        to_refresh: list[tuple[str, str, str]] = []  # (event_id, old_status, new_status)
        for event in synced_events:
            old_status = event.event_time_status
            new_status = event_time_status(
                event.start_time,
                event.end_time,
                start_at=event.start_at,
                end_at=event.end_at,
                tz_name=event.timezone or "Asia/Shanghai",
            )
            if new_status != old_status:
                to_refresh.append((event.event_id, old_status, new_status))
                event.event_time_status = new_status
                EventPolicyService(db).apply(event)
                db.flush()

        if not to_refresh:
            return 0

        event_ids = [eid for eid, _, _ in to_refresh]
        logger.info("Refreshing %d events with changed time_status", len(event_ids))

        refreshed = self._sync_event_ids_parallel(
            event_ids, label="刷新状态", max_workers=2,
        )

        for event_id, old, new in to_refresh:
            logger.info("Refreshed event %s: time_status %s → %s", event_id, old, new)

        return refreshed

    def _backfill_missing_times(self, db: "Session") -> int:
        """回溯补提取缺少时间信息的事件。

        查询 event_time_status 为 unknown 且未进入终态的事件，
        重新调用 TimeExtractor 从文章内容中提取时间。
        每次同步最多处理 20 个事件，避免耗时过长。
        """
        from app.services.time_extractor import TimeExtractor

        limit = 20
        events = (
            db.query(Event)
            .options(joinedload(Event.article))
            .filter(
                Event.event_time_status == "unknown",
                Event.status.notin_(EventStatus.TERMINAL_STATUSES),
            )
            .limit(limit)
            .all()
        )
        if not events:
            return 0

        updated = 0
        time_extractor = TimeExtractor()
        for event in events:
            article = event.article
            if not article:
                continue
            try:
                candidate = time_extractor.extract(article, event, event.ocr_text or "")
                if not candidate:
                    continue
                changed = False
                if not event.start_time and candidate.start_time:
                    event.start_time = candidate.start_time
                    changed = True
                if not event.end_time and candidate.end_time:
                    event.end_time = candidate.end_time
                    changed = True
                if not changed:
                    continue
                # 重新计算时间状态
                new_time_status = event_time_status(
                    event.start_time,
                    event.end_time,
                    start_at=event.start_at,
                    end_at=event.end_at,
                    tz_name=event.timezone or "Asia/Shanghai",
                )
                event.event_time_status = new_time_status
                EventPolicyService(db).apply(event)
                db.flush()
                updated += 1
                logger.info(
                    "Backfilled time for event %s: start=%s end=%s time_status=%s",
                    event.event_id, event.start_time, event.end_time, new_time_status,
                )
            except Exception as exc:
                logger.warning("Time backfill failed for event %s: %s", event.event_id, exc)

        if updated:
            logger.info("Time backfill: %d events updated", updated)
        return updated

    def _sync_event_ids_parallel(
        self, event_ids: list[str], label: str, max_workers: int = 3
    ) -> int:
        """并行将事件同步到飞书。

        每个 worker 线程创建独立的 SessionLocal() 和 FeishuAdapter，
        遵循 ingest_candidates_parallel 的线程安全模式。

        Args:
            event_ids: 要同步的 event_id 列表
            label: 进度消息标签（如 "同步飞书"、"刷新状态"）
            max_workers: 最大并行数（默认 3，避免飞书 API 限流）

        Returns:
            成功同步的事件数
        """
        if not event_ids:
            return 0

        total = len(event_ids)

        def _sync_one(event_id: str) -> bool:
            for attempt in range(3):
                try:
                    with contextlib.closing(SessionLocal()) as worker_db:
                        event = (
                            worker_db.query(Event)
                            .options(joinedload(Event.article))
                            .filter(Event.event_id == event_id)
                            .first()
                        )
                        if not event:
                            logger.warning("Event %s not found, skipping", event_id)
                            return False
                        adapter = FeishuAdapter(worker_db)
                        result = adapter.sync_event(event)
                        return result.get("status") == "synced"
                except Exception as e:
                    if "database is locked" in str(e) and attempt < 2:
                        _time.sleep(0.5 * (attempt + 1))
                        continue
                    raise

        # 少量事件直接串行，避免 executor 开销
        if total <= 2:
            synced = 0
            for i, eid in enumerate(event_ids):
                with self._status_lock:
                    if self._sync_status["running"]:
                        self._sync_status["message"] = f"正在{label}… ({i + 1}/{total})"
                try:
                    if _sync_one(eid):
                        synced += 1
                except Exception as e:
                    logger.error("Failed to sync event %s: %s", eid, e)
            return synced

        # 多事件并行
        synced = 0
        completed = 0
        with ThreadPoolExecutor(max_workers=min(max_workers, total)) as executor:
            futures = {executor.submit(_sync_one, eid): eid for eid in event_ids}
            for future in as_completed(futures):
                eid = futures[future]
                try:
                    if future.result():
                        synced += 1
                except Exception as e:
                    logger.error("Failed to sync event %s: %s", eid, e)
                completed += 1
                with self._status_lock:
                    if self._sync_status["running"]:
                        self._sync_status["message"] = f"正在{label}… ({completed}/{total})"

        return synced

    def run_now(self) -> dict:
        """立即执行一次同步（供手动触发使用）。非阻塞，后台线程运行。"""
        if not self._begin_run("manual"):
            return {"status": "already_running", "message": "同步正在进行中"}

        def _run():
            try:
                logger.info("Running manual sync...")
                result = self._execute_sync("manual")
                degraded = result.get("run_status") == "degraded"
                self._finish_run(
                    "degraded" if degraded else "done",
                    "同步完成（存在部分失败）" if degraded else "同步完成",
                    result,
                )
                logger.info(
                    "Manual sync complete: %d articles fetched, %d events synced, %d failed",
                    result["articles_fetched"],
                    result["events_synced"],
                    result["events_failed"],
                )
            except Exception as e:
                logger.exception("Manual sync failed")
                self._finish_run("error", f"同步失败: {e}")
            finally:
                self._execution_lock.release()

        try:
            threading.Thread(target=_run, daemon=True).start()
        except Exception:
            self._finish_run("error", "同步后台线程启动失败")
            self._execution_lock.release()
            raise
        return {"status": "started", "message": "同步已启动"}

    def get_sync_status(self) -> dict:
        """返回当前同步状态。"""
        with self._status_lock:
            return dict(self._sync_status)

    def get_scheduler_status(self) -> dict:
        """返回调度器体征，而不仅是线程是否存活。"""
        required_jobs = []
        if self.settings.auto_sync_cron:
            required_jobs.append("auto_sync")
        if self.settings.priority_collection_cron:
            required_jobs.append("priority_collection")
        if self.settings.feishu_reconcile_enabled and self.settings.feishu_reconcile_cron:
            required_jobs.append("feishu_reconcile")

        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_at": job.next_run_time.isoformat() if job.next_run_time else None,
            })
        job_ids = {job["id"] for job in jobs}
        missing_jobs = [job_id for job_id in required_jobs if job_id not in job_ids]

        latest_run = None
        age_minutes = None
        try:
            with contextlib.closing(SessionLocal()) as db:
                latest_run = (
                    db.query(SyncRun)
                    .filter(SyncRun.source == "auto-sync")
                    .order_by(SyncRun.started_at.desc())
                    .first()
                )
                if latest_run and latest_run.started_at:
                    now = datetime.now(timezone.utc).replace(tzinfo=None)
                    age_minutes = round(max(0, (now - latest_run.started_at).total_seconds()) / 60, 1)
        except Exception as exc:
            logger.warning("Failed to inspect latest auto-sync run: %s", exc)

        stale = bool(
            missing_jobs
            or (
                self.settings.auto_sync_cron
                and (age_minutes is None or age_minutes > max(1, self.settings.auto_sync_stale_minutes))
            )
        )
        running = bool(self.scheduler.running)
        status = "error" if not running else ("degraded" if missing_jobs or stale else "ok")
        return {
            "status": status,
            "running": running,
            "required_jobs": required_jobs,
            "missing_jobs": missing_jobs,
            "jobs": jobs,
            "last_sync_at": latest_run.started_at.isoformat() if latest_run and latest_run.started_at else None,
            "last_sync_status": latest_run.status if latest_run else None,
            "last_sync_age_minutes": age_minutes,
            "stale": stale,
            "stale_after_minutes": max(1, self.settings.auto_sync_stale_minutes),
        }

    def _begin_run(self, trigger: str) -> bool:
        """Atomically reserve the single maintenance execution slot."""
        if not self._execution_lock.acquire(blocking=False):
            return False
        with self._status_lock:
            self._sync_status.update({
                "running": True,
                "status": "running",
                "phase": "fetching",
                "message": "正在拉取文章…",
                "result": None,
                "trigger": trigger,
                "started_at": datetime.now(timezone.utc).isoformat(),
            })
        return True

    def _set_maintenance_status(self, trigger: str, message: str) -> None:
        with self._status_lock:
            self._sync_status.update({
                "running": True,
                "status": "running",
                "phase": "syncing" if "飞书" in message else "fetching",
                "message": message,
                "result": None,
                "trigger": trigger,
                "started_at": datetime.now(timezone.utc).isoformat(),
            })

    def _finish_run(self, phase: str, message: str, result: dict | None = None) -> None:
        with self._status_lock:
            self._sync_status.update({
                "running": False,
                "status": "error" if phase == "error" else ("degraded" if phase == "degraded" else "done"),
                "phase": phase,
                "message": message,
                "result": result,
            })

    def notify_new_events(self, result: dict) -> None:
        """同步完成后发送飞书通知（仅当有新活动入库时）。"""
        events_synced = result.get("events_synced", 0)
        if events_synced <= 0:
            return

        articles_fetched = result.get("articles_fetched", 0)
        try:
            from app.services.feishu_messenger import FeishuMessenger
            messenger = FeishuMessenger()
            message = (
                f"GoActivity 同步完成: {articles_fetched}个新活动已入库, "
                f"{events_synced}个已同步到飞书"
            )
            messenger.send_daily_report(message)
            logger.info("Sync notification sent: %s", message)
        except Exception as exc:
            logger.warning("Failed to send sync notification: %s", exc)
