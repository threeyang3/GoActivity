"""活动归档服务。

归档 ≠ 删除：归档是软删除，清除重数据（图片、markdown、OCR），
保留轻量信息（标题、日期、原文链接等）用于追溯。
"""

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.models import Article, Event, Image
from app.utils.constants import EventStatus, RetentionDecision
from app.utils.time import from_storage_datetime, parse_datetime_str, utcnow

logger = logging.getLogger(__name__)


class ArchiveService:
    """活动归档服务。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def archive_event(self, event: Event, source: str = "user") -> dict:
        """归档单个事件：清重数据 + 更新飞书 + 删文件。

        Args:
            event: 要归档的事件
            source: 归档来源 ("user" 或 "auto")

        Returns:
            操作结果字典
        """
        if event.status == EventStatus.ARCHIVED:
            return {"status": "already_archived", "message": "事件已归档"}

        # 自动归档时检查保护标记（手动归档不受限制）
        if source == "auto":
            if event.user_keep:
                return {"status": "protected", "message": "事件已置顶，跳过自动归档"}
            if event.user_participate:
                return {"status": "protected", "message": "用户标记参与，跳过自动归档"}

        # 1. 清除重数据
        self._clear_heavy_data(event)

        # 2. 删除本地文件
        self._delete_local_files(event)

        # 3. 更新事件状态
        now = utcnow()
        event.status = EventStatus.ARCHIVED
        event.retention_decision = (
            RetentionDecision.USER_ARCHIVED if source == "user"
            else RetentionDecision.AUTO_ARCHIVED
        )
        event.archived_at = now
        event.updated_at = now
        self.db.flush()

        # 4. 同步到飞书（如果有记录）
        feishu_result = None
        if event.feishu_record_id:
            try:
                from app.services.feishu import FeishuAdapter
                adapter = FeishuAdapter(self.db)
                feishu_result = adapter.sync_event(event)
            except Exception as exc:
                logger.warning("Failed to sync archive to Feishu for %s: %s", event.event_id, exc)

        self.db.commit()

        logger.info(
            "Archived event %s (source=%s, title=%s)",
            event.event_id, source, event.title,
        )

        return {
            "status": "archived",
            "event_id": event.event_id,
            "archived_at": now.isoformat(),
            "feishu_result": feishu_result,
        }

    def unarchive_event(self, event: Event) -> dict:
        """取消归档：恢复状态为 extracted（需重新同步飞书）。"""
        if event.status != EventStatus.ARCHIVED:
            return {"status": "not_archived", "message": "事件未归档"}

        event.status = EventStatus.EXTRACTED
        event.retention_decision = RetentionDecision.KEEP
        event.archived_at = None
        event.updated_at = utcnow()
        self.db.commit()

        logger.info("Unarchived event %s", event.event_id)

        return {
            "status": "unarchived",
            "event_id": event.event_id,
            "message": "已取消归档，需重新同步到飞书",
        }

    def auto_archive_expired(self, days: int = 30) -> dict:
        """自动归档过期事件。

        条件：
        - event_time_status 为 expired 或 past
        - 结束时间距今超过 N 天
        - user_keep = False
        - user_participate = False
        - status 不在终态（不重复归档）

        Returns:
            统计信息
        """
        if days <= 0:
            return {"archived": 0, "skipped": 0, "message": "自动归档已禁用"}

        cutoff = utcnow() - timedelta(days=days)

        # 查询候选事件
        candidates = (
            self.db.query(Event)
            .options(joinedload(Event.article))
            .filter(
                Event.status.notin_(EventStatus.TERMINAL_STATUSES),
                Event.user_keep == False,
                Event.user_participate == False,
            )
            .all()
        )

        archived = 0
        skipped = 0
        protected = 0

        for event in candidates:
            # 判断是否过期
            if not self._is_expired_past_cutoff(event, cutoff):
                skipped += 1
                continue

            result = self.archive_event(event, source="auto")
            if result["status"] == "archived":
                archived += 1
            elif result["status"] == "protected":
                protected += 1
            else:
                skipped += 1

        if archived > 0:
            logger.info("Auto-archived %d expired events (cutoff=%d days)", archived, days)

        return {
            "archived": archived,
            "skipped": skipped,
            "protected": protected,
            "cutoff_days": days,
        }

    def _is_expired_past_cutoff(self, event: Event, cutoff: datetime) -> bool:
        """判断事件是否过期超过截止时间。"""
        # 优先使用 event_time_status
        if event.event_time_status not in ("expired", "past", "ended"):
            return False

        # 尝试解析结束时间
        end_at = from_storage_datetime(event.end_at, event.timezone or "Asia/Shanghai")
        if not end_at:
            end_time = event.end_time or event.start_time
            if not end_time:
                return False
            end_at = parse_datetime_str(end_time)
        if not end_at:
            return False

        # 统一时区：将 cutoff 提升为 timezone-aware（上海时区）再比较
        from app.utils.time import SHANGHAI_TZ
        if end_at.tzinfo is None:
            end_at = end_at.replace(tzinfo=SHANGHAI_TZ)
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=SHANGHAI_TZ)

        return end_at < cutoff

    def _clear_heavy_data(self, event: Event) -> None:
        """清除事件和关联文章的重数据字段。"""
        # 清除事件的重数据
        event.ocr_text = ""
        event.vision_result = "{}"
        event.poster_images = "[]"
        event.cover_image = ""

        # 清除关联文章的重数据
        article = self.db.query(Article).filter(
            Article.article_id == event.article_id
        ).first()
        if article:
            article.raw_payload = "{}"
            article.raw_markdown = ""
            article.processed_markdown = ""
            article.markdown_path = ""
            article.processed_markdown_path = ""

            # 清除关联的 Image 记录
            images = self.db.query(Image).filter(
                Image.article_id == article.article_id
            ).all()
            for img in images:
                self.db.delete(img)

        self.db.flush()

    def _delete_local_files(self, event: Event) -> None:
        """删除磁盘上的图片和 markdown 文件。"""
        # 删除图片目录
        images_dir = self.settings.images_dir / event.article_id
        if images_dir.exists():
            try:
                shutil.rmtree(images_dir)
                logger.debug("Deleted images dir: %s", images_dir)
            except Exception as exc:
                logger.warning("Failed to delete images dir %s: %s", images_dir, exc)

        # 删除文章 markdown 文件
        article = self.db.query(Article).filter(
            Article.article_id == event.article_id
        ).first()
        if article:
            for path_attr in ("markdown_path", "processed_markdown_path"):
                file_path = getattr(article, path_attr, "")
                if file_path:
                    p = Path(file_path)
                    if p.exists():
                        try:
                            p.unlink()
                            logger.debug("Deleted file: %s", p)
                        except Exception as exc:
                            logger.warning("Failed to delete file %s: %s", p, exc)
