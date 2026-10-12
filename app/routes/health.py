"""健康检查、配置诊断路由。

三级状态：
- ok: 所有启用模块正常
- degraded: 核心服务正常，但集成模块有问题
- error: 核心服务（数据库、主服务）不可用
"""

import importlib.util
import logging
import shutil
import time
from typing import Any

import requests as http_requests
from fastapi import APIRouter, Request
from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal
from app.schemas import DiagnosticsResponse
from app.services.diagnostics import DiagnosticsService

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health/live")
def liveness(request: Request) -> dict:
    database = _check_database()
    execution = _check_sync_execution(getattr(request.app.state, "auto_sync", None), get_settings())
    return {"status": "error" if database["status"] == "error" or execution["status"] == "error" else "ok",
            "checks": {"database": database, "sync_execution": execution}}


def _check_database() -> dict[str, Any]:
    """检查数据库连接。"""
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)[:200]}
    finally:
        db.close()


def _check_we_mp_rss(settings) -> dict[str, Any]:
    """检查 we-mp-rss 连通性。"""
    try:
        start = time.time()
        resp = http_requests.get(f"{settings.we_mp_rss_base_url}/api/docs", timeout=3)
        elapsed_ms = int((time.time() - start) * 1000)
        if resp.status_code == 200:
            from app.services.automation_guard import AutomationGuardService
            with SessionLocal() as db:
                collection = AutomationGuardService(db).collection_health()
            return {"status": collection["status"], "latency_ms": elapsed_ms, "collection": collection}
        return {"status": "error", "code": resp.status_code}
    except Exception as exc:
        return {"status": "unreachable", "detail": str(exc)[:100]}


def _check_lark_cli(settings) -> dict[str, Any]:
    """检查 lark-cli 可用性。"""
    cli_path = settings.feishu_cli_path
    if shutil.which(cli_path):
        return {"status": "ok", "path": cli_path}
    return {"status": "not_found", "path": cli_path}


def _check_ocr(settings) -> dict[str, Any]:
    """检查 OCR Provider 状态。"""
    provider = settings.ocr_provider
    if provider == "disabled":
        return {"status": "disabled", "provider": provider}
    if provider == "mock":
        return {"status": "mock", "provider": provider}
    if provider == "rapid":
        # Do not import the native OCR runtime from a high-frequency health
        # endpoint.  A mismatched Python/ONNX DLL can terminate the process
        # before Python has a chance to raise ImportError.
        if importlib.util.find_spec("rapidocr_onnxruntime") is not None:
            return {"status": "ok", "provider": provider}
        return {"status": "error", "provider": provider, "detail": "rapidocr_onnxruntime 未安装"}
    if provider in ("openai", "openai_compatible"):
        if not settings.ocr_api_key:
            return {"status": "not_configured", "provider": provider, "detail": "缺少 OCR_API_KEY"}
        return {"status": "configured", "provider": provider, "model": settings.ocr_api_model}
    return {"status": "unknown", "provider": provider}


def _check_vision(settings) -> dict[str, Any]:
    """检查 Vision Provider 状态。"""
    provider = settings.vision_api_provider
    if provider == "mock":
        return {"status": "mock", "provider": provider}
    if provider in ("openai", "openai_compatible"):
        if not settings.vision_api_key:
            return {"status": "not_configured", "provider": provider, "detail": "缺少 VISION_API_KEY"}
        return {"status": "configured", "provider": provider, "model": settings.vision_api_model}
    if provider == "textai":
        if not settings.vision_api_key:
            return {"status": "not_configured", "provider": provider, "detail": "缺少 VISION_API_KEY"}
        return {"status": "configured", "provider": provider, "model": settings.vision_api_model}
    return {"status": "unknown", "provider": provider}


def _check_text_ai(settings) -> dict[str, Any]:
    """检查文本 AI Provider 状态。"""
    provider = settings.text_ai_provider
    if provider == "disabled":
        return {"status": "disabled", "provider": provider}
    if provider == "mock":
        return {"status": "mock", "provider": provider}
    if provider in ("openai", "openai_compatible"):
        if not settings.text_ai_api_key:
            return {"status": "not_configured", "provider": provider, "detail": "缺少 TEXT_AI_API_KEY"}
        return {"status": "configured", "provider": provider, "model": settings.text_ai_api_model}
    return {"status": "unknown", "provider": provider}


def _check_last_sync() -> dict[str, Any]:
    """检查最近一次同步状态。"""
    try:
        from app.services.sync_run_service import SyncRunService

        db = SessionLocal()
        try:
            latest = SyncRunService(db).latest_run("auto-sync")
            if latest:
                return {
                    "status": latest.status,
                    "at": latest.started_at.isoformat() if latest.started_at else None,
                    "error": latest.error_message[:200] if latest.error_message else None,
                }
            return {"status": "no_runs"}
        finally:
            db.close()
    except Exception:
        return {"status": "unknown"}


def _check_storage(settings) -> dict[str, Any]:
    """检查存储目录。"""
    storage = settings.storage_dir
    if storage.exists():
        return {"status": "ok", "path": str(storage)}
    return {"status": "missing", "path": str(storage)}


def _check_sync_execution(auto_sync, settings) -> dict:
    from datetime import datetime, timezone
    if auto_sync is None:
        return {"status": "disabled"}
    state = auto_sync.get_sync_status()
    if not state.get("running"):
        return {"status": "ok"}
    try:
        started = datetime.fromisoformat(state["started_at"])
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        minutes = (datetime.now(timezone.utc) - started).total_seconds() / 60
    except (KeyError, TypeError, ValueError):
        return {"status": "degraded", "detail": "运行中的任务缺少有效开始时间"}
    limit = max(30, settings.auto_sync_stale_minutes)
    return {"status": "error" if minutes > limit else "ok", "running_minutes": round(minutes, 1), "limit_minutes": limit}


def _check_scheduler(obj: Any, name: str) -> dict[str, Any]:
    if obj is None:
        return {"status": "unknown", "detail": f"{name} 未初始化"}
    scheduler = getattr(obj, "scheduler", None)
    if scheduler is None:
        return {"status": "unknown", "detail": f"{name} 无 scheduler"}
    status_getter = getattr(obj, "get_scheduler_status", None)
    if callable(status_getter):
        try:
            return status_getter()
        except Exception as exc:
            logger.warning("Failed to inspect %s scheduler: %s", name, exc)
            return {"status": "degraded", "running": bool(scheduler.running), "detail": str(exc)[:200]}
    return {"status": "ok" if scheduler.running else "error", "running": bool(scheduler.running)}


def _check_config(settings) -> dict[str, Any]:
    warnings = []
    if settings.allow_lan_access and not settings.admin_token:
        warnings.append("启用局域网访问但未配置 admin_token")
    if settings.feishu_provider == "lark_cli" and not settings.feishu_cli_path:
        warnings.append("缺少 feishu_cli_path")
    return {"status": "ok" if not warnings else "degraded", "warnings": warnings}


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    """增强健康检查：检查各组件状态，返回三级状态。"""
    settings = get_settings()
    checks: dict[str, Any] = {}
    has_error = False
    has_degraded = False

    # 核心检查：数据库
    checks["database"] = _check_database()
    if checks["database"]["status"] == "error":
        has_error = True

    # 核心检查：存储目录
    checks["storage"] = _check_storage(settings)
    if checks["storage"]["status"] == "missing":
        has_error = True

    # 集成检查：we-mp-rss
    checks["we_mp_rss"] = _check_we_mp_rss(settings)
    if checks["we_mp_rss"]["status"] in {"error", "degraded"}:
        has_degraded = True
    elif checks["we_mp_rss"]["status"] == "unreachable":
        has_degraded = True

    # 集成检查：lark-cli
    checks["lark_cli"] = _check_lark_cli(settings)
    if checks["lark_cli"]["status"] == "not_found":
        has_degraded = True

    # 集成检查：OCR
    checks["ocr"] = _check_ocr(settings)
    if checks["ocr"]["status"] == "error":
        has_degraded = True

    # 集成检查：Vision
    checks["vision"] = _check_vision(settings)
    if checks["vision"]["status"] == "error":
        has_degraded = True

    # 集成检查：文本 AI
    checks["text_ai"] = _check_text_ai(settings)
    if checks["text_ai"]["status"] == "error":
        has_degraded = True

    # 集成检查：最近同步
    checks["last_sync"] = _check_last_sync()
    if checks["last_sync"].get("status") == "failed":
        has_degraded = True

    checks["config"] = _check_config(settings)
    if checks["config"]["status"] == "degraded":
        has_degraded = True

    checks["auto_sync_scheduler"] = _check_scheduler(getattr(request.app.state, "auto_sync", None), "auto_sync")
    checks["sync_execution"] = _check_sync_execution(getattr(request.app.state, "auto_sync", None), settings)
    if checks["sync_execution"]["status"] == "error":
        has_error = True
    from app.services.backup_status import backup_status
    checks["backup"] = backup_status(settings)
    if checks["backup"]["status"] != "completed":
        has_degraded = True
    if checks["auto_sync_scheduler"]["status"] in {"error", "degraded"}:
        has_degraded = True

    checks["report_scheduler"] = _check_scheduler(getattr(request.app.state, "report_scheduler", None), "report_scheduler")
    if checks["report_scheduler"]["status"] in {"error", "degraded"}:
        has_degraded = True

    bot_consumer = getattr(request.app.state, "bot_consumer", None)
    checks["bot_consumer"] = {
        "status": "disabled" if not settings.feishu_bot_enabled else ("ok" if getattr(bot_consumer, "running", False) else "error")
    }
    if checks["bot_consumer"]["status"] == "error":
        has_degraded = True

    # 确定总体状态
    if has_error:
        overall = "error"
    elif has_degraded:
        overall = "degraded"
    else:
        overall = "ok"

    return {
        "status": overall,
        "checks": checks,
    }


@router.get("/diagnostics/config", response_model=DiagnosticsResponse)
def diagnostics_config() -> DiagnosticsResponse:
    service = DiagnosticsService()
    settings = service.settings
    return DiagnosticsResponse(
        app_name=settings.app_name,
        we_mp_rss_base_url=settings.we_mp_rss_base_url,
        checks=service.config_checks(),
    )
