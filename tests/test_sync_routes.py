from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def test_sync_we_mp_rss_articles_returns_400_without_credentials() -> None:
    settings = get_settings()
    original_access_key = settings.we_mp_rss_access_key
    original_secret_key = settings.we_mp_rss_secret_key
    try:
        settings.we_mp_rss_access_key = ""
        settings.we_mp_rss_secret_key = ""
        with TestClient(app) as client:
            response = client.post("/sync/we-mp-rss/articles")
    finally:
        settings.we_mp_rss_access_key = original_access_key
        settings.we_mp_rss_secret_key = original_secret_key

    assert response.status_code == 400
    assert "WE_MP_RSS_ACCESS_KEY" in response.json()["detail"]
