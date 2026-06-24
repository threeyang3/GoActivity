from fastapi.testclient import TestClient

from app.main import app


def test_diagnostics_config_returns_expected_checks() -> None:
    with TestClient(app) as client:
        response = client.get("/diagnostics/config")

    assert response.status_code == 200
    body = response.json()
    keys = {item["key"] for item in body["checks"]}
    assert "WE_MP_RSS_ACCESS_KEY" in keys
    assert "VISION_API_KEY" in keys
    assert ".env" in keys
