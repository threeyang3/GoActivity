from fastapi.testclient import TestClient

from app.main import app


def test_remote_webhook_requires_configured_token(monkeypatch):
    monkeypatch.setattr("app.routes.webhooks._is_local_request", lambda request: False)
    with TestClient(app) as client:
        response = client.post("/webhooks/we-mp-rss", json={"title": "untrusted"})

    assert response.status_code in {401, 503}
