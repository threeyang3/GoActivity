"""文章图片处理路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import WebhookResponse
from app.services.article_service import ArticleService

router = APIRouter(tags=["articles"])


@router.post("/articles/{article_id}/process-images", response_model=WebhookResponse)
def process_images(article_id: str, db: Session = Depends(get_db)) -> WebhookResponse:
    result = ArticleService(db).process_article_images(article_id)
    return WebhookResponse(**result)
