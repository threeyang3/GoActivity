"""Vision/OCR 抽取结果后校验。

在 event_extractor._apply_result 之后调用，对 Vision API 返回的结构化数据做
防御性校验和修正，防止脏数据入库。
"""

import logging
from datetime import datetime

from app.models import Event
from app.services.event_policy import parse_datetime

logger = logging.getLogger(__name__)

# 允许的一级分类
VALID_CATEGORY_1 = {"讲座", "演出", "比赛", "招募", "展览", "工作坊", "分享会", "其他"}

# 合理的年份范围
YEAR_MIN = 2020
YEAR_MAX = 2035


class ExtractionValidator:
    """对 Vision API 抽取结果做后校验和修正。"""

    def validate(self, event: Event) -> list[str]:
        """校验并修正 event 上的字段。返回修正/警告信息列表。"""
        warnings: list[str] = []

        warnings.extend(self._validate_category(event))
        warnings.extend(self._validate_confidence(event))
        warnings.extend(self._validate_times(event))
        warnings.extend(self._validate_required_fields(event))

        for w in warnings:
            logger.warning("Extraction validation [event=%s]: %s", event.event_id, w)

        return warnings

    # ------------------------------------------------------------------

    def _validate_category(self, event: Event) -> list[str]:
        warnings = []
        if not event.category_1:
            return warnings
        if event.category_1 not in VALID_CATEGORY_1:
            warnings.append(f"category_1 '{event.category_1}' not in allowed values, resetting to '其他'")
            event.category_1 = "其他"
        return warnings

    def _validate_confidence(self, event: Event) -> list[str]:
        warnings = []
        if event.confidence is None:
            event.confidence = 0.0
            return warnings
        if event.confidence < 0 or event.confidence > 1:
            clamped = max(0.0, min(1.0, event.confidence))
            warnings.append(f"confidence {event.confidence} out of [0,1], clamped to {clamped}")
            event.confidence = clamped
        return warnings

    def _validate_times(self, event: Event) -> list[str]:
        warnings = []
        for field_name in ("start_time", "end_time"):
            value = getattr(event, field_name)
            if not value:
                continue
            parsed = parse_datetime(value)
            if not parsed:
                warnings.append(f"{field_name} '{value}' could not be parsed, clearing")
                setattr(event, field_name, "")
                continue
            if parsed.year < YEAR_MIN or parsed.year > YEAR_MAX:
                warnings.append(f"{field_name} year {parsed.year} out of range [{YEAR_MIN},{YEAR_MAX}], clearing")
                setattr(event, field_name, "")
        return warnings

    def _validate_required_fields(self, event: Event) -> list[str]:
        warnings = []
        # 如果标记为活动但没有标题，用 article_type_reason 或 summary 兜底
        if event.is_event_related and not (event.title or "").strip():
            fallback = (event.summary or event.activity_kind_reason or "").strip()[:80]
            if fallback:
                warnings.append(f"is_event=True but title empty, using fallback: {fallback}")
                event.title = fallback
            else:
                warnings.append("is_event=True but title and summary both empty")
        return warnings
