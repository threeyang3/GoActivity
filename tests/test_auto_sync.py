"""自动同步服务测试。"""

import pytest
from apscheduler.triggers.cron import CronTrigger

from app.services.auto_sync import AutoSyncService
from app.utils.cron import parse_cron


class TestParseCron:
    def test_five_field_cron(self) -> None:
        trigger = parse_cron("0 * * * *")
        assert isinstance(trigger, CronTrigger)

    def test_two_field_cron(self) -> None:
        trigger = parse_cron("30 9")
        assert isinstance(trigger, CronTrigger)

    def test_three_field_cron(self) -> None:
        trigger = parse_cron("0 9 *")
        assert isinstance(trigger, CronTrigger)

    def test_invalid_cron_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_cron("bad")

    def test_single_field_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_cron("0")


def test_trigger_collection_polls_remote_candidates(monkeypatch, db) -> None:
    service = AutoSyncService()
    calls = {"fetch": 0}

    class FakeClient:
        def list_message_tasks(self):
            return [{"id": "task-1", "name": "Daily"}]

        def trigger_message_task(self, task_id: str):
            return {"count": 1}

    class FakeArticleService:
        def __init__(self, _db) -> None:
            pass

        def fetch_candidates(self, limit: int, include_no_content: bool):
            calls["fetch"] += 1
            if calls["fetch"] < 2:
                return []
            return [{"article_id": "new-1"}]

    monkeypatch.setattr("app.adapters.we_mp_rss.WeMpRssClient", FakeClient)
    monkeypatch.setattr("app.services.article_service.ArticleService", FakeArticleService)
    monkeypatch.setattr("app.services.auto_sync.ArticleService", FakeArticleService)
    monkeypatch.setattr("app.services.auto_sync._time.sleep", lambda _: None)

    candidates = service._trigger_we_mp_rss_collection(db)

    assert candidates == [{"article_id": "new-1"}]
    assert calls["fetch"] == 2
