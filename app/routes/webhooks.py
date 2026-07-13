"""Webhook 接收路由。"""

import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth import _is_local_request
from app.config import get_settings
from app.schemas import WebhookResponse
from app.services.article_service import ArticleService

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/we-mp-rss", response_model=WebhookResponse)
def receive_we_mp_rss(
    payload: dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
    webhook_token: str | None = Header(default=None, alias="X-GoActivity-Webhook-Token"),
) -> WebhookResponse:
    settings = get_settings()
    if not _is_local_request(request):
        expected = settings.we_mp_rss_webhook_token
        if not expected:
            raise HTTPException(status_code=503, detail="远程 Webhook 未配置认证令牌。")
        if not webhook_token or not secrets.compare_digest(webhook_token, expected):
            raise HTTPException(status_code=401, detail="Webhook 认证失败。")
    result = ArticleService(db).ingest_we_mp_rss_payload(payload)
    return WebhookResponse(**result)
