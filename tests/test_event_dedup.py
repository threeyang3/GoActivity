"""事件去重逻辑测试。"""

from app.models import Event
from app.services.event_extractor import EventExtractor


class TestDedupKey:
    def test_same_title_same_key(self) -> None:
        e1 = Event(event_id="e1", title="人工智能前沿讲座", start_time="2026-07-01 19:00:00", location="报告厅")
        e2 = Event(event_id="e2", title="人工智能前沿讲座", start_time="2026-07-01 19:00:00", location="报告厅")
        assert EventExtractor._generate_dedup_key(e1) == EventExtractor._generate_dedup_key(e2)

    def test_different_title_different_key(self) -> None:
        e1 = Event(event_id="e1", title="讲座A", start_time="2026-07-01", location="")
        e2 = Event(event_id="e2", title="讲座B", start_time="2026-07-01", location="")
        assert EventExtractor._generate_dedup_key(e1) != EventExtractor._generate_dedup_key(e2)

    def test_different_time_different_key(self) -> None:
        e1 = Event(event_id="e1", title="同一讲座", start_time="2026-07-01 19:00:00", location="")
        e2 = Event(event_id="e2", title="同一讲座", start_time="2026-07-02 19:00:00", location="")
        assert EventExtractor._generate_dedup_key(e1) != EventExtractor._generate_dedup_key(e2)

    def test_normalization_removes_punctuation(self) -> None:
        e1 = Event(event_id="e1", title="讲座（第一期）", start_time="", location="")
        e2 = Event(event_id="e2", title="讲座 第一期", start_time="", location="")
        # 归一化后应该相同（去掉了括号和空格）
        assert EventExtractor._generate_dedup_key(e1) == EventExtractor._generate_dedup_key(e2)

    def test_empty_fields(self) -> None:
        e = Event(event_id="e1", title="", start_time="", location="")
        key = EventExtractor._generate_dedup_key(e)
        assert key  # 应该生成一个非空 key
        assert len(key) == 32

    def test_case_insensitive(self) -> None:
        e1 = Event(event_id="e1", title="AI Talk", start_time="", location="")
        e2 = Event(event_id="e2", title="ai talk", start_time="", location="")
        assert EventExtractor._generate_dedup_key(e1) == EventExtractor._generate_dedup_key(e2)
