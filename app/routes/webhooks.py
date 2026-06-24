"""Webhook 接收路由。"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import WebhookResponse
from app.services.article_service import ArticleService

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/we-mp-rss", response_model=WebhookResponse)
def receive_we_mp_rss(payload: dict[str, Any], db: Session = Depends(get_db)) -> WebhookResponse:
    result = ArticleService(db).ingest_we_mp_rss_payload(payload)
    return WebhookResponse(**result)
