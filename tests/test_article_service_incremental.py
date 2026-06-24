from app.db import SessionLocal, init_db
from app.models import Article
from app.services.article_service import ArticleService


class _IncrementalFakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls: list[tuple[int, int]] = []
        self._all_articles = [a for page in pages for a in page]

    def fetch_articles(self, limit: int = 20, offset: int = 0, has_content: bool = True):
        self.calls.append((limit, offset))
        return self._all_articles[offset:offset + limit]

    def fetch_article_detail(self, article_id: str):
        return {"id": article_id, "content_html": "<p>detail</p>"}


def test_incremental_sync_skips_existing_by_id(monkeypatch) -> None:
    """已入库的 article_id 被跳过，新文章被摄入。"""
    init_db()
    db = SessionLocal()
    existing = Article(
        article_id="existing-a-110",
        mp_name="账号A",
        title="已有文章",
        publish_time="110",
        url="https://example.com/existing",
        raw_markdown="x",
    )
    db.add(existing)
    db.commit()

    fake_client = _IncrementalFakeClient(
        [
            [
                {"id": "new-a-120", "account_name": "账号A", "publish_time": "120", "title": "新文章", "content_html": "<p>a</p>"},
                {"id": "existing-a-110", "account_name": "账号A", "publish_time": "110", "title": "旧文章", "content_html": "<p>b</p>"},
            ],
            [
                {"id": "older-a-100", "account_name": "账号A", "publish_time": "100", "title": "更旧文章", "content_html": "<p>c</p>"},
            ],
        ]
    )
    monkeypatch.setattr("app.services.article_service.WeMpRssClient", lambda: fake_client)

    service = ArticleService(db)
    monkeypatch.setattr(service, "ingest_we_mp_rss_payload", lambda payload: {"article_id": payload["id"], "event_id": "", "image_count": 0, "status": "ok"})
    try:
        results = service.sync_from_we_mp_rss_articles(limit=2, offset=0)
        ids = [item["article_id"] for item in results]
        # existing-a-110 被跳过，new-a-120 和 older-a-100 被摄入
        assert "existing-a-110" not in ids
        assert "new-a-120" in ids
        assert len(results) == 2
    finally:
        db.query(Article).filter(Article.article_id == existing.article_id).delete()
        db.commit()
        db.close()


def test_incremental_sync_backfills_old_articles(monkeypatch) -> None:
    """旧文章也能被同步（不再按 publish_time 跳过）。"""
    init_db()
    db = SessionLocal()
    existing = Article(
        article_id="existing-a-110-b",
        mp_name="账号A",
        title="已有文章",
        publish_time="110",
        url="https://example.com/existing-b",
        raw_markdown="x",
    )
    db.add(existing)
    db.commit()

    fake_client = _IncrementalFakeClient(
        [
            [
                {"id": "new-b-60", "account_name": "账号B", "publish_time": "60", "title": "B1", "content_html": "<p>a</p>"},
                {"id": "old-a-100-b", "account_name": "账号A", "publish_time": "100", "title": "A old", "content_html": "<p>b</p>"},
            ],
            [
                {"id": "new-b-50", "account_name": "账号B", "publish_time": "50", "title": "B2", "content_html": "<p>c</p>"},
            ],
        ]
    )
    monkeypatch.setattr("app.services.article_service.WeMpRssClient", lambda: fake_client)

    service = ArticleService(db)
    monkeypatch.setattr(service, "ingest_we_mp_rss_payload", lambda payload: {"article_id": payload["id"], "event_id": "", "image_count": 0, "status": "ok"})
    try:
        results = service.sync_from_we_mp_rss_articles(limit=10, offset=0)
        ids = [item["article_id"] for item in results]
        # existing-a-110-b 被跳过，其他 3 篇都被摄入
        assert "existing-a-110-b" not in ids
        assert len(results) == 3
        assert "new-b-60" in ids
        assert "old-a-100-b" in ids
        assert "new-b-50" in ids
    finally:
        db.query(Article).filter(Article.article_id == existing.article_id).delete()
        db.commit()
        db.close()
