from datetime import timedelta
import uuid

import pytest

from app.exceptions import FeishuError
from app.models import AppSetting, Article, Event
from app.services.automation_guard import AutomationGuardService
from app.services.auto_sync import AutoSyncService
from app.services.article_service import ArticleService
from app.services.feishu import FeishuAdapter
from app.services.event_policy import ArticleGateDecision
from app.utils.constants import EventStatus
from app.utils.time import utcnow


def test_feishu_failure_uses_exponential_backoff(db):
    event = Event(event_id="retry-backoff", article_id="article-retry", status=EventStatus.EXTRACTED)
    adapter = FeishuAdapter.__new__(FeishuAdapter)
    adapter.db = db
    adapter.client = type("Client", (), {"settings": type("Settings", (), {"feishu_sync_retry_base_minutes": 15})()})()

    before = utcnow()
    adapter._mark_sync_failure(event, "network error")
    first_retry = event.feishu_next_retry_at
    adapter._mark_sync_failure(event, "network error again")

    assert event.feishu_retry_count == 2
    assert first_retry >= before + timedelta(minutes=15)
    assert event.feishu_next_retry_at >= before + timedelta(minutes=30)
    assert event.feishu_last_error == "network error again"


def test_only_due_failed_sync_events_are_retried(monkeypatch, db):
    db.add_all([
        Article(article_id="article-due", mp_name="重试来源"),
        Article(article_id="article-later", mp_name="重试来源"),
    ])
    db.flush()
    due = Event(
        event_id="retry-due",
        article_id="article-due",
        status=EventStatus.FAILED_SYNC,
        feishu_retry_count=1,
        feishu_next_retry_at=utcnow() - timedelta(minutes=1),
    )
    later = Event(
        event_id="retry-later",
        article_id="article-later",
        status=EventStatus.FAILED_SYNC,
        feishu_retry_count=1,
        feishu_next_retry_at=utcnow() + timedelta(hours=1),
    )
    db.add_all([due, later])
    db.commit()
    service = AutoSyncService()
    captured = []
    monkeypatch.setattr(service, "_sync_event_ids_parallel", lambda ids, **kwargs: captured.extend(ids) or len(ids))

    assert service._retry_failed_syncs(db) == 1
    assert captured == ["retry-due"]


def test_account_health_marks_stale_sources(db):
    db.add_all([
        Article(article_id="fresh-source", mp_name="新鲜公众号", created_at=utcnow()),
        Article(article_id="stale-source", mp_name="停更公众号", created_at=utcnow() - timedelta(hours=48)),
    ])
    db.commit()
    service = AutomationGuardService(db)
    service.settings.account_stale_hours = 36

    health = {item["mp_name"]: item for item in service.account_health()}

    assert health["新鲜公众号"]["status"] == "ok"
    assert health["停更公众号"]["status"] == "stale"


def test_account_health_includes_remote_accounts_without_local_articles(monkeypatch, db):
    service = AutomationGuardService(db)
    monkeypatch.setattr(
        service,
        "_list_remote_accounts",
        lambda: [{"mp_id": "mp-new", "mp_name": "尚未采集公众号"}],
    )

    health = [
        item for item in service.account_health(include_remote=True)
        if item["mp_name"] == "尚未采集公众号"
    ]

    assert health == [{
        "mp_name": "尚未采集公众号",
        "mp_id": "mp-new",
        "remote_subscribed": True,
        "article_count": 0,
        "event_count": 0,
        "latest_publish_time": None,
        "latest_publish_epoch": None,
        "latest_ingested_at": None,
        "stale_hours": None,
        "stale_days": None,
        "latest_publication_age_hours": None,
        "sla_hours": service.settings.account_stale_hours,
        "status": "stale",
        "health_status": "never_collected",
        "remote_error": None,
    }]


def test_filtered_article_is_persisted_and_not_reprocessed(monkeypatch, db):
    payload = {
        "id": "filtered-article",
        "title": "很久以前的公告",
        "content": "历史内容",
        "publish_time": "2020-01-01 09:00:00",
        "mp_name": "历史来源",
        "url": "https://example.com/filtered",
    }
    monkeypatch.setattr(
        "app.services.article_service.evaluate_article_gate",
        lambda *_: ArticleGateDecision("announcement", "历史公告", "skip_older_than_60_days", True),
    )
    service = ArticleService(db)

    result = service.ingest_we_mp_rss_payload(payload)

    assert result["article_skipped"] is True
    assert db.query(Article).filter(Article.article_id == "filtered-article").one().ingestion_status == "filtered"

    class FakeClient:
        def fetch_articles(self, **kwargs):
            return [payload] if kwargs.get("offset", 0) == 0 else []

    monkeypatch.setattr("app.services.article_service.WeMpRssClient", FakeClient)
    assert service.fetch_candidates(limit=1) == []


def test_parallel_ingest_returns_failures_in_result(monkeypatch, db):
    service = ArticleService(db)

    def fail(_payload):
        raise ValueError("vision unavailable")

    monkeypatch.setattr(service, "ingest_we_mp_rss_payload", fail)
    result = service.ingest_candidates_parallel([{"id": "a"}, {"id": "b"}])

    assert len(result) == 2
    assert all(item["ingest_failed"] for item in result)
    assert {item["article_id"] for item in result} == {"a", "b"}


def test_reconcile_reports_missing_and_drift_without_writing(monkeypatch, db):
    article = Article(article_id="reconcile-article", mp_name="测试公众号")
    missing = Event(
        event_id="event-missing-remote",
        article_id=article.article_id,
        title="缺失活动",
        feishu_record_id="rec-missing",
        status=EventStatus.SYNCED,
    )
    drift = Event(
        event_id="event-drift-remote",
        article_id=article.article_id,
        title="正确标题",
        feishu_record_id="rec-drift",
        status=EventStatus.SYNCED,
    )
    db.add_all([article, missing, drift])
    db.commit()
    service = AutomationGuardService(db)
    service.settings.feishu_reconcile_max_missing_ratio = 0.5
    monkeypatch.setattr(
        service,
        "_list_feishu_records",
        lambda: [{"record_id": "rec-drift", "fields": {"标题": "错误标题"}}],
    )

    result = service.reconcile_feishu(repair_missing=False)

    assert "event-missing-remote" in result["missing_record_ids"]
    assert "event-drift-remote" in result["field_drift_event_ids"]
    assert result["repaired_event_ids"] == []
    assert result["matched_records"] == 1
    assert result["safe_to_repair"] is False
    assert missing.feishu_record_id == "rec-missing"

    confirmed = service.reconcile_feishu(repair_missing=False)
    assert confirmed["snapshot_confirmed"] is True


def test_reconcile_ignores_terminal_events(monkeypatch, db):
    article = Article(article_id="reconcile-terminal-article", mp_name="测试公众号")
    event = Event(
        event_id="reconcile-terminal-event",
        article_id=article.article_id,
        feishu_record_id="rec-terminal",
        status=EventStatus.EXPIRED_HIDDEN,
    )
    db.add_all([article, event])
    db.commit()
    service = AutomationGuardService(db)
    monkeypatch.setattr(
        service,
        "_list_feishu_records",
        lambda: [{"record_id": "unrelated-record", "fields": {"标题": "其他活动"}}],
    )

    result = service.reconcile_feishu(repair_missing=False)

    assert "reconcile-terminal-event" not in result["missing_record_ids"]
    assert result["skipped_terminal_records"] >= 1


def test_alert_cooldown_is_persisted(db):
    service = AutomationGuardService(db)
    fingerprint = f"test-{uuid.uuid4().hex}"
    db.add(AppSetting(key=f"alert:{fingerprint}", value=utcnow().isoformat(), category="automation_internal"))
    db.commit()

    assert service._in_cooldown(fingerprint) is True


def test_feishu_reconcile_reads_all_pages(monkeypatch, db):
    service = AutomationGuardService(db)
    monkeypatch.setattr("app.services.automation_guard.build_lark_cli_command", lambda path: ["lark-cli"])
    calls = []

    def fake_run(command, timeout):
        offset = int(command[command.index("--offset") + 1])
        calls.append(offset)
        count = 200 if offset == 0 else 1
        items = [{"record_id": f"rec-{offset + index}", "fields": {"标题": "活动"}} for index in range(count)]
        return {"return_code": 0, "stdout": "", "stderr": "", "data": {"data": {"items": items}}}

    monkeypatch.setattr("app.services.automation_guard.run_cli_command", fake_run)

    records = service._list_feishu_records()

    assert len(records) == 201
    assert calls == [0, 200]


def test_feishu_reconcile_parses_lark_cli_field_matrix(monkeypatch, db):
    service = AutomationGuardService(db)
    monkeypatch.setattr("app.services.automation_guard.build_lark_cli_command", lambda path: ["lark-cli"])
    monkeypatch.setattr(
        "app.services.automation_guard.run_cli_command",
        lambda command, timeout: {
            "return_code": 0,
            "stdout": "",
            "stderr": "",
            "data": {
                "ok": True,
                "data": {
                    "data": [["活动 A", [{"name": "poster.jpg"}]]],
                    "fields": ["标题", "海报附件"],
                    "record_id_list": ["rec-a"],
                    "has_more": False,
                },
            },
        },
    )

    assert service._list_feishu_records() == [
        {"record_id": "rec-a", "fields": {"标题": "活动 A", "海报附件": [{"name": "poster.jpg"}]}}
    ]


def test_reconcile_reports_remote_only_records(monkeypatch, db):
    article = Article(article_id="reconcile-orphan-article", mp_name="测试公众号")
    event = Event(
        event_id="reconcile-orphan-event",
        article_id=article.article_id,
        feishu_record_id="rec-local",
        status=EventStatus.SYNCED,
    )
    db.add_all([article, event])
    db.commit()
    service = AutomationGuardService(db)
    monkeypatch.setattr(
        service,
        "_list_feishu_records",
        lambda: [
            {"record_id": "rec-local", "fields": {"标题": "活动"}},
            {"record_id": "rec-orphan", "fields": {"标题": "远端孤儿"}},
        ],
    )

    result = service.reconcile_feishu()

    assert result["remote_only_record_ids"] == ["rec-orphan"]


def test_remote_accounts_use_supported_page_size(monkeypatch, db):
    service = AutomationGuardService(db)
    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"list": [{"mp_id": "mp", "mp_name": "公众号"}]}}

    def fake_get(_url, params, **_kwargs):
        calls.append(params)
        return Response()

    monkeypatch.setattr("app.services.automation_guard.requests.get", fake_get)

    service._list_remote_accounts()

    assert calls[0]["limit"] == 100


def test_reconcile_fails_closed_when_remote_records_are_empty(monkeypatch, db):
    article = Article(article_id="reconcile-empty-article", mp_name="测试公众号")
    event = Event(
        event_id="reconcile-empty-event",
        article_id=article.article_id,
        feishu_record_id="rec-local",
        status=EventStatus.SYNCED,
    )
    db.add_all([article, event])
    db.commit()
    service = AutomationGuardService(db)
    monkeypatch.setattr(service, "_list_feishu_records", lambda: [])

    with pytest.raises(FeishuError, match="停止对账"):
        service.reconcile_feishu(repair_missing=False)
