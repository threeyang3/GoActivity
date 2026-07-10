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
        self._sync_status = {
            "running": False,
            "phase": "idle",       # idle | fetching | extracting | syncing | done | error
            "message": "",
            "result": None,
            "started_at": None,
        }

    def start(self) -> None:
        """启动定时任务调度器。"""
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

        self.scheduler.start()
        logger.info("Auto sync scheduler started")

    def shutdown(self) -> None:
        """关闭定时任务调度器。"""
        self.scheduler.shutdown()
        logger.info("Auto sync scheduler stopped")

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

    def _execute_sync(self) -> dict:
        """执行一次完整同步（拉取文章 + 同步到飞书）。

        Returns:
            包含 articles_fetched, events_synced, events_failed 的字典。
        """
        sync_start_time = datetime.now()
        logger.info("=" * 60)
        logger.info("同步开始 | 时间: %s", sync_start_time.strftime("%Y-%m-%d %H:%M:%S"))

        with contextlib.closing(SessionLocal()) as db:
            run_service = SyncRunService(db)
            run = run_service.start_run("auto-sync", {"trigger": "scheduled"})

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
                ingest_duration = (datetime.now() - ingest_start).total_seconds()
                logger.info(
                    "步骤2/6 完成 | 成功入库 %d 篇文章 | 耗时: %.1f秒",
                    len(articles), ingest_duration
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
                    "articles_fetched": len(articles),
                    "images_retried": retried,
                    "extracts_retried": extract_retried,
                    "times_backfilled": backfilled,
                    "statuses_refreshed": refreshed,
                    "events_synced": synced,
                    "events_failed": failed,
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

                if failed == 0:
                    run_service.finish_success(run, imported_count=len(articles), results=[result])
                else:
                    run_service.finish_failure(run, f"{failed} events failed to sync")

                # 7. 新活动通知
                self.notify_new_events(result)

                # 输出同步总结
                total_duration = (datetime.now() - sync_start_time).total_seconds()
                logger.info("-" * 60)
                logger.info("同步完成 | 总耗时: %.1f秒", total_duration)
                logger.info(
                    "同步结果 | 文章: %d | 飞书同步: %d | 失败: %d",
                    len(articles), synced, failed
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

    def _run_sync(self) -> None:
        """定时任务回调：执行同步并记录日志。"""
        try:
            result = self._execute_sync()
        except Exception as e:
            logger.error("定时同步失败: %s", e)

    def _run_archive_only(self) -> None:
        """独立运行自动归档（不依赖同步流程）。

        启动时运行一次，将过期且未保护的事件自动归档。
        """
        auto_archive_days = self.settings.auto_archive_expired_days
        if auto_archive_days <= 0:
            return

        logger.info("Running standalone auto-archive (cutoff=%d days)...", auto_archive_days)
        try:
            with contextlib.closing(SessionLocal()) as db:
                # 先刷新事件时间状态（确保 event_time_status 是最新的）
                self._refresh_event_statuses(db)

                from app.services.archive_service import ArchiveService
                archive_service = ArchiveService(db)
                result = archive_service.auto_archive_expired(auto_archive_days)
                if result.get("archived", 0) > 0:
                    logger.info("Standalone auto-archive result: %s", result)
                else:
                    logger.info("Standalone auto-archive: no events to archive")
        except Exception as e:
            logger.error("Standalone auto-archive failed: %s", e)

    def _retry_image_downloads(self, db: "Session") -> int:
        """重试 needs_image_retry 状态的事件：重新下载图片并抽取。"""
        retry_events = (
            db.query(Event)
            .options(joinedload(Event.article))
            .filter(Event.status == EventStatus.NEEDS_IMAGE_RETRY)
            .all()
        )
        if not retry_events:
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
        return retried

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
            new_status = event_time_status(event.start_time, event.end_time)
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
                new_time_status = event_time_status(event.start_time, event.end_time)
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
                self._sync_status["message"] = f"正在{label}… ({completed}/{total})"

        return synced

    def run_now(self) -> dict:
        """立即执行一次同步（供手动触发使用）。非阻塞，后台线程运行。"""
        if self._sync_status["running"]:
            return {"status": "already_running", "message": "同步正在进行中"}

        def _run():
            self._sync_status.update({
                "running": True,
                "phase": "fetching",
                "message": "正在拉取文章…",
                "result": None,
                "started_at": datetime.now(timezone.utc).isoformat(),
            })
            try:
                logger.info("Running manual sync...")
                result = self._execute_sync()
                self._sync_status.update({
                    "running": False,
                    "phase": "done",
                    "message": "同步完成",
                    "result": result,
                })
                logger.info(
                    "Manual sync complete: %d articles fetched, %d events synced, %d failed",
                    result["articles_fetched"],
                    result["events_synced"],
                    result["events_failed"],
                )
            except Exception as e:
                logger.exception("Manual sync failed")
                self._sync_status.update({
                    "running": False,
                    "phase": "error",
                    "message": f"同步失败: {e}",
                    "result": None,
                })

        threading.Thread(target=_run, daemon=True).start()
        return {"status": "started", "message": "同步已启动"}

    def get_sync_status(self) -> dict:
        """返回当前同步状态。"""
        return dict(self._sync_status)

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
