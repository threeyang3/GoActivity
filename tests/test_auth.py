"""API 鉴权测试。"""

from fastapi.testclient import TestClient

from app.main import app


def test_local_requests_do_not_need_token():
    """本机访问不需要 token。"""
    with TestClient(app) as client:
        # 本机 GET 请求不需要 auth
        resp = client.get("/health")
        assert resp.status_code == 200

        # 本机 GET /events 也不需要 auth（只读）
        resp = client.get("/events")
        assert resp.status_code == 200


def test_settings_schema_no_auth_needed():
    """GET /settings/schema 不需要鉴权（只读）。"""
    with TestClient(app) as client:
        resp = client.get("/settings/schema")
        assert resp.status_code == 200


def test_settings_get_no_auth_needed():
    """GET /settings 不需要鉴权（只读，密钥已掩码）。"""
    with TestClient(app) as client:
        resp = client.get("/settings")
        assert resp.status_code == 200


def test_health_no_auth_needed():
    """GET /health 不需要鉴权（只读）。"""
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
