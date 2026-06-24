from datetime import datetime, timedelta

from app.db import SessionLocal, init_db
from app.models import Article, Event
from app.services.event_policy import EventPolicyService, evaluate_article_gate, now_shanghai
from app.services.feishu import FeishuAdapter


def test_evaluate_article_gate_skips_old_announcement() -> None:
    publish_time = str(int((now_shanghai() - timedelta(days=31)).timestamp()))
    decision = evaluate_article_gate("活动通知", "这是一次活动通知", publish_time)
    assert decision.should_skip is True
    assert decision.retention_decision == "skip_older_than_30_days"


def test_evaluate_article_gate_keeps_recent_recap() -> None:
    publish_time = str(int((now_shanghai() - timedelta(days=45)).timestamp()))
    decision = evaluate_article_gate("活动回顾", "本次活动回顾", publish_time)
    assert decision.should_skip is False
    assert decision.article_type == "recap"


def test_event_policy_marks_past_announcement_for_removal() -> None:
    init_db()
    db = SessionLocal()
    article = Article(
        article_id="article_policy_1",
        title="活动通知",
        publish_time=str(int(now_shanghai().timestamp())),
        raw_markdown="活动通知正文",
        processed_markdown="活动通知正文",
    )
    event = Event(
        event_id="event_policy_1",
        article_id=article.article_id,
        title=article.title,
        start_time=(now_shanghai() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
        feishu_record_id="rec_xxx",
        status="synced",
    )
    db.add(article)
    db.add(event)
    db.commit()
    try:
        decision = EventPolicyService(db).apply(event)
        assert decision.should_remove_from_feishu is True
        assert decision.retention_decision == "drop_past_event"
        assert event.status == "expired_hidden"
    finally:
        db.query(Event).filter(Event.event_id == event.event_id).delete()
        db.query(Article).filter(Article.article_id == article.article_id).delete()
        db.commit()
        db.close()


def test_feishu_adapter_deletes_expired_event(monkeypatch) -> None:
    init_db()
    db = SessionLocal()
    article = Article(
        article_id="article_policy_2",
        title="活动通知",
        publish_time=str(int(now_shanghai().timestamp())),
        raw_markdown="活动通知正文",
        processed_markdown="活动通知正文",
    )
    event = Event(
        event_id="event_policy_2",
        article_id=article.article_id,
        title=article.title,
        start_time=(now_shanghai() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
        feishu_record_id="rec_delete_me",
        status="synced",
    )
    db.add(article)
    db.add(event)
    db.commit()

    class FakeClient:
        def __init__(self, db):
            self.db = db
            self.settings = type("Settings", (), {"feishu_dry_run": False})()

        def upsert_event(self, event):
            raise AssertionError("Expired event should not upsert")

        def delete_event(self, event):
            return {"return_code": 0, "stdout": "deleted", "stderr": "", "dry_run": False, "record_id": ""}

    monkeypatch.setattr("app.services.feishu._build_client", lambda db: FakeClient(db))
    try:
        result = FeishuAdapter(db).sync_event(event)
        db.refresh(event)
        assert result["status"] == "expired_hidden"
        assert event.feishu_record_id == ""
    finally:
        db.query(Event).filter(Event.event_id == event.event_id).delete()
        db.query(Article).filter(Article.article_id == article.article_id).delete()
        db.commit()
        db.close()
