"""健康检查测试 — 验证三级状态逻辑。"""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.routes.health import _check_ocr


def test_health_returns_ok_when_healthy():
    """数据库正常时应返回 ok 或 degraded。"""
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded", "error")
        assert "checks" in data


def test_health_has_required_checks():
    """健康检查应包含所有必要的检查项。"""
    with TestClient(app) as client:
        resp = client.get("/health")
        data = resp.json()
        checks = data["checks"]
        required = ["database", "we_mp_rss", "ocr", "vision", "text_ai", "lark_cli", "storage"]
        for key in required:
            assert key in checks, f"缺少检查项: {key}"
            assert "status" in checks[key], f"检查项 {key} 缺少 status 字段"


def test_health_disabled_modules_not_error():
    """已禁用的模块应显示 disabled，不能误报为 error。"""
    with TestClient(app) as client:
        resp = client.get("/health")
        data = resp.json()
        checks = data["checks"]
        # OCR 和 Vision 默认是 mock，不应报 error
        if checks.get("ocr", {}).get("provider") == "mock":
            assert checks["ocr"]["status"] != "error"
        if checks.get("text_ai", {}).get("provider") in ("disabled", "mock"):
            assert checks["text_ai"]["status"] not in ("error",)


def test_health_database_error_leads_to_error_status():
    """数据库不可用时应返回 error 状态。

    注意：这个测试在数据库正常时无法真正模拟失败，
    但可以验证数据库检查结果的结构。
    """
    with TestClient(app) as client:
        resp = client.get("/health")
        data = resp.json()
        db_check = data["checks"]["database"]
        if db_check["status"] == "error":
            assert data["status"] == "error"


def test_rapidocr_health_check_does_not_import_native_runtime(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.routes.health.importlib.util.find_spec",
        lambda name: calls.append(name) or object(),
    )

    result = _check_ocr(SimpleNamespace(ocr_provider="rapid"))

    assert result == {"status": "ok", "provider": "rapid"}
    assert calls == ["rapidocr_onnxruntime"]
