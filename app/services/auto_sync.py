"""自动同步服务。

定时从 we-mp-rss 拉取新文章，自动抽取活动信息，同步到飞书。
"""

import contextlib
import logging
import threading
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.utils.constants import EventStatus
from app.utils.cron import parse_cron
from app.db import SessionLocal
from app.models import Event
from app.services.article_service import ArticleService
from app.services.event_extractor import EventExtractor
from app.services.event_policy import EventPolicyService, event_time_status
from app.services.feishu import FeishuAdapter
from app.services.sync_run_service import SyncRunService

logger = logging.getLogger(__name__)


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

    def _execute_sync(self) -> dict:
        """执行一次完整同步（拉取文章 + 同步到飞书）。

        Returns:
            包含 articles_fetched, events_synced, events_failed 的字典。
        """
        with contextlib.closing(SessionLocal()) as db:
            run_service = SyncRunService(db)
            run = run_service.start_run("auto-sync", {"trigger": "scheduled"})

            try:
                # 1. 从 we-mp-rss 拉取新文章候选（快速，仅 HTTP + DB 去重）
                self._sync_status["phase"] = "fetching"
                self._sync_status["message"] = "正在从 we-mp-rss 拉取文章…"
                article_service = ArticleService(db)
                candidates = article_service.fetch_candidates(
                    limit=50, include_no_content=False
                )
                logger.info("Fetched %d new article candidates", len(candidates))

                # 2. 并行入库（图片下载 + Vision 抽取，耗时操作）
                self._sync_status["phase"] = "extracting"
                self._sync_status["message"] = f"已拉取 {len(candidates)} 篇文章，正在并行处理…"

                def _on_ingest_progress(completed: int, total: int):
                    self._sync_status["message"] = f"正在处理文章… ({completed}/{total})"

                articles = article_service.ingest_candidates_parallel(
                    candidates, on_progress=_on_ingest_progress
                )

                # 2. 重试失败的图片下载 + 重新抽取
                self._sync_status["phase"] = "extracting"
                self._sync_status["message"] = f"已拉取 {len(articles)} 篇文章，正在重试图片下载…"
                retried = self._retry_image_downloads(db)

                # 3. 刷新已同步事件的时间状态（过期 → past 等）
                self._sync_status["message"] = "正在刷新事件时间状态…"
                refreshed = self._refresh_event_statuses(db)

                # 4. 同步新事件到飞书
                self._sync_status["phase"] = "syncing"
                self._sync_status["message"] = "正在同步到飞书…"
                feishu_adapter = FeishuAdapter(db)
                events = (
                    db.query(Event)
                    .options(joinedload(Event.article))
                    .filter(
                        Event.status.in_([EventStatus.EXTRACTED, EventStatus.PENDING_AI]),
                        Event.feishu_record_id == "",
                    )
                    .all()
                )

                synced = 0
                failed = 0
                total = len(events)
                for i, event in enumerate(events):
                    self._sync_status["message"] = f"正在同步飞书… ({i+1}/{total})"
                    try:
                        result = feishu_adapter.sync_event(event)
                        if result.get("status") == "synced":
                            synced += 1
                        else:
                            failed += 1
                    except Exception as e:
                        failed += 1
                        logger.error("Failed to sync event %s: %s", event.event_id, e)

                result = {
                    "articles_fetched": len(articles),
                    "images_retried": retried,
                    "statuses_refreshed": refreshed,
                    "events_synced": synced,
                    "events_failed": failed,
                }

                if failed == 0:
                    run_service.finish_success(run, imported_count=len(articles), results=[result])
                else:
                    run_service.finish_failure(run, f"{failed} events failed to sync")

                return result
            except Exception as exc:
                run_service.finish_failure(run, str(exc))
                raise

    def _run_sync(self) -> None:
        """定时任务回调：执行同步并记录日志。"""
        logger.info("Starting auto sync...")
        try:
            result = self._execute_sync()
            logger.info(
                "Auto sync complete: %d articles fetched, %d events synced, %d failed",
                result["articles_fetched"],
                result["events_synced"],
                result["events_failed"],
            )
        except Exception as e:
            logger.error("Auto sync failed: %s", e)

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

    def _refresh_event_statuses(self, db: "Session") -> int:
        """刷新已同步到飞书的事件的时间状态。

        检查所有 feishu_record_id 非空的事件，重新计算 event_time_status。
        如果状态发生变化（如 upcoming → past），更新本地记录并同步到飞书。
        """
        from app.services.article_service import Article as _Article  # noqa: F811

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

        feishu_adapter = FeishuAdapter(db)
        refreshed = 0
        for event in synced_events:
            old_status = event.event_time_status
            new_status = event_time_status(event.start_time, event.end_time)
            if new_status == old_status:
                continue

            # 时间状态发生了变化，重新评估保留策略
            event.event_time_status = new_status
            EventPolicyService(db).apply(event)
            db.flush()

            # 同步到飞书
            try:
                feishu_adapter.sync_event(event)
                refreshed += 1
                logger.info(
                    "Refreshed event %s: time_status %s → %s, retention: %s",
                    event.event_id, old_status, new_status, event.retention_decision,
                )
            except Exception as exc:
                logger.warning("Failed to sync refreshed event %s: %s", event.event_id, exc)

        if refreshed:
            logger.info("Event status refresh: %d events updated", refreshed)
        return refreshed

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
