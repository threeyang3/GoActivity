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
        publish_time=str(int((now_shanghai() - timedelta(days=10)).timestamp())),
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


def test_feishu_adapter_updates_expired_event_status(monkeypatch) -> None:
    """过期事件应更新状态（upsert）而非删除，保留在飞书表格中。"""
    init_db()
    db = SessionLocal()
    article = Article(
        article_id="article_policy_2",
        title="活动通知",
        publish_time=str(int((now_shanghai() - timedelta(days=10)).timestamp())),
        raw_markdown="活动通知正文",
        processed_markdown="活动通知正文",
    )
    event = Event(
        event_id="event_policy_2",
        article_id=article.article_id,
        title=article.title,
        start_time=(now_shanghai() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
        feishu_record_id="rec_keep_me",
        status="synced",
    )
    db.add(article)
    db.add(event)
    db.commit()

    upserted_events: list[str] = []

    class FakeClient:
        def __init__(self, db):
            self.db = db
            self.settings = type("Settings", (), {"feishu_dry_run": False})()

        def upsert_event(self, event):
            upserted_events.append(event.event_id)
            return {"return_code": 0, "stdout": "upserted", "stderr": "", "dry_run": False, "record_id": event.feishu_record_id}

        def delete_event(self, event):
            raise AssertionError("Expired event should not be deleted")

    monkeypatch.setattr("app.services.feishu._build_client", lambda db: FakeClient(db))
    try:
        result = FeishuAdapter(db).sync_event(event)
        db.refresh(event)
        assert result["status"] == "expired_hidden"
        # 记录保留在飞书，feishu_record_id 不清空
        assert event.feishu_record_id == "rec_keep_me"
        # 确认调用了 upsert 而非 delete
        assert upserted_events == ["event_policy_2"]
    finally:
        db.query(Event).filter(Event.event_id == event.event_id).delete()
        db.query(Article).filter(Article.article_id == article.article_id).delete()
        db.commit()
        db.close()
