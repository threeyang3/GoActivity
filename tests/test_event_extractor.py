from types import SimpleNamespace

from app.models import Article, Event
from app.services.article_service import ArticleService
from app.services.event_extractor import EventExtractor
from app.utils.ids import stable_id


def test_extract_multi_events_is_idempotent(monkeypatch, db) -> None:
    article = Article(
        article_id="article-multi",
        title="Campus Week",
        url="https://example.com/a",
        processed_markdown="A" * 800,
        raw_markdown="A" * 800,
    )
    primary_event = Event(
        event_id=stable_id("event", article.article_id),
        article_id=article.article_id,
        title=article.title,
        source_url=article.url,
    )
    db.add_all([article, primary_event])
    db.commit()

    monkeypatch.setattr("app.services.event_extractor.OCRExtractor.extract", lambda self, paths: "")
    monkeypatch.setattr(
        "app.services.event_extractor.VisionExtractor.analyze",
        lambda self, *args, **kwargs: {
            "events": [
                {"event_name": "Opening Talk", "is_event": True, "confidence": 0.9},
                {"event_name": "Workshop", "is_event": True, "confidence": 0.8},
                {"event_name": "Workshop", "is_event": True, "confidence": 0.7},
            ]
        },
    )
    monkeypatch.setattr("app.services.event_extractor.ExtractionValidator.validate", lambda self, event: None)
    monkeypatch.setattr("app.services.event_extractor.EventPolicyService.apply", lambda self, event: None)
    monkeypatch.setattr("app.services.event_extractor.TimeExtractor.extract", lambda self, article, event, ocr: None)
    monkeypatch.setattr(
        "app.services.time_extractor.LocationExtractor.extract",
        lambda self, article, event, ocr: "",
    )
    monkeypatch.setattr(
        "app.services.event_extractor.ContentClassifier.classify",
        lambda self, article, event: SimpleNamespace(
            is_event_related=True,
            reason="",
            activity_kind="general_event",
            activity_kind_reason="",
        ),
    )

    extractor = EventExtractor(db)
    extractor.extract(primary_event)
    db.commit()
    extractor.extract(primary_event)
    db.commit()

    events = db.query(Event).filter(Event.article_id == article.article_id).all()
    assert len(events) == 3
    primary = db.query(Event).filter(Event.event_id == primary_event.event_id).one()
    assert primary.title == "Opening Talk"
    assert sum(1 for event in events if event.title == "Workshop") == 2
    assert len({event.event_id for event in events}) == 3


def test_ensure_event_candidate_uses_primary_event(db) -> None:
    article = Article(
        article_id="article-primary",
        title="Primary",
        url="https://example.com/p",
        processed_markdown="body",
        raw_markdown="body",
    )
    primary_event = Event(
        event_id=stable_id("event", article.article_id),
        article_id=article.article_id,
        title="Primary",
    )
    extra_event = Event(
        event_id=stable_id("event", article.article_id, "1", "extra"),
        article_id=article.article_id,
        title="Extra",
    )
    db.add_all([article, primary_event, extra_event])
    db.commit()

    event = ArticleService(db)._ensure_event_candidate(article)

    assert event.event_id == primary_event.event_id
