"""公众号管理全链路集成测试。

模拟完整流程：搜索 → 添加 → 列表 → 刷新 → 删除，验证代理路由与 we-mp-rss API 的对接。
"""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def _with_creds(ak="test-ak", sk="test-sk"):
    settings = get_settings()
    orig_ak, orig_sk = settings.we_mp_rss_access_key, settings.we_mp_rss_secret_key
    settings.we_mp_rss_access_key = ak
    settings.we_mp_rss_secret_key = sk
    return settings, orig_ak, orig_sk


def _restore(settings, orig_ak, orig_sk):
    settings.we_mp_rss_access_key = orig_ak
    settings.we_mp_rss_secret_key = orig_sk


class FakeResponse:
    """可配置的 mock HTTP 响应。"""
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text or str(json_data)

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(response=self)


class TestFullFlow:
    """搜索 → 添加 → 列表 → 刷新 → 删除 全链路。"""

    def test_search_then_add_then_list_then_delete(self, monkeypatch):
        """完整生命周期：搜索公众号 → 添加 → 列表确认 → 删除。"""
        settings, orig_ak, orig_sk = _with_creds()
        calls = []  # 记录所有 API 调用

        # Phase 1: 搜索返回一个公众号
        search_result = {
            "data": {
                "list": [{
                    "mp_name": "北京大学团委",
                    "mp_id": "MjM5NjA4MTk4MA==",
                    "fakeid": "MjM5NjA4MTk4MA==",
                    "avatar": "https://example.com/avatar.png",
                    "mp_intro": "北京大学团委官方公众号",
                }],
                "total": 1,
            }
        }

        # Phase 2: 添加成功
        add_result = {
            "data": {
                "id": "MP_WXS_abc123",
                "mp_name": "北京大学团委",
                "status": 1,
                "created_at": "2026-06-26T10:00:00",
            }
        }

        # Phase 3: 列表包含刚添加的公众号
        list_result = {
            "data": {
                "list": [{
                    "id": "MP_WXS_abc123",
                    "mp_name": "北京大学团委",
                    "mp_cover": "/files/avatars/abc.png",
                    "mp_intro": "北京大学团委官方公众号",
                    "status": 1,
                    "created_at": "2026-06-26T10:00:00",
                }],
                "total": 1,
            }
        }

        # Phase 4: 删除成功
        delete_result = {"data": {"message": "删除成功", "id": "MP_WXS_abc123"}}

        # Phase 5: 刷新文章
        update_result = {"data": {"message": "已触发更新", "time_span": 100}}

        def mock_get(url, **kwargs):
            calls.append(("GET", url, kwargs.get("params", {})))
            if "/search/" in url:
                return FakeResponse(200, search_result)
            if "/update/" in url:
                return FakeResponse(200, update_result)
            # 列表
            return FakeResponse(200, list_result)

        def mock_post(url, **kwargs):
            calls.append(("POST", url, kwargs.get("json", {})))
            return FakeResponse(200, add_result)

        def mock_delete(url, **kwargs):
            calls.append(("DELETE", url, {}))
            return FakeResponse(200, delete_result)

        monkeypatch.setattr("app.routes.accounts.http_requests.get", mock_get)
        monkeypatch.setattr("app.routes.accounts.http_requests.post", mock_post)
        monkeypatch.setattr("app.routes.accounts.http_requests.delete", mock_delete)

        try:
            with TestClient(app) as client:
                # Step 1: 搜索
                resp = client.get("/accounts/search/北京大学团委")
                assert resp.status_code == 200
                search_data = resp.json()
                assert search_data["data"]["list"][0]["mp_name"] == "北京大学团委"
                assert "北京大学团委" in calls[-1][1]  # URL 包含关键词

                # Step 2: 添加
                mp = search_data["data"]["list"][0]
                resp = client.post("/accounts", json={
                    "mp_name": mp["mp_name"],
                    "mp_id": mp.get("mp_id") or mp.get("fakeid") or mp.get("id", ""),
                    "avatar": mp.get("avatar", ""),
                    "mp_cover": mp.get("mp_cover") or mp.get("avatar", ""),
                    "mp_intro": mp.get("mp_intro", ""),
                })
                assert resp.status_code == 200
                add_data = resp.json()
                assert add_data["data"]["mp_name"] == "北京大学团委"
                assert add_data["data"]["id"] == "MP_WXS_abc123"
                # 验证 POST body 包含正确字段
                post_call = [c for c in calls if c[0] == "POST"][0]
                assert post_call[2]["mp_name"] == "北京大学团委"
                assert post_call[2]["mp_id"] == "MjM5NjA4MTk4MA=="

                # Step 3: 列表确认
                resp = client.get("/accounts")
                assert resp.status_code == 200
                list_data = resp.json()
                assert list_data["data"]["total"] == 1
                assert list_data["data"]["list"][0]["id"] == "MP_WXS_abc123"

                # Step 4: 刷新文章
                resp = client.post("/accounts/update/MP_WXS_abc123")
                assert resp.status_code == 200
                assert "已触发更新" in resp.json()["data"]["message"]
                # 验证 URL 包含 mp_id
                update_call = [c for c in calls if c[0] == "GET" and "update" in c[1]][0]
                assert "MP_WXS_abc123" in update_call[1]

                # Step 5: 删除
                resp = client.delete("/accounts/MP_WXS_abc123")
                assert resp.status_code == 200
                assert resp.json()["data"]["message"] == "删除成功"
                # 验证 DELETE URL 包含 mp_id
                delete_call = [c for c in calls if c[0] == "DELETE"][0]
                assert "MP_WXS_abc123" in delete_call[1]

                # 验证总调用次数
                assert len(calls) == 5  # search, add, list, update, delete

        finally:
            _restore(settings, orig_ak, orig_sk)


class TestErrorRecovery:
    """各种异常场景下的可靠性。"""

    def test_search_with_chinese_characters(self, monkeypatch):
        """中文关键词正确 URL 编码。"""
        settings, orig_ak, orig_sk = _with_creds()
        captured_url = {}

        def mock_get(url, **kwargs):
            captured_url["url"] = url
            return FakeResponse(200, {"data": {"list": [], "total": 0}})

        monkeypatch.setattr("app.routes.accounts.http_requests.get", mock_get)

        try:
            with TestClient(app) as client:
                resp = client.get("/accounts/search/百周年纪念讲堂")
                assert resp.status_code == 200
                assert "百周年纪念讲堂" in captured_url["url"]
        finally:
            _restore(settings, orig_ak, orig_sk)

    def test_add_with_special_characters_in_name(self, monkeypatch):
        """公众号名称含特殊字符（如 ·）时正确处理。"""
        settings, orig_ak, orig_sk = _with_creds()
        captured_json = {}

        def mock_post(url, **kwargs):
            captured_json["body"] = kwargs.get("json", {})
            return FakeResponse(200, {"data": {"id": "mp1", "mp_name": kwargs["json"]["mp_name"]}})

        monkeypatch.setattr("app.routes.accounts.http_requests.post", mock_post)

        try:
            with TestClient(app) as client:
                resp = client.post("/accounts", json={
                    "mp_name": "北京大学·艺术学院",
                    "mp_id": "abc123==",
                })
                assert resp.status_code == 200
                assert captured_json["body"]["mp_name"] == "北京大学·艺术学院"
        finally:
            _restore(settings, orig_ak, orig_sk)

    def test_add_with_base64_mp_id(self, monkeypatch):
        """base64 编码的 mp_id（含 + / =）正确传递。"""
        settings, orig_ak, orig_sk = _with_creds()
        captured_json = {}

        def mock_post(url, **kwargs):
            captured_json["body"] = kwargs.get("json", {})
            return FakeResponse(200, {"data": {"id": "mp1"}})

        monkeypatch.setattr("app.routes.accounts.http_requests.post", mock_post)

        try:
            with TestClient(app) as client:
                # base64 含 + / = 特殊字符
                resp = client.post("/accounts", json={
                    "mp_name": "测试号",
                    "mp_id": "MjM5NjA4/MTk4MA==",
                })
                assert resp.status_code == 200
                assert captured_json["body"]["mp_id"] == "MjM5NjA4/MTk4MA=="
        finally:
            _restore(settings, orig_ak, orig_sk)

    def test_delete_with_url_encoded_id(self, monkeypatch):
        """DELETE 请求中 mp_id 的特殊字符被正确编码传递。"""
        settings, orig_ak, orig_sk = _with_creds()
        captured_url = {}

        def mock_delete(url, **kwargs):
            captured_url["url"] = url
            return FakeResponse(200, {"data": {"message": "ok"}})

        monkeypatch.setattr("app.routes.accounts.http_requests.delete", mock_delete)

        try:
            with TestClient(app) as client:
                # 含 + 和 = 的 base64 id（/ 会被 URL 编码）
                mp_id = "MP_WXS_abc+def=="
                resp = client.delete(f"/accounts/{mp_id}")
                assert resp.status_code == 200
                assert "MP_WXS_abc" in captured_url["url"]
        finally:
            _restore(settings, orig_ak, orig_sk)

    def test_we_mp_rss_returns_error_passthrough(self, monkeypatch):
        """we-mp-rss 返回业务错误时，状态码和消息透传。"""
        import requests as _requests

        settings, orig_ak, orig_sk = _with_creds()

        def mock_get(url, **kwargs):
            resp = FakeResponse(
                status_code=404,
                json_data={"code": 40401, "message": "公众号不存在"},
            )
            raise _requests.HTTPError(response=resp)

        monkeypatch.setattr("app.routes.accounts.http_requests.get", mock_get)

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                # 用 update 端点测试（POST /accounts/update/{mp_id}）
                resp = client.post("/accounts/update/nonexistent")
                assert resp.status_code == 404
        finally:
            _restore(settings, orig_ak, orig_sk)

    def test_we_mp_rss_connection_refused(self, monkeypatch):
        """we-mp-rss 完全不可达时返回 502。"""
        import requests as _requests

        settings, orig_ak, orig_sk = _with_creds()

        def mock_get(url, **kwargs):
            raise _requests.ConnectionError("Connection refused")

        monkeypatch.setattr("app.routes.accounts.http_requests.get", mock_get)

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/accounts")
                assert resp.status_code == 502
                assert "不可达" in resp.json()["detail"]
        finally:
            _restore(settings, orig_ak, orig_sk)

    def test_we_mp_rss_timeout(self, monkeypatch):
        """we-mp-rss 超时时返回 502。"""
        import requests as _requests

        settings, orig_ak, orig_sk = _with_creds()

        def mock_get(url, **kwargs):
            raise _requests.Timeout("Read timed out")

        monkeypatch.setattr("app.routes.accounts.http_requests.get", mock_get)

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/accounts")
                assert resp.status_code == 502
        finally:
            _restore(settings, orig_ak, orig_sk)

    def test_missing_credentials_blocks_all_endpoints(self):
        """所有端点在无凭据时都返回 500（POST 需要 body，单独测试）。"""
        settings = get_settings()
        orig_ak, orig_sk = settings.we_mp_rss_access_key, settings.we_mp_rss_secret_key
        settings.we_mp_rss_access_key = ""
        settings.we_mp_rss_secret_key = ""

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                # GET / DELETE 端点
                for method, path in [
                    ("GET", "/accounts"),
                    ("GET", "/accounts/search/test"),
                    ("DELETE", "/accounts/fake"),
                    ("POST", "/accounts/update/fake"),
                ]:
                    resp = getattr(client, method.lower())(path)
                    assert resp.status_code == 500, f"{method} {path} should be 500, got {resp.status_code}"
                    assert "WE_MP_RSS_ACCESS_KEY" in resp.json()["detail"]

                # POST 需要 body，否则 FastAPI 返回 422
                resp = client.post("/accounts", json={"mp_name": "test", "mp_id": "x"})
                assert resp.status_code == 500, f"POST /accounts should be 500, got {resp.status_code}"
                assert "WE_MP_RSS_ACCESS_KEY" in resp.json()["detail"]
        finally:
            settings.we_mp_rss_access_key = orig_ak
            settings.we_mp_rss_secret_key = orig_sk


class TestAuthHeaders:
    """认证头传递验证。"""

    def test_auth_header_contains_ak_sk(self, monkeypatch):
        """请求头包含正确的 AK-SK 格式。"""
        settings, orig_ak, orig_sk = _with_creds("my-ak", "my-sk")
        captured_headers = {}

        def mock_get(url, **kwargs):
            captured_headers["h"] = kwargs.get("headers", {})
            return FakeResponse(200, {"data": {"list": [], "total": 0}})

        monkeypatch.setattr("app.routes.accounts.http_requests.get", mock_get)

        try:
            with TestClient(app) as client:
                client.get("/accounts")
                assert captured_headers["h"]["Authorization"] == "AK-SK my-ak:my-sk"
        finally:
            _restore(settings, orig_ak, orig_sk)
