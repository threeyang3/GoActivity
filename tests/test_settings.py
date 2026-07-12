"""设置 API 测试。"""

from fastapi.testclient import TestClient

from app.main import app


def test_settings_schema_returns_list():
    """GET /settings/schema 应返回配置 Schema 列表。"""
    with TestClient(app) as client:
        resp = client.get("/settings/schema")
        assert resp.status_code == 200
        schema = resp.json()
        assert isinstance(schema, list)
        assert len(schema) > 20  # 应该有大量配置项

        # 验证每个 schema 项的结构
        for item in schema:
            assert "key" in item
            assert "label" in item
            assert "category" in item
            assert "type" in item
            assert "default" in item


def test_settings_returns_current_values():
    """GET /settings 应返回当前配置值。"""
    with TestClient(app) as client:
        resp = client.get("/settings")
        assert resp.status_code == 200
        settings = resp.json()
        assert isinstance(settings, dict)
        # 应该包含基本配置
        assert "app_name" in settings
        assert "app_port" in settings
        assert "ocr_provider" in settings


def test_settings_secrets_are_masked():
    """GET /settings 不应返回明文密钥。"""
    with TestClient(app) as client:
        resp = client.get("/settings")
        settings = resp.json()
        # 密钥字段应该返回掩码对象
        secret_keys = ["vision_api_key", "feishu_app_secret", "admin_token", "ocr_api_key",
                       "text_ai_api_key", "we_mp_rss_access_key", "we_mp_rss_secret_key"]
        for key in secret_keys:
            if key in settings:
                val = settings[key]
                # 密钥字段应该是对象，包含 configured 和 masked_value
                if isinstance(val, dict):
                    assert "configured" in val
                    assert "masked_value" in val
                    # masked_value 不应包含完整密钥
                    if val.get("configured"):
                        assert val["masked_value"] != ""
                        assert "****" in val["masked_value"] or len(val["masked_value"]) < 20


def test_settings_update_saves():
    """PUT /settings 应保存配置。"""
    with TestClient(app) as client:
        resp = client.put("/settings", json={"app_name": "TestApp"})
        assert resp.status_code == 200
        data = resp.json()
        assert "applied" in data
        assert "app_name" in data["applied"]

        # 验证保存后可读取
        resp = client.get("/settings")
        settings = resp.json()
        assert settings["app_name"] == "TestApp"

        # 恢复默认值
        client.put("/settings", json={"app_name": "GoActivity"})


def test_settings_rejects_unknown_fields():
    """PUT /settings 应拒绝未知字段。"""
    with TestClient(app) as client:
        resp = client.put("/settings", json={"unknown_field": "value"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data.get("errors", [])) > 0
        assert any("未知配置项" in e.get("error", "") for e in data["errors"])


def test_settings_rejects_type_errors():
    """PUT /settings 应拒绝类型错误。"""
    with TestClient(app) as client:
        resp = client.put("/settings", json={"app_port": "not_a_number"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data.get("errors", [])) > 0


def test_settings_restart_required():
    """PUT /settings 应正确返回需要重启的字段。"""
    with TestClient(app) as client:
        resp = client.put("/settings", json={"app_port": 9999})
        assert resp.status_code == 200
        data = resp.json()
        assert "app_port" in data.get("restart_required", [])

        # 恢复默认值
        client.put("/settings", json={"app_port": 8000})


def test_settings_test_endpoints_exist():
    """测试 Provider 测试端点存在且可访问。"""
    with TestClient(app) as client:
        for endpoint in ["/settings/test/ocr", "/settings/test/vision",
                         "/settings/test/text-ai", "/settings/test/feishu",
                         "/settings/test/we-mp-rss"]:
            resp = client.post(endpoint)
            assert resp.status_code == 200
            data = resp.json()
            assert "ok" in data
            assert "message" in data
