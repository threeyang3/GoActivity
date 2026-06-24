"""健康检查、配置诊断路由。"""

import shutil
import time
from typing import Any

import requests as http_requests
from fastapi import APIRouter
from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal
from app.schemas import DiagnosticsResponse
from app.services.diagnostics import DiagnosticsService

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, Any]:
    """增强健康检查：检查各组件状态。"""
    checks: dict[str, Any] = {}
    overall_ok = True

    # 1. 数据库连接
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:
        checks["database"] = {"status": "error", "detail": str(exc)}
        overall_ok = False
    finally:
        db.close()

    # 2. lark-cli 可用性
    settings = get_settings()
    cli_path = settings.feishu_cli_path
    if shutil.which(cli_path):
        checks["lark_cli"] = {"status": "ok", "path": cli_path}
    else:
        checks["lark_cli"] = {"status": "not_found", "path": cli_path}

    # 3. Vision API 配置
    if settings.vision_api_key:
        checks["vision_api"] = {"status": "configured", "model": settings.vision_api_model}
    else:
        checks["vision_api"] = {"status": "not_configured"}

    # 4. we-mp-rss 连通性
    try:
        start = time.time()
        resp = http_requests.get(f"{settings.we_mp_rss_base_url}/health", timeout=2)
        elapsed_ms = int((time.time() - start) * 1000)
        if resp.status_code == 200:
            checks["we_mp_rss"] = {"status": "ok", "latency_ms": elapsed_ms}
        else:
            checks["we_mp_rss"] = {"status": "error", "code": resp.status_code}
    except Exception as exc:
        checks["we_mp_rss"] = {"status": "unreachable", "detail": str(exc)[:80]}

    # 5. 上次同步状态
    try:
        from app.services.sync_run_service import SyncRunService

        db = SessionLocal()
        try:
            latest = SyncRunService(db).latest_run("auto-sync")
            if latest:
                checks["last_sync"] = {
                    "status": latest.status,
                    "at": latest.started_at.isoformat() if latest.started_at else None,
                }
            else:
                checks["last_sync"] = {"status": "no_runs"}
        finally:
            db.close()
    except Exception:
        checks["last_sync"] = {"status": "unknown"}

    return {
        "status": "ok" if overall_ok else "degraded",
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
