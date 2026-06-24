from datetime import timedelta

from app.db import SessionLocal, init_db
from app.models import Article, Event
from app.services.event_extractor import EventExtractor
from app.services.event_policy import now_shanghai
from app.services.time_extractor import TimeExtractor


def test_time_extractor_prefers_labeled_event_time() -> None:
    article = Article(
        article_id="article_time_1",
        title="毕业晚会通知",
        publish_time=str(int(now_shanghai().timestamp())),
        raw_markdown="节目征集截止时间 5月28日 晚23:59\n演出时间：2026年6月26日",
        processed_markdown="节目征集截止时间 5月28日 晚23:59\n演出时间：2026年6月26日",
    )
    event = Event(event_id="event_time_1", article_id=article.article_id, title=article.title)

    candidate = TimeExtractor().extract(article, event, "")

    assert candidate is not None
    assert candidate.start_time == "2026-06-26 00:00:00"


def test_time_extractor_handles_range_without_explicit_year() -> None:
    article = Article(
        article_id="article_time_2",
        title="训练营通知",
        publish_time=str(int(now_shanghai().timestamp())),
        raw_markdown="活动时间：6月20日 09:00-6月22日 18:00",
        processed_markdown="活动时间：6月20日 09:00-6月22日 18:00",
    )
    event = Event(event_id="event_time_2", article_id=article.article_id, title=article.title)

    candidate = TimeExtractor().extract(article, event, "")

    assert candidate is not None
    assert candidate.start_time.endswith("09:00:00")
    assert candidate.end_time.endswith("18:00:00")


def test_event_extractor_uses_time_fallback_when_vision_is_empty() -> None:
    """Vision 返回空 start_time 时，TimeExtractor 从 markdown 兜底提取时间。"""
    init_db()
    db = SessionLocal()
    article = Article(
        article_id="article_time_3",
        title="活动通知",
        publish_time=str(int((now_shanghai() - timedelta(hours=2)).timestamp())),
        raw_markdown="活动时间：6月30日 19:00",
        processed_markdown="活动时间：6月30日 19:00",
    )
    event = Event(event_id="event_time_3", article_id=article.article_id, title=article.title, status="pending")
    db.add(article)
    db.add(event)
    db.commit()
    try:
        # 验证 TimeExtractor 能从 markdown 提取时间
        extractor = EventExtractor(db)
        candidate = TimeExtractor().extract(article, event, "")
        assert candidate is not None
        assert candidate.start_time.endswith("19:00:00")
        assert candidate.start_time.startswith("2026-")

        # 验证 _apply_time_fallback 能正确设置 event.start_time
        event.start_time = ""
        extractor._apply_time_fallback(article, event, "")
        assert event.start_time.endswith("19:00:00")
        assert event.start_time.startswith("2026-")
    finally:
        db.query(Event).filter(Event.event_id == event.event_id).delete()
        db.query(Article).filter(Article.article_id == article.article_id).delete()
        db.commit()
        db.close()
