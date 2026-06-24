"""Campus Activity Knowledge Hub — FastAPI 入口。"""

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.db import init_db
from app.exceptions import AppError, FeishuError, ProviderError, SyncError, ValidationError
from app.logging_config import setup_logging
from app.routes import articles, events, health, reports, setup, sync, webhooks
from app.routes.dashboard import router as dashboard_router
from app.services.auto_sync import AutoSyncService
from app.services.bot_consumer import BotEventConsumer
from app.services.scheduler import ReportScheduler


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    init_db()
    # 启动定时任务调度器
    scheduler = ReportScheduler()
    scheduler.start()
    # 启动自动同步服务
    auto_sync = AutoSyncService()
    auto_sync.start()
    # 启动飞书机器人
    bot_consumer = BotEventConsumer()
    bot_consumer.start()
    # 将实例挂到 app.state，供路由复用
    application.state.auto_sync = auto_sync
    application.state.bot_consumer = bot_consumer
    yield
    # 关闭飞书机器人
    bot_consumer.shutdown()
    # 关闭定时任务调度器
    scheduler.shutdown()
    # 关闭自动同步服务
    auto_sync.shutdown()


app = FastAPI(title="Campus Activity Knowledge Hub", lifespan=lifespan)

logger = logging.getLogger(__name__)

# 挂载静态文件
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def root():
    """重定向到管理后台。"""
    return RedirectResponse(url="/static/index.html")


# ---------------------------------------------------------------------------
# Global exception handlers — map domain exceptions to HTTP status codes
# ---------------------------------------------------------------------------

@app.exception_handler(ProviderError)
async def provider_error_handler(request: Request, exc: ProviderError) -> JSONResponse:
    logger.error("ProviderError: %s", exc)
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(FeishuError)
async def feishu_error_handler(request: Request, exc: FeishuError) -> JSONResponse:
    logger.error("FeishuError: %s", exc)
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(SyncError)
async def sync_error_handler(request: Request, exc: SyncError) -> JSONResponse:
    logger.error("SyncError: %s", exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    logger.warning("ValidationError: %s", exc)
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.error("AppError: %s", exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# ---------------------------------------------------------------------------
# Request ID middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """为每个请求附加 X-Request-Id，便于日志关联。"""
    request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


# ---------------------------------------------------------------------------
# Routes that need app.state stay here; everything else is in app/routes/.
# ---------------------------------------------------------------------------

@app.get("/bot/status")
def bot_status() -> dict[str, Any]:
    """飞书机器人运行状态。"""
    consumer: BotEventConsumer = app.state.bot_consumer
    return {
        "enabled": consumer.running or False,
        "running": consumer.running,
    }


@app.post("/sync/auto")
def trigger_auto_sync() -> dict[str, Any]:
    """手动触发一次自动同步（拉取新文章 + 同步到飞书）"""
    service: AutoSyncService = app.state.auto_sync
    result = service.run_now()
    return {
        "status": "ok",
        "articles_fetched": result["articles_fetched"],
        "events_synced": result["events_synced"],
        "events_failed": result["events_failed"],
    }


# ---------------------------------------------------------------------------
# Include routers
# ---------------------------------------------------------------------------

app.include_router(health.router)
app.include_router(events.router)
app.include_router(sync.router)
app.include_router(reports.router)
app.include_router(setup.router)
app.include_router(webhooks.router)
app.include_router(articles.router)
app.include_router(dashboard_router)
