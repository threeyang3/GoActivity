"""活动相关路由：列表、抽取、飞书同步、置顶、清理、图片重过滤。"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models import Event
from app.routes.helpers import event_to_out
from app.schemas import (
    CleanupExpiredResponse,
    EventKeepResponse,
    EventOut,
    ExtractResponse,
    FeishuSyncResponse,
)
from app.services.event_extractor import EventExtractor
from app.services.feishu import FeishuAdapter
from app.utils.constants import EventStatus
from app.utils.jsonx import loads_list

router = APIRouter(tags=["events"])
logger = logging.getLogger(__name__)


@router.get("/events", response_model=list[EventOut])
def list_events(
    status: str | None = None,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
    db: Session = Depends(get_db),
) -> list[EventOut]:
    """分页查询活动列表。"""
    query = db.query(Event).options(joinedload(Event.article))
    if status:
        query = query.filter(Event.status == status)
    offset = (page - 1) * page_size
    events = query.order_by(Event.created_at.desc()).offset(offset).limit(page_size).all()
    return [event_to_out(event) for event in events]


@router.post("/events/{event_id}/extract", response_model=ExtractResponse)
def extract_event(event_id: str, db: Session = Depends(get_db)) -> ExtractResponse:
    event = db.query(Event).filter(Event.event_id == event_id).one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    result = EventExtractor(db).extract(event)
    db.commit()
    return ExtractResponse(event_id=event.event_id, status=event.status, result=result)


@router.post("/events/{event_id}/sync-feishu", response_model=FeishuSyncResponse)
def sync_feishu(event_id: str, db: Session = Depends(get_db)) -> FeishuSyncResponse:
    event = db.query(Event).filter(Event.event_id == event_id).one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    result = FeishuAdapter(db).sync_event(event)
    return FeishuSyncResponse(event_id=event.event_id, **result)


@router.post("/events/{event_id}/keep", response_model=EventKeepResponse)
def keep_event(event_id: str, value: bool = True, db: Session = Depends(get_db)) -> EventKeepResponse:
    event = db.query(Event).filter(Event.event_id == event_id).one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event.user_keep = value
    if value and event.status in {EventStatus.EXPIRED_HIDDEN, EventStatus.FILTERED_OUT}:
        event.status = EventStatus.EXTRACTED if event.confidence else EventStatus.PENDING_AI
        event.retention_decision = "keep_user"
    db.commit()
    return EventKeepResponse(
        event_id=event.event_id,
        user_keep=event.user_keep,
        retention_decision=event.retention_decision,
        status=event.status,
    )


@router.post("/events/cleanup-expired", response_model=CleanupExpiredResponse)
def cleanup_expired_events(db: Session = Depends(get_db)) -> CleanupExpiredResponse:
    events = (
        db.query(Event)
        .options(joinedload(Event.article))
        .filter(
            Event.status.notin_(EventStatus.TERMINAL_STATUSES),
        )
        .all()
    )
    removed = 0
    kept = 0
    skipped = 0
    failed = 0
    affected: list[str] = []
    adapter = FeishuAdapter(db)
    for event in events:
        before_status = event.status
        before_record_id = event.feishu_record_id
        try:
            result = adapter.sync_event(event)
        except Exception as exc:
            failed += 1
            logger.error("Failed to cleanup event %s: %s", event.event_id, exc)
            continue
        if event.status in {"expired_hidden", "filtered_out"} and (before_record_id or before_status != event.status):
            removed += 1
            affected.append(event.event_id)
        elif event.user_keep:
            kept += 1
        elif result["status"] == before_status and not before_record_id:
            skipped += 1
    return CleanupExpiredResponse(
        checked=len(events),
        removed=removed,
        kept=kept,
        skipped=skipped,
        affected_event_ids=affected,
    )


@router.post("/events/refilter-images")
def refilter_images(db: Session = Depends(get_db)) -> dict[str, Any]:
    """重新过滤所有已同步事件的海报图片（排除装饰性图片）。

    对每个已同步到飞书的事件，重新评估 poster_images，
    移除装饰性图片后更新飞书附件。
    """
    from app.services.article_service import ArticleService

    events = (
        db.query(Event)
        .options(joinedload(Event.article))
        .filter(
            Event.feishu_record_id != "",
            Event.status.notin_(EventStatus.TERMINAL_STATUSES),
        )
        .all()
    )

    article_service = ArticleService(db)
    feishu_adapter = FeishuAdapter(db)
    updated = 0
    unchanged = 0
    failed = 0
    details: list[dict[str, Any]] = []

    for event in events:
        try:
            old_images = loads_list(event.poster_images)
            old_count = len(old_images)

            changed = article_service.refilter_event_images(event)
            if not changed:
                unchanged += 1
                continue

            new_count = len(loads_list(event.poster_images))

            # 图片列表变了，重新同步到飞书（会重新上传附件）
            result = feishu_adapter.sync_event(event)
            updated += 1
            details.append({
                "event_id": event.event_id,
                "title": event.title,
                "old_count": old_count,
                "new_count": new_count,
                "sync_status": result.get("status"),
            })
        except Exception as exc:
            failed += 1
            logger.warning("Refilter failed for event %s: %s", event.event_id, exc)

    return {
        "total": len(events),
        "updated": updated,
        "unchanged": unchanged,
        "failed": failed,
        "details": details,
    }
