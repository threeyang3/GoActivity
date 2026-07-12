"""设置 API 路由。"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.auth import require_admin
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])
logger = logging.getLogger(__name__)


@router.get("/schema")
def get_settings_schema() -> list[dict[str, Any]]:
    return SettingsService().get_schema()


@router.get("")
def get_settings_values() -> dict[str, Any]:
    return SettingsService().get_current_values()


@router.put("")
def update_settings(
    body: dict[str, Any],
    request: Request,
    _auth: None = Depends(require_admin),
) -> dict[str, Any]:
    service = SettingsService()
    secret_updates: dict[str, str] = {}
    normal_updates: dict[str, Any] = {}
    clear_secrets: list[str] = []

    raw_clear = body.pop("clear_secrets", None)
    if isinstance(raw_clear, list):
        clear_secrets = [str(item) for item in raw_clear]

    schema_keys = {item["key"]: item for item in service.get_schema()}
    for key, value in body.items():
        schema = schema_keys.get(key)
        if schema and schema.get("is_secret"):
            secret_updates[key] = str(value)
        else:
            normal_updates[key] = value

    applied, rescheduled, restart_required, errors = service.update_settings(
        normal_updates,
        secret_updates,
        clear_secrets=clear_secrets,
    )
    runtime = service.reload_runtime(request.app) if applied else {"reloaded": [], "rescheduled": []}
    return {
        "applied": applied,
        "rescheduled": sorted(set(rescheduled + runtime["rescheduled"])),
        "restart_required": restart_required,
        "errors": errors,
        "reloaded": runtime["reloaded"],
    }


@router.post("/reset")
def reset_settings(
    body: dict[str, Any] | None,
    request: Request,
    _auth: None = Depends(require_admin),
) -> dict[str, Any]:
    keys = [str(item) for item in (body or {}).get("keys", [])]
    if not keys:
        keys = [item["key"] for item in SettingsService().get_schema()]
    reset = SettingsService().reset_settings(keys)
    runtime = SettingsService().reload_runtime(request.app)
    return {"reset": reset, "reloaded": runtime["reloaded"], "rescheduled": runtime["rescheduled"]}


@router.post("/reload")
def reload_settings(request: Request, _auth: None = Depends(require_admin)) -> dict[str, Any]:
    return SettingsService().reload_runtime(request.app)


@router.post("/test/ocr")
def test_ocr(_auth: None = Depends(require_admin)) -> dict[str, Any]:
    from app.config import get_settings

    settings = get_settings()
    provider = settings.ocr_provider

    if provider == "disabled":
        return {"ok": True, "provider": provider, "message": "OCR 已禁用", "latency_ms": 0}
    if provider == "mock":
        return {"ok": True, "provider": provider, "message": "Mock 模式，无需连接", "latency_ms": 0}
    if provider == "rapid":
        try:
            start = time.time()
            from rapidocr_onnxruntime import RapidOCR  # noqa: F401

            latency = int((time.time() - start) * 1000)
            return {"ok": True, "provider": provider, "model": "rapidocr_onnxruntime", "latency_ms": latency, "message": "RapidOCR 可用"}
        except ImportError:
            return {"ok": False, "provider": provider, "message": "rapidocr_onnxruntime 未安装", "error_type": "dependency_missing"}
    if provider in ("openai", "openai_compatible"):
        if not settings.ocr_api_key:
            return {"ok": False, "provider": provider, "message": "缺少 OCR API 密钥", "error_type": "config_missing"}
        return _test_openai_api(settings.ocr_api_key, settings.ocr_api_base_url, settings.ocr_api_model, "OCR")
    return {"ok": False, "provider": provider, "message": f"未知 Provider: {provider}", "error_type": "unknown"}


@router.post("/test/vision")
def test_vision(_auth: None = Depends(require_admin)) -> dict[str, Any]:
    from app.config import get_settings

    settings = get_settings()
    provider = settings.vision_api_provider

    if provider == "mock":
        return {"ok": True, "provider": provider, "message": "Mock 模式，无需连接", "latency_ms": 0}
    if provider in ("openai", "openai_compatible"):
        if not settings.vision_api_key:
            return {"ok": False, "provider": provider, "message": "缺少 Vision API 密钥", "error_type": "config_missing"}
        return _test_openai_api(settings.vision_api_key, settings.vision_api_base_url, settings.vision_api_model, "Vision")
    return {"ok": False, "provider": provider, "message": f"未知 Provider: {provider}", "error_type": "unknown"}


@router.post("/test/text-ai")
def test_text_ai(_auth: None = Depends(require_admin)) -> dict[str, Any]:
    from app.config import get_settings

    settings = get_settings()
    provider = settings.text_ai_provider

    if provider == "disabled":
        return {"ok": True, "provider": provider, "message": "文本 AI 已禁用", "latency_ms": 0}
    if provider == "mock":
        return {"ok": True, "provider": provider, "message": "Mock 模式，无需连接", "latency_ms": 0}
    if provider in ("openai", "openai_compatible"):
        if not settings.text_ai_api_key:
            return {"ok": False, "provider": provider, "message": "缺少文本 AI API 密钥", "error_type": "config_missing"}
        return _test_openai_api(settings.text_ai_api_key, settings.text_ai_api_base_url, settings.text_ai_api_model, "TextAI")
    return {"ok": False, "provider": provider, "message": f"未知 Provider: {provider}", "error_type": "unknown"}


@router.post("/test/feishu")
def test_feishu(_auth: None = Depends(require_admin)) -> dict[str, Any]:
    import shutil
    from app.config import get_settings

    settings = get_settings()
    provider = settings.feishu_provider

    if provider in ("lark_cli", "auto"):
        cli_path = settings.feishu_cli_path
        if shutil.which(cli_path):
            return {"ok": True, "provider": "lark_cli", "path": cli_path, "message": "lark-cli 可用", "latency_ms": 0}
        if provider == "lark_cli":
            return {"ok": False, "provider": "lark_cli", "message": f"lark-cli 未找到: {cli_path}", "error_type": "dependency_missing"}

    if provider in ("openapi", "auto"):
        if not settings.feishu_app_id or not settings.feishu_app_secret:
            if provider == "openapi":
                return {"ok": False, "provider": "openapi", "message": "缺少飞书 App ID 或 Secret", "error_type": "config_missing"}
        else:
            return {"ok": True, "provider": "openapi", "message": "飞书 OpenAPI 配置完整", "latency_ms": 0}
    return {"ok": False, "provider": provider, "message": "飞书未配置", "error_type": "config_missing"}


@router.post("/test/we-mp-rss")
def test_we_mp_rss(_auth: None = Depends(require_admin)) -> dict[str, Any]:
    import requests as http_requests
    from app.config import get_settings

    settings = get_settings()
    try:
        start = time.time()
        resp = http_requests.get(f"{settings.we_mp_rss_base_url}/api/docs", timeout=5)
        latency = int((time.time() - start) * 1000)
        if resp.status_code == 200:
            return {"ok": True, "provider": "we-mp-rss", "latency_ms": latency, "message": "连接成功"}
        return {"ok": False, "provider": "we-mp-rss", "message": f"HTTP {resp.status_code}", "error_type": "http_error", "latency_ms": latency}
    except Exception as exc:
        return {"ok": False, "provider": "we-mp-rss", "message": f"连接失败: {str(exc)[:100]}", "error_type": "network_error"}


def _test_openai_api(api_key: str, base_url: str, model: str, label: str) -> dict[str, Any]:
    import requests

    try:
        start = time.time()
        resp = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": "Say OK"}], "max_tokens": 5},
            timeout=15,
        )
        latency = int((time.time() - start) * 1000)
        if resp.status_code == 200:
            return {"ok": True, "provider": "openai_compatible", "model": model, "latency_ms": latency, "message": "连接成功"}
        try:
            error_body = resp.json()
            error_msg = error_body.get("error", {}).get("message", resp.text[:200])
        except Exception:
            error_msg = resp.text[:200]
        error_type = "http_error"
        if resp.status_code == 401:
            error_type = "auth_error"
        elif resp.status_code == 404:
            error_type = "model_not_found"
        elif resp.status_code == 429:
            error_type = "rate_limit"
        return {"ok": False, "provider": "openai_compatible", "model": model, "latency_ms": latency, "message": f"{label} API 错误 ({resp.status_code}): {error_msg}", "error_type": error_type}
    except requests.exceptions.Timeout:
        return {"ok": False, "provider": "openai_compatible", "model": model, "message": f"{label} API 超时", "error_type": "timeout"}
    except requests.exceptions.ConnectionError as exc:
        return {"ok": False, "provider": "openai_compatible", "model": model, "message": f"连接失败: {str(exc)[:100]}", "error_type": "network_error"}
    except Exception as exc:
        return {"ok": False, "provider": "openai_compatible", "model": model, "message": f"未知错误: {str(exc)[:100]}", "error_type": "unknown"}
