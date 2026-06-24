"""feishu_fields.py 单元测试。"""

from datetime import datetime
from unittest.mock import patch

import pytest

from app.models import Article, Event
from app.services.feishu_fields import (
    SELECT_OPTIONS,
    build_record_fields,
    checkbox,
    multi_select_texts,
    number,
    select_text,
    to_datetime_str,
    url_link,
)


# ---------------------------------------------------------------------------
# to_datetime_str
# ---------------------------------------------------------------------------

class TestToDatetimeStr:
    def test_none_returns_none(self):
        assert to_datetime_str(None) is None

    def test_empty_returns_none(self):
        assert to_datetime_str("") is None

    def test_full_format_passthrough(self):
        assert to_datetime_str("2026-06-24 14:00:00") == "2026-06-24 14:00:00"

    def test_date_only_adds_time(self):
        assert to_datetime_str("2026-06-24") == "2026-06-24 00:00:00"

    def test_timestamp_converts(self):
        # 2025-06-25 15:00:00 UTC+8 (1750834800)
        result = to_datetime_str("1750834800")
        assert result is not None
        assert "2025-06-25" in result

    def test_millisecond_timestamp_converts(self):
        result = to_datetime_str("1750834800000")
        assert result is not None
        assert "2025-06-25" in result


# ---------------------------------------------------------------------------
# select_text
# ---------------------------------------------------------------------------

class TestSelectText:
    def test_none_returns_none(self):
        assert select_text("一级分类", None) is None

    def test_empty_returns_none(self):
        assert select_text("一级分类", "") is None

    def test_valid_option_returns_value(self):
        assert select_text("一级分类", "讲座") == "讲座"

    def test_invalid_option_returns_none(self):
        assert select_text("一级分类", "无效选项") is None

    def test_unknown_field_passes_through(self):
        assert select_text("未知字段", "任意值") == "任意值"


# ---------------------------------------------------------------------------
# multi_select_texts
# ---------------------------------------------------------------------------

class TestMultiSelectTexts:
    def test_none_returns_none(self):
        assert multi_select_texts("标签", None) is None

    def test_empty_list_returns_none(self):
        assert multi_select_texts("标签", []) is None

    def test_valid_options_filtered(self):
        result = multi_select_texts("标签", ["免费", "线下"])
        assert result == ["免费", "线下"]

    def test_invalid_options_removed(self):
        result = multi_select_texts("标签", ["免费", "无效标签"])
        assert result == ["免费"]

    def test_all_invalid_returns_none(self):
        assert multi_select_texts("标签", ["无效1", "无效2"]) is None


# ---------------------------------------------------------------------------
# url_link / checkbox / number
# ---------------------------------------------------------------------------

class TestNormalizers:
    def test_url_link_none(self):
        assert url_link(None) is None

    def test_url_link_valid(self):
        assert url_link("https://example.com") == "https://example.com"

    def test_url_link_strips_whitespace(self):
        assert url_link("  https://example.com  ") == "https://example.com"

    def test_checkbox_none(self):
        assert checkbox(None) is None

    def test_checkbox_true(self):
        assert checkbox(True) is True

    def test_checkbox_false(self):
        assert checkbox(False) is False

    def test_number_none(self):
        assert number(None) is None

    def test_number_zero(self):
        assert number(0) is None

    def test_number_valid(self):
        assert number(0.856) == 0.86

    def test_number_rounds(self):
        assert number(1.234, digits=1) == 1.2


# ---------------------------------------------------------------------------
# build_record_fields
# ---------------------------------------------------------------------------

class TestBuildRecordFields:
    def _make_event(self, **kwargs) -> Event:
        """创建测试用 Event 对象。"""
        defaults = {
            "event_id": "test-001",
            "article_id": "art-001",
            "title": "测试讲座",
            "category_1": "讲座",
            "start_time": "2026-06-24 14:00:00",
            "end_time": "2026-06-24 16:00:00",
            "location": "学术报告厅",
            "status": "synced",
            "event_time_status": "upcoming",
            "retention_decision": "keep",
            "confidence": 0.85,
            "activity_kind": "lecture",
        }
        defaults.update(kwargs)
        event = Event(**defaults)
        # 创建关联的 Article
        article = Article(
            article_id="art-001",
            title="测试讲座",
            mp_name="测试公众号",
            pic_url="https://example.com/pic.jpg",
        )
        event.article = article
        return event

    def test_basic_fields(self):
        event = self._make_event()
        fields = build_record_fields(event)
        assert fields["标题"] == "测试讲座"
        assert fields["一级分类"] == "讲座"
        assert fields["活动地点"] == "学术报告厅"

    def test_empty_fields_skipped(self):
        event = self._make_event(location="", speaker="")
        fields = build_record_fields(event)
        assert "活动地点" not in fields
        assert "嘉宾" not in fields

    def test_select_fields_use_whitelist(self):
        event = self._make_event(category_1="讲座")
        fields = build_record_fields(event)
        assert fields["一级分类"] == "讲座"

    def test_select_invalid_option_skipped(self):
        event = self._make_event(category_1="无效分类")
        fields = build_record_fields(event)
        assert "一级分类" not in fields

    def test_datetime_fields_formatted(self):
        event = self._make_event(start_time="2026-06-24 14:00:00")
        fields = build_record_fields(event)
        assert fields["开始时间"] == "2026-06-24 14:00:00"

    def test_multi_select_tags(self):
        event = self._make_event(tags='["免费", "线下"]')
        fields = build_record_fields(event)
        assert fields["标签"] == ["免费", "线下"]

    def test_url_field(self):
        event = self._make_event(source_url="https://example.com")
        fields = build_record_fields(event)
        assert fields["原文链接"] == "https://example.com"

    def test_checkbox_field(self):
        event = self._make_event(user_keep=True)
        fields = build_record_fields(event)
        assert fields["用户置顶"] is True

    def test_number_field(self):
        event = self._make_event(confidence=0.856)
        fields = build_record_fields(event)
        assert fields["置信度"] == 0.86

    def test_article_pic_url_as_cover(self):
        event = self._make_event()
        fields = build_record_fields(event)
        assert fields["封面"] == "https://example.com/pic.jpg"

    def test_activity_kind_label(self):
        event = self._make_event(activity_kind="lecture")
        fields = build_record_fields(event)
        assert fields["活动类型"] == "讲座"

    def test_performance_fields(self):
        event = self._make_event(
            performance_type="音乐会",
            performance_name="贝多芬交响曲",
            performer="校乐团",
        )
        fields = build_record_fields(event)
        assert fields["演出类型"] == "音乐会"
        assert fields["演出作品"] == "贝多芬交响曲"
        assert fields["演出团体"] == "校乐团"

    def test_lecture_fields(self):
        event = self._make_event(
            lecture_topic="AI 前沿",
            speaker_title="教授",
            lecture_series="博雅讲堂",
        )
        fields = build_record_fields(event)
        assert fields["讲座主题"] == "AI 前沿"
        assert fields["主讲人头衔"] == "教授"
        assert fields["讲座系列"] == "博雅讲堂"
