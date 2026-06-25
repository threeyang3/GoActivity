import hashlib
import logging
import re
import traceback
from typing import Any

from sqlalchemy.orm import Session

from app.models import Article, Event, Image
from app.services.content_classifier import ContentClassifier
from app.services.event_policy import EventPolicyService, parse_datetime
from app.services.extraction_validator import ExtractionValidator
from app.services.image_service import select_key_images
from app.services.ocr import OCRExtractor
from app.services.providers import ProviderSelectionError
from app.services.time_extractor import TimeExtractor
from app.services.vision import VisionExtractor
from app.utils.constants import EventStatus
from app.utils.jsonx import dumps_json, dumps_list, loads_list
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


class EventExtractor:
    def __init__(self, db: Session) -> None:
        self.db = db

    def extract(self, event: Event) -> dict[str, Any]:
        article = self.db.query(Article).filter(Article.article_id == event.article_id).one_or_none()
        if article is None:
            logger.warning("Article %s not found for event %s, skipping extraction", event.article_id, event.event_id)
            return {}
        images = self.db.query(Image).filter(Image.article_id == event.article_id).all()
        image_paths = [image.local_path for image in select_key_images(images) if image.local_path]
        ocr_text = ""
        vision: dict[str, Any] = {}
        extraction_ok = False
        try:
            # 无图片时跳过 OCR，节省 API 调用
            if image_paths:
                ocr_text = OCRExtractor().extract(image_paths)
            # 无图片且文章较短时，跳过 Vision API（纯文字文章抽取价值低）
            content_len = len(article.processed_markdown or article.raw_markdown or "")
            if image_paths or content_len > 500:
                vision = VisionExtractor().analyze(article.title, article.processed_markdown, image_paths, ocr_text)
            self._apply_result(event, vision, ocr_text)
            ExtractionValidator().validate(event)
            extraction_ok = True
        except ProviderSelectionError as exc:
            logger.warning("Provider not available for event %s: %s", event.event_id, exc)
            event.status = EventStatus.PENDING_AI
            event.ocr_text = ocr_text
            event.vision_result = dumps_json({"provider_error": str(exc)})
        except Exception as exc:
            logger.error("Extraction failed for event %s: %s\n%s", event.event_id, exc, traceback.format_exc())
            event.status = EventStatus.FAILED_EXTRACT
            event.ocr_text = ocr_text
            event.vision_result = dumps_json({"error": str(exc)})
        self._apply_time_fallback(article, event, ocr_text)
        self._apply_content_classification(article, event)
        # 只在抽取成功时生成 dedup_key，避免空字段碰撞
        if extraction_ok:
            event.dedup_key = self._generate_dedup_key(event)
        EventPolicyService(self.db).apply(event)
        event.updated_at = utcnow()
        self.db.flush()
        return {
            "ocr_text": event.ocr_text,
            "vision_result": vision,
            "status": event.status,
        }

    def _apply_result(self, event: Event, result: dict[str, Any], ocr_text: str) -> None:
        event.title = result.get("event_name") or event.title
        event.category_1 = result.get("category_1") or "其他"
        event.category_2 = result.get("category_2") or ""
        event.start_time = result.get("start_time") or ""
        event.end_time = result.get("end_time") or ""
        event.location = result.get("location") or ""
        event.speaker = result.get("speaker") or ""
        event.organizer = result.get("organizer") or ""
        event.registration = result.get("registration") or ""
        event.summary = result.get("summary") or ""
        event.tags = dumps_list(result.get("tags") or [])
        event.poster_images = dumps_list(result.get("poster_images") or loads_list(event.poster_images))
        event.ocr_text = ocr_text
        event.vision_result = dumps_json(result)
        event.confidence = float(result.get("confidence") or 0.0)
        event.status = EventStatus.PENDING_AI if not result.get("is_event", True) else EventStatus.EXTRACTED

        # 设置封面图片（第一张海报）
        poster_images = loads_list(event.poster_images)
        if poster_images and not event.cover_image:
            event.cover_image = poster_images[0]

        # 演出信息
        event.performance_type = result.get("performance_type") or ""
        event.performance_name = result.get("performance_name") or ""
        event.performer = result.get("performer") or ""
        event.ticket_info = result.get("ticket_info") or ""

        # 讲座信息
        event.lecture_topic = result.get("lecture_topic") or ""
        event.speaker_title = result.get("speaker_title") or ""
        event.lecture_series = result.get("lecture_series") or ""

        # 比赛信息
        event.competition_name = result.get("competition_name") or ""
        event.competition_type = result.get("competition_type") or ""
        event.deadline = result.get("deadline") or ""
        event.prize_info = result.get("prize_info") or ""

        # 报名信息
        event.registration_url = result.get("registration_url") or ""
        event.registration_deadline = result.get("registration_deadline") or ""
        event.participant_limit = result.get("participant_limit") or ""

    def _apply_time_fallback(self, article: Article, event: Event, ocr_text: str) -> None:
        # 先校验 Vision API 返回的时间合理性
        self._fix_time_sanity(event)

        candidate = TimeExtractor().extract(article, event, ocr_text)
        if not candidate:
            return
        if not event.start_time:
            event.start_time = candidate.start_time
        if not event.end_time and candidate.end_time:
            event.end_time = candidate.end_time

    def _apply_content_classification(self, article: Article, event: Event) -> None:
        decision = ContentClassifier().classify(article, event)
        event.is_event_related = decision.is_event_related
        event.relevance_reason = decision.reason
        event.activity_kind = decision.activity_kind
        event.activity_kind_reason = decision.activity_kind_reason
        if not decision.is_event_related:
            event.status = EventStatus.IGNORED_NON_EVENT

    @staticmethod
    def _fix_time_sanity(event: Event) -> None:
        """校验并修复 Vision API 返回的时间合理性。"""
        start = parse_datetime(event.start_time)
        end = parse_datetime(event.end_time)

        # end < start → 清除 end_time（让 time_extractor 重新抽取）
        if start and end and end < start:
            logger.warning(
                "Event %s: end_time %s < start_time %s, clearing end_time",
                event.event_id, event.end_time, event.start_time,
            )
            event.end_time = ""

    @staticmethod
    def _generate_dedup_key(event: Event) -> str:
        """基于 title + start_time + location 生成去重 key。

        对 title 做归一化（去空格、标点、大小写、常见前缀后缀），
        避免"同一活动不同措辞"绕过去重。
        """
        def _normalize(text: str) -> str:
            # 去除所有空白和常见标点
            text = re.sub(r"[\s　\-—–·｜|：:，,。.！!？?（）()\[\]【】{}「」『』《》<>]", "", text)
            # 去除常见前缀后缀（如"讲座："、"活动预告"、"通知"等）
            prefixes = ["讲座", "演出", "比赛", "活动", "通知", "预告", "招募", "征集", "报名"]
            for p in prefixes:
                if text.startswith(p):
                    text = text[len(p):]
            # 去除常见后缀
            suffixes = ["通知", "预告", "公告", "详情", "来了", "来了！", "等你来"]
            for s in suffixes:
                if text.endswith(s):
                    text = text[:-len(s)]
            return text.lower().strip()

        parts = [
            _normalize(event.title or ""),
            (event.start_time or "").strip(),
            _normalize(event.location or ""),
        ]
        raw = "::".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
