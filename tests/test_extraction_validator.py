"""抽取结果校验器测试。"""

from app.models import Event
from app.services.extraction_validator import ExtractionValidator, VALID_CATEGORY_1


def _make_event(**kwargs) -> Event:
    defaults = {
        "event_id": "test_val_001",
        "article_id": "art_001",
        "category_1": "其他",
        "confidence": 0.0,
        "title": "",
        "start_time": "",
        "end_time": "",
        "is_event_related": True,
    }
    defaults.update(kwargs)
    event = Event(**defaults)
    return event


class TestExtractionValidator:
    def setup_method(self) -> None:
        self.validator = ExtractionValidator()

    def test_valid_category_passes(self) -> None:
        event = _make_event(category_1="讲座")
        warnings = self.validator.validate(event)
        assert not any("category_1" in w for w in warnings)
        assert event.category_1 == "讲座"

    def test_invalid_category_reset(self) -> None:
        event = _make_event(category_1="不存在的分类")
        warnings = self.validator.validate(event)
        assert any("category_1" in w for w in warnings)
        assert event.category_1 == "其他"

    def test_confidence_out_of_range_clamped(self) -> None:
        event = _make_event(confidence=1.5)
        warnings = self.validator.validate(event)
        assert any("confidence" in w for w in warnings)
        assert event.confidence == 1.0

    def test_negative_confidence_clamped(self) -> None:
        event = _make_event(confidence=-0.1)
        warnings = self.validator.validate(event)
        assert event.confidence == 0.0

    def test_invalid_time_cleared(self) -> None:
        event = _make_event(start_time="not a date")
        warnings = self.validator.validate(event)
        assert any("start_time" in w for w in warnings)
        assert event.start_time == ""

    def test_unreasonable_year_cleared(self) -> None:
        event = _make_event(start_time="1970-01-01 00:00:00")
        warnings = self.validator.validate(event)
        assert any("year" in w for w in warnings)
        assert event.start_time == ""

    def test_valid_time_passes(self) -> None:
        event = _make_event(start_time="2026-07-01 19:00:00")
        warnings = self.validator.validate(event)
        assert not any("start_time" in w for w in warnings)
        assert event.start_time == "2026-07-01 19:00:00"

    def test_empty_title_with_is_event(self) -> None:
        event = _make_event(is_event_related=True, title="", summary="这是一个活动摘要")
        warnings = self.validator.validate(event)
        assert any("title empty" in w for w in warnings)
        assert event.title == "这是一个活动摘要"

    def test_all_valid_no_warnings(self) -> None:
        event = _make_event(
            category_1="讲座",
            confidence=0.8,
            start_time="2026-07-01 19:00:00",
            title="测试讲座",
            is_event_related=True,
        )
        warnings = self.validator.validate(event)
        assert len(warnings) == 0
