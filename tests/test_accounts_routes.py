"""公众号管理代理路由测试。"""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def _with_creds(access_key="test-ak", secret_key="test-sk"):
    """临时设置凭据的上下文管理器。"""
    settings = get_settings()
    orig_ak = settings.we_mp_rss_access_key
    orig_sk = settings.we_mp_rss_secret_key
    settings.we_mp_rss_access_key = access_key
    settings.we_mp_rss_secret_key = secret_key
    return settings, orig_ak, orig_sk


def _restore_creds(settings, orig_ak, orig_sk):
    settings.we_mp_rss_access_key = orig_ak
    settings.we_mp_rss_secret_key = orig_sk


def test_list_accounts_requires_credentials() -> None:
    """未配置凭据时返回 500。"""
    settings = get_settings()
    orig_ak = settings.we_mp_rss_access_key
    orig_sk = settings.we_mp_rss_secret_key
    try:
        settings.we_mp_rss_access_key = ""
        settings.we_mp_rss_secret_key = ""
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/accounts")
    finally:
        settings.we_mp_rss_access_key = orig_ak
        settings.we_mp_rss_secret_key = orig_sk

    # _auth_headers() raises HTTPException(500), _proxy_error 透传
    assert resp.status_code == 500
    assert "WE_MP_RSS_ACCESS_KEY" in resp.json()["detail"]


def test_list_accounts_proxies_to_we_mp_rss(monkeypatch) -> None:
    """正常请求转发到 we-mp-rss 并返回结果。"""
    settings, orig_ak, orig_sk = _with_creds()

    captured = {}

    def mock_get(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs.get("params", {})
        captured["headers"] = kwargs.get("headers", {})
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"data": {"list": [{"id": "mp1", "mp_name": "测试号"}], "total": 1}},
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr("app.routes.accounts.http_requests.get", mock_get)

    try:
        with TestClient(app) as client:
            resp = client.get("/accounts?limit=10&offset=0")
    finally:
        _restore_creds(settings, orig_ak, orig_sk)

    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["list"][0]["mp_name"] == "测试号"
    assert "test-ak" in captured["headers"]["Authorization"]


def test_search_accounts_passes_keyword(monkeypatch) -> None:
    """搜索关键词正确传递。"""
    settings, orig_ak, orig_sk = _with_creds()
    captured = {}

    def mock_get(url, **kwargs):
        captured["url"] = url
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"data": {"list": [{"mp_name": "搜索结果"}], "total": 1}},
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr("app.routes.accounts.http_requests.get", mock_get)

    try:
        with TestClient(app) as client:
            resp = client.get("/accounts/search/校园活动")
    finally:
        _restore_creds(settings, orig_ak, orig_sk)

    assert resp.status_code == 200
    assert "校园活动" in captured["url"]


def test_add_account_posts_body(monkeypatch) -> None:
    """添加公众号时 body 正确转发。"""
    settings, orig_ak, orig_sk = _with_creds()
    captured = {}

    def mock_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json", {})
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"data": {"id": "mp-new", "mp_name": "新公众号"}},
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr("app.routes.accounts.http_requests.post", mock_post)

    try:
        with TestClient(app) as client:
            resp = client.post("/accounts", json={
                "mp_name": "新公众号",
                "mp_id": "abc123",
                "avatar": "https://example.com/avatar.png",
            })
    finally:
        _restore_creds(settings, orig_ak, orig_sk)

    assert resp.status_code == 200
    assert captured["json"]["mp_name"] == "新公众号"


def test_delete_account_sends_delete(monkeypatch) -> None:
    """删除请求正确发送。"""
    settings, orig_ak, orig_sk = _with_creds()
    captured = {}

    def mock_delete(url, **kwargs):
        captured["url"] = url
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"data": {"message": "删除成功"}},
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr("app.routes.accounts.http_requests.delete", mock_delete)

    try:
        with TestClient(app) as client:
            resp = client.delete("/accounts/MP_WXS_abc123")
    finally:
        _restore_creds(settings, orig_ak, orig_sk)

    assert resp.status_code == 200
    assert "MP_WXS_abc123" in captured["url"]


def test_update_account_articles_proxies(monkeypatch) -> None:
    """触发文章更新请求正确代理。"""
    settings, orig_ak, orig_sk = _with_creds()
    captured = {}

    def mock_get(url, **kwargs):
        captured["url"] = url
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"data": {"message": "已触发更新"}},
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr("app.routes.accounts.http_requests.get", mock_get)

    try:
        with TestClient(app) as client:
            resp = client.post("/accounts/update/MP_WXS_xyz")
    finally:
        _restore_creds(settings, orig_ak, orig_sk)

    assert resp.status_code == 200
    assert "MP_WXS_xyz" in captured["url"]


def test_proxy_returns_502_when_we_mp_rss_unreachable(monkeypatch) -> None:
    """we-mp-rss 不可达时返回 502。"""
    import requests as _requests

    settings, orig_ak, orig_sk = _with_creds()

    def mock_get(url, **kwargs):
        raise _requests.ConnectionError("Connection refused")

    monkeypatch.setattr("app.routes.accounts.http_requests.get", mock_get)

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/accounts")
    finally:
        _restore_creds(settings, orig_ak, orig_sk)

    assert resp.status_code == 502
    assert "不可达" in resp.json()["detail"]


def test_proxy_returns_upstream_error_code(monkeypatch) -> None:
    """we-mp-rss 返回错误时，状态码正确透传。"""
    import requests as _requests

    settings, orig_ak, orig_sk = _with_creds()

    def mock_get(url, **kwargs):
        resp = SimpleNamespace(
            status_code=404,
            json=lambda: {"detail": "公众号不存在"},
            text='{"detail": "公众号不存在"}',
        )
        exc = _requests.HTTPError(response=resp)
        raise exc

    monkeypatch.setattr("app.routes.accounts.http_requests.get", mock_get)

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/accounts")
    finally:
        _restore_creds(settings, orig_ak, orig_sk)

    assert resp.status_code == 404
