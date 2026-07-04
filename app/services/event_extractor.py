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
        self._apply_location_extraction(article, event, ocr_text)
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

    def _apply_location_extraction(self, article: Article, event: Event, ocr_text: str) -> None:
        """从文章内容中提取地点信息。"""
        from app.services.time_extractor import LocationExtractor
        location = LocationExtractor().extract(article, event, ocr_text)
        if location:
            event.location = location

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
        parts = [
            EventExtractor._normalize_title(event.title or ""),
            (event.start_time or "").strip(),
            EventExtractor._normalize_title(event.location or ""),
        ]
        raw = "::".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _generate_core_key(event: Event) -> str:
        """基于归一化标题生成宽松去重 key（不依赖时间/地点）。

        用于匹配同一活动的渐进式推文（如"开售预告"→"开售"→"节目单"）。
        只用标题核心部分，适合同公众号内的模糊匹配。
        """
        normalized = EventExtractor._normalize_title(event.title or "")
        if not normalized or len(normalized) < 4:
            return ""
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _normalize_title(text: str) -> str:
        """标题归一化：去标点、前缀后缀、阶段关键词、日期地点前缀。

        注意保留序号（第X讲）和尾部日期（2026.6.8），用于区分不同活动。
        """
        # 去除常见标点（保留中文括号和数字相关的 .）
        text = re.sub(r"[\s　\-—–·｜|：:，,。.！!？?（）()\[\]【】{}「」『』《》<>]", "", text)

        # 去除日期地点前缀，如 "7.13【李莹厅】"、"8.6【观众厅】"
        text = re.sub(r"^\d{1,2}\.\d{1,2}【[^】]*】", "", text)
        text = re.sub(r"^\d{1,2}月\d{1,2}[日号]【[^】]*】", "", text)

        # 去除阶段关键词（开售/预告/售票等）
        stage_keywords = [
            "开售预告", "开售", "预售", "售票", "抢票", "节目单",
            "活动预告", "活动通知", "详情预告",
        ]
        for kw in stage_keywords:
            text = text.replace(kw, "")

        # 去除常见前缀
        prefixes = ["讲座", "演出", "比赛", "活动", "通知", "预告", "招募", "征集", "报名"]
        for p in prefixes:
            if text.startswith(p):
                text = text[len(p):]

        # 去除常见后缀（但保留"回顾"等可能区分不同文章的词）
        suffixes = ["通知", "公告", "详情", "来了", "来了！", "等你来", "等你"]
        for s in suffixes:
            if text.endswith(s):
                text = text[:-len(s)]

        return text.lower().strip()

    @staticmethod
    def is_same_event(event1_title: str, event1_start: str, event1_location: str,
                      event2_title: str, event2_start: str, event2_location: str) -> bool:
        """判断两个事件是否为同一活动。

        综合匹配策略：
        1. 标题归一化后完全相同 → 同一活动
        2. 标题子串/高相似度 → 同一活动
        3. 时间相同 + 地点相同 + 标题有公共关键词(>=4字) → 同一活动
        4. 时间相同 + 标题高相似度(>=75%) → 同一活动
        """
        n1 = EventExtractor._normalize_title(event1_title or "")
        n2 = EventExtractor._normalize_title(event2_title or "")
        if not n1 or not n2 or len(n1) < 4 or len(n2) < 4:
            return False

        # 1. 完全相同
        if n1 == n2:
            return True

        # 2. 标题子串匹配（要求短标题>=12字，避免"人工智能前沿讲座"匹配"人工智能前沿讲座报名通知"）
        shorter, longer = (n1, n2) if len(n1) <= len(n2) else (n2, n1)
        if len(shorter) >= 12 and shorter in longer:
            return True

        # 标题相似度
        lcs = EventExtractor._lcs_length(n1, n2)
        title_ratio = lcs / min(len(n1), len(n2)) if min(len(n1), len(n2)) > 0 else 0

        # 3. 时间+地点+关键词联合匹配
        time_match = EventExtractor._is_time_match(event1_start, event2_start)
        loc_match = EventExtractor._is_location_match(event1_location, event2_location)

        if time_match and loc_match:
            # 时间地点都相同，标题有公共部分(>=4字)即可
            if lcs >= 4:
                return True

        # 4. 时间相同 + 标题高相似度
        if time_match and title_ratio >= 0.75 and lcs >= 8:
            return True

        # 5. 纯标题高相似度（无时间地点辅助时要求更严格）
        if title_ratio >= 0.85 and lcs >= 10:
            return True

        return False

    @staticmethod
    def is_same_event_title(title1: str, title2: str) -> bool:
        """仅基于标题判断是否为同一活动（兼容旧调用）。"""
        return EventExtractor.is_same_event(
            title1, "", "", title2, "", ""
        )

    @staticmethod
    def _is_time_match(time1: str, time2: str) -> bool:
        """判断两个时间是否匹配。"""
        if not time1 or not time2:
            return False
        t1 = (time1 or "").strip()[:16]  # 精确到分钟
        t2 = (time2 or "").strip()[:16]
        return t1 == t2

    @staticmethod
    def _is_location_match(loc1: str, loc2: str) -> bool:
        """判断两个地点是否匹配。"""
        if not loc1 or not loc2:
            return False
        l1 = re.sub(r"[\s　\-—–·｜|：:，,。]", "", (loc1 or "").strip()).lower()
        l2 = re.sub(r"[\s　\-—–·｜|：:，,。]", "", (loc2 or "").strip()).lower()
        if not l1 or not l2:
            return False
        # 完全相同或一个是另一个的子串
        if l1 == l2:
            return True
        if len(l1) >= 3 and len(l2) >= 3:
            if l1 in l2 or l2 in l1:
                return True
        return False

    @staticmethod
    def _lcs_length(s1: str, s2: str) -> int:
        """计算两个字符串的最长公共子串长度。"""
        m, n = len(s1), len(s2)
        dp = [0] * (n + 1)
        max_len = 0
        for i in range(1, m + 1):
            prev = 0
            for j in range(1, n + 1):
                temp = dp[j]
                if s1[i - 1] == s2[j - 1]:
                    dp[j] = prev + 1
                    max_len = max(max_len, dp[j])
                else:
                    dp[j] = 0
                prev = temp
        return max_len
