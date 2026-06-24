import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_we_mp_rss_webhook_ingests_article_and_event() -> None:
    payload = json.loads(Path(__file__).resolve().parent.parent.joinpath("docs", "mock-webhook-payload.json").read_text(encoding="utf-8"))
    with TestClient(app) as client:
        response = client.post("/webhooks/we-mp-rss", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["article_id"] == "demo-001"
    assert body["event_id"].startswith("event_")
    assert body["status"] in {"extracted", "needs_image_retry", "pending_ai"}


def test_we_mp_rss_webhook_filters_non_event_promo() -> None:
    payload = {
        "id": "demo-non-event-001",
        "title": "知行并进强本领 挺膺担当建新功",
        "account_name": "北大团委",
        "publish_time": "2026-06-15 10:00:00",
        "url": "https://example.com/non-event",
        "content": "北大青年以青春之名在祖国大地之上书写时代答卷，弘扬时代新声。",
        "content_html": "<p>北大青年以青春之名在祖国大地之上书写时代答卷，弘扬时代新声。</p>",
    }
    with TestClient(app) as client:
        response = client.post("/webhooks/we-mp-rss", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ignored_non_event"
