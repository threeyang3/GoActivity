import json
import logging
import contextlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.adapters.we_mp_rss import WeMpRssClient, normalize_payload
from app.config import get_settings
from app.models import Article, Event
from app.services.event_policy import evaluate_article_gate
from app.services.event_extractor import EventExtractor
from app.services.image_service import ImageService, select_key_images
from app.utils.constants import EventStatus
from app.utils.ids import stable_id
from app.utils.jsonx import dumps_json, dumps_list, loads_list
from app.utils.time import utcnow, parse_to_epoch

logger = logging.getLogger(__name__)


class ArticleService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def ingest_we_mp_rss_payload(self, payload: dict) -> dict:
        data = normalize_payload(payload)
        return self._ingest_normalized_payload(data, payload)

    def fetch_candidates(
        self,
        limit: int = 20,
        offset: int = 0,
        include_no_content: bool = False,
    ) -> list[dict]:
        """从 we-mp-rss 拉取新文章候选列表（去重 + 补全 content）。

        此方法只做 HTTP 拉取和 DB 去重检查，不做入库，速度快。
        """
        client = WeMpRssClient()
        page_size = max(1, min(limit, 50))

        seen_ids: set[str] = set()
        candidates: list[dict] = []
        page_offset = offset
        while len(candidates) < limit:
            page = client.fetch_articles(
                limit=page_size,
                offset=page_offset,
                has_content=not include_no_content,
            )
            if not page:
                break
            page_offset += len(page)
            for payload in page:
                normalized = normalize_payload(payload)
                article_id = normalized.get("article_id", "")
                if not article_id or article_id in seen_ids:
                    continue
                if self.db.query(Article.article_id).filter(Article.article_id == article_id).first():
                    seen_ids.add(article_id)
                    continue
                seen_ids.add(article_id)
                candidates.append(payload)
                if len(candidates) >= limit:
                    break
            if len(page) < page_size:
                break

        if candidates:
            self._enrich_payloads_parallel(client, candidates)

        return candidates

    def ingest_candidates_parallel(
        self, candidates: list[dict], on_progress=None
    ) -> list[dict]:
        """并行入库候选文章。on_progress(completed, total) 可选回调。"""
        from app.db import SessionLocal

        if not candidates:
            return []

        def _ingest_one(payload: dict) -> dict:
            import time as _time
            for attempt in range(3):
                try:
                    with contextlib.closing(SessionLocal()) as worker_db:
                        svc = ArticleService(worker_db)
                        return svc.ingest_we_mp_rss_payload(payload)
                except Exception as e:
                    if "database is locked" in str(e) and attempt < 2:
                        _time.sleep(0.5 * (attempt + 1))
                        continue
                    raise

        total = len(candidates)
        if total <= 4:
            results = []
            for i, p in enumerate(candidates):
                try:
                    results.append(self.ingest_we_mp_rss_payload(p))
                except Exception as e:
                    logger.error("Failed to ingest article: %s", e)
                if on_progress:
                    on_progress(i + 1, total)
            return results

        max_workers = min(4, total)
        results = []
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_ingest_one, p): p for p in candidates}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    logger.error("Failed to ingest article: %s", e)
                completed += 1
                if on_progress:
                    on_progress(completed, total)
        return results

    def sync_from_we_mp_rss_articles(
        self,
        limit: int = 20,
        offset: int = 0,
        include_no_content: bool = False,
    ) -> list[dict]:
        """兼容旧接口：拉取 + 入库一步完成。"""
        candidates = self.fetch_candidates(limit, offset, include_no_content)
        return self.ingest_candidates_parallel(candidates)

    def _enrich_payloads_parallel(
        self, client: WeMpRssClient, payloads: list[dict]
    ) -> None:
        """并行获取缺少 content 的文章详情。直接修改 payloads 列表中的元素。"""
        need_enrich = [
            (i, p)
            for i, p in enumerate(payloads)
            if not p.get("content_html") and not p.get("content")
        ]
        if not need_enrich:
            return

        def fetch(idx_payload: tuple[int, dict]) -> tuple[int, dict | None]:
            idx, payload = idx_payload
            article_id = str(
                payload.get("id") or payload.get("article_id") or ""
            ).strip()
            if not article_id:
                return idx, None
            try:
                detail = client.fetch_article_detail(article_id)
                return idx, detail
            except Exception as exc:
                logger.warning("Failed to fetch article detail %s: %s", article_id, exc)
                return idx, None

        max_workers = min(8, len(need_enrich))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(fetch, item) for item in need_enrich]
            for future in as_completed(futures):
                idx, detail = future.result()
                if detail:
                    payloads[idx].update(detail)

    def sync_from_we_mp_rss_rss(
        self, feed_id: str = "all", limit: int = 20, offset: int = 0
    ) -> list[dict]:
        client = WeMpRssClient()
        seen_ids: set[str] = set()
        results: list[dict] = []
        for payload in client.fetch_rss_articles(
            feed_id=feed_id, limit=limit, offset=offset
        ):
            normalized = normalize_payload(payload)
            article_id = normalized.get("article_id", "")
            if not article_id or article_id in seen_ids:
                continue
            if self.db.query(Article.article_id).filter(Article.article_id == article_id).first():
                seen_ids.add(article_id)
                continue
            seen_ids.add(article_id)
            results.append(self.ingest_we_mp_rss_payload(payload))
        return results

    def process_article_images(self, article_id: str) -> dict:
        article = (
            self.db.query(Article)
            .filter(Article.article_id == article_id)
            .one_or_none()
        )
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        image_count = self._process_images(article)
        event = self._ensure_event_candidate(article)
        if any(
            image.download_status != "downloaded" for image in article.images
        ):
            event.status = EventStatus.NEEDS_IMAGE_RETRY
        self.db.commit()
        return {
            "article_id": article.article_id,
            "event_id": event.event_id,
            "image_count": image_count,
            "status": event.status,
        }

    def refilter_event_images(self, event: Event) -> bool:
        """重新过滤事件的海报图片（应用装饰性图片过滤规则）。

        Returns:
            True 如果 poster_images 发生了变化。
        """
        article = (
            self.db.query(Article)
            .filter(Article.article_id == event.article_id)
            .one_or_none()
        )
        if not article:
            return False

        old_poster_images = loads_list(event.poster_images)
        new_poster_images = [
            image.local_path
            for image in select_key_images(article.images)
            if image.local_path
        ]

        if old_poster_images == new_poster_images:
            return False

        event.poster_images = dumps_list(new_poster_images)
        # 更新封面图
        if new_poster_images:
            event.cover_image = new_poster_images[0]
        elif event.cover_image in old_poster_images:
            event.cover_image = ""
        event.updated_at = utcnow()
        self.db.flush()
        return True

    def _upsert_article(
        self, data: dict[str, str], raw_payload: dict
    ) -> Article:
        article = (
            self.db.query(Article)
            .filter(Article.article_id == data["article_id"])
            .one_or_none()
        )
        now = utcnow()
        if article is None:
            article = Article(article_id=data["article_id"])
            self.db.add(article)
        article.title = data["title"]
        article.mp_name = data["mp_name"]
        article.publish_time = data["publish_time"]
        article.url = data["url"]
        article.pic_url = data.get("pic_url", "")
        article.raw_payload = json.dumps(raw_payload, ensure_ascii=False)
        article.raw_markdown = data["markdown"]
        article.updated_at = now
        article.markdown_path = str(
            self._write_article_file(
                article.article_id, "raw.md", data["markdown"]
            )
        )
        self.db.flush()
        return article

    def _ingest_normalized_payload(
        self, data: dict[str, str], raw_payload: dict
    ) -> dict:
        gate = evaluate_article_gate(
            data["title"], data["markdown"], data["publish_time"]
        )
        if gate.should_skip:
            return {
                "article_id": data["article_id"],
                "event_id": "",
                "image_count": 0,
                "status": gate.retention_decision,
            }
        article = self._upsert_article(data, raw_payload)
        image_count = self._process_images(article)
        event = self._ensure_event_candidate(article)
        EventExtractor(self.db).extract(event)
        # 去重：如果另一个 event 已有相同 dedup_key，合并到已有 event
        event = self._dedup_event(event)
        self.db.commit()
        return {
            "article_id": article.article_id,
            "event_id": event.event_id,
            "image_count": image_count,
            "status": event.status,
        }

    def _dedup_event(self, event: Event) -> Event:
        """检查 dedup_key 冲突，如果已有相同活动则合并。返回最终保留的 event。

        合并策略：保留已有 event，但从新 event 中补充缺失或更完整的字段。
        """
        if not event.dedup_key:
            return event
        existing = (
            self.db.query(Event)
            .filter(
                Event.dedup_key == event.dedup_key,
                Event.event_id != event.event_id,
                Event.status.notin_(EventStatus.TERMINAL_STATUSES),
            )
            .first()
        )
        if not existing:
            return event
        logger.info(
            "Dedup: event %s matches existing %s (key=%s), merging article %s",
            event.event_id, existing.event_id, event.dedup_key, event.article_id,
        )

        # 合并策略：从新 event 补充缺失字段
        merge_fields = [
            "location", "speaker", "organizer", "registration", "summary",
            "performance_type", "performance_name", "performer", "ticket_info",
            "lecture_topic", "speaker_title", "lecture_series",
            "competition_name", "competition_type", "deadline", "prize_info",
            "registration_url", "registration_deadline", "participant_limit",
        ]
        for field in merge_fields:
            existing_val = getattr(existing, field, "") or ""
            new_val = getattr(event, field, "") or ""
            if not existing_val and new_val:
                setattr(existing, field, new_val)

        # 保留更高的置信度
        if (event.confidence or 0) > (existing.confidence or 0):
            existing.confidence = event.confidence

        # 更新 source_url
        if not existing.source_url:
            article = self.db.query(Article).filter(Article.article_id == event.article_id).one_or_none()
            if article:
                existing.source_url = article.url

        # 删除新创建的 event
        self.db.delete(event)
        self.db.flush()
        return existing

    def _enrich_we_mp_rss_article_payload(
        self, client: WeMpRssClient, payload: dict
    ) -> dict:
        article_id = str(
            payload.get("id") or payload.get("article_id") or ""
        ).strip()
        if not article_id:
            return payload
        if payload.get("content_html") or payload.get("content"):
            return payload
        detail = client.fetch_article_detail(article_id)
        if not detail:
            return payload
        merged = dict(payload)
        merged.update(detail)
        return merged

    def _process_images(self, article: Article) -> int:
        processed_markdown, images = ImageService(self.db).process_article(
            article
        )
        article.processed_markdown = processed_markdown
        article.processed_markdown_path = str(
            self._write_article_file(
                article.article_id, "processed.md", processed_markdown
            )
        )
        return len(images)

    def _ensure_event_candidate(self, article: Article) -> Event:
        event = (
            self.db.query(Event)
            .filter(Event.article_id == article.article_id)
            .one_or_none()
        )
        if event is None:
            event = Event(
                event_id=stable_id("event", article.article_id),
                article_id=article.article_id,
            )
            self.db.add(event)
        poster_images = [
            image.local_path
            for image in select_key_images(article.images)
            if image.local_path
        ]
        event.title = event.title or article.title
        event.source_url = article.url
        event.poster_images = dumps_list(poster_images)
        event.ocr_text = "\n".join(
            image.ocr_text for image in article.images if image.ocr_text
        )
        event.vision_result = event.vision_result or dumps_json({})
        if any(
            image.download_status != "downloaded"
            for image in article.images
        ):
            event.status = EventStatus.NEEDS_IMAGE_RETRY
        elif event.status == EventStatus.PENDING:
            event.status = EventStatus.PENDING_AI
        return event

    def _write_article_file(
        self, article_id: str, filename: str, content: str
    ) -> Path:
        article_dir = self.settings.articles_dir / article_id
        article_dir.mkdir(parents=True, exist_ok=True)
        path = article_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    # 以下方法保留，供其他调用方使用（如 diagnostics、旧 webhook）

    def _latest_publish_time_by_mp(self) -> dict[str, int]:
        rows = (
            self.db.query(Article.mp_name, func.max(Article.publish_time))
            .filter(Article.mp_name != "")
            .group_by(Article.mp_name)
            .all()
        )
        return {
            str(mp_name): parsed
            for mp_name, publish_time in rows
            if mp_name
            and (parsed := self._publish_time_to_epoch(str(publish_time)))
        }

    def _should_ingest_incrementally(
        self, data: dict[str, str], local_latest: dict[str, int]
    ) -> bool:
        """保留用于 webhook 调用（单条推入时仍按时间判断是否更新）。"""
        mp_name = data.get("mp_name", "").strip()
        if not mp_name:
            return True
        latest_known = local_latest.get(mp_name)
        if latest_known is None:
            return True
        published_at = self._publish_time_to_epoch(
            data.get("publish_time", "")
        )
        if published_at is None:
            return True
        return published_at > latest_known

    @staticmethod
    def _publish_time_to_epoch(value: str) -> int | None:
        """解析发布时间为 Unix 时间戳，委托给统一的 parse_to_epoch。"""
        return parse_to_epoch(value)
