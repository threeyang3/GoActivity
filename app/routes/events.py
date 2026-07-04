"""活动相关路由：列表、抽取、飞书同步、置顶、清理、图片重过滤。"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models import Event
from app.routes.helpers import event_to_out
from app.schemas import (
    ArchiveResponse,
    BatchRequest,
    BatchResponse,
    CleanupExpiredResponse,
    EventEditRequest,
    EventKeepResponse,
    EventOut,
    ExtractResponse,
    FeishuSyncResponse,
    ParticipateResponse,
)
from app.services.archive_service import ArchiveService
from app.services.event_extractor import EventExtractor
from app.services.event_policy import EventPolicyService
from app.services.feishu import FeishuAdapter
from app.utils.constants import EventStatus
from app.utils.jsonx import dumps_list, loads_list

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
    else:
        query = query.filter(Event.status.notin_(EventStatus.TERMINAL_STATUSES))
        # 默认排除已过期事件
        query = query.filter(Event.event_time_status != "expired")
    offset = (page - 1) * page_size
    events = query.order_by(Event.created_at.desc()).offset(offset).limit(page_size).all()
    return [event_to_out(event) for event in events]


@router.put("/events/{event_id}", response_model=EventOut)
def edit_event(
    event_id: str,
    body: EventEditRequest,
    db: Session = Depends(get_db),
) -> EventOut:
    """编辑活动信息（部分更新）。

    仅更新请求体中提供的字段，更新后重新应用策略引擎。
    如事件已同步到飞书，同步更新飞书记录。
    """
    event = (
        db.query(Event)
        .options(joinedload(Event.article))
        .filter(Event.event_id == event_id)
        .one_or_none()
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    update_fields = body.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        if field == "tags" and value is not None:
            setattr(event, field, dumps_list(value))
        else:
            setattr(event, field, value)

    # 重新应用策略引擎
    EventPolicyService(db).apply(event)
    db.flush()

    # 如已同步到飞书，同步更新
    if event.feishu_record_id:
        try:
            FeishuAdapter(db).sync_event(event)
        except Exception as exc:
            logger.warning("Feishu sync after edit failed for %s: %s", event.event_id, exc)

    db.commit()
    return event_to_out(event)


@router.post("/events/batch", response_model=BatchResponse)
def batch_events(
    body: BatchRequest,
    db: Session = Depends(get_db),
) -> BatchResponse:
    """批量操作活动：归档、同步飞书、置顶。"""
    valid_actions = {"archive", "sync", "keep"}
    if body.action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action: {body.action}")

    processed = 0
    failed = 0
    errors: list[str] = []

    for event_id in body.event_ids:
        try:
            event = (
                db.query(Event)
                .options(joinedload(Event.article))
                .filter(Event.event_id == event_id)
                .one_or_none()
            )
            if not event:
                errors.append(f"{event_id}: not found")
                failed += 1
                continue

            if body.action == "archive":
                if event.status == EventStatus.ARCHIVED:
                    processed += 1
                    continue
                ArchiveService(db).archive_event(event, source="user")
            elif body.action == "sync":
                FeishuAdapter(db).sync_event(event)
            elif body.action == "keep":
                event.user_keep = True
                if event.status in {EventStatus.EXPIRED_HIDDEN, EventStatus.FILTERED_OUT}:
                    event.status = EventStatus.EXTRACTED
                    event.retention_decision = "keep_user"

            processed += 1
        except Exception as exc:
            logger.error("Batch %s failed for event %s: %s", body.action, event_id, exc)
            errors.append(f"{event_id}: {exc}")
            failed += 1

    if body.action != "archive":
        db.commit()

    return BatchResponse(processed=processed, failed=failed, errors=errors)


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


@router.post("/events/{event_id}/participate", response_model=ParticipateResponse)
def participate_event(event_id: str, value: bool = True, db: Session = Depends(get_db)) -> ParticipateResponse:
    """标记/取消标记用户参与活动。参与的活动不会被自动归档。"""
    event = db.query(Event).filter(Event.event_id == event_id).one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event.user_participate = value
    db.commit()
    return ParticipateResponse(
        event_id=event.event_id,
        user_participate=event.user_participate,
        status=event.status,
    )


@router.post("/events/{event_id}/archive", response_model=ArchiveResponse)
def archive_event(event_id: str, db: Session = Depends(get_db)) -> ArchiveResponse:
    """手动归档事件：清除重数据，保留基本信息用于追溯。"""
    event = (
        db.query(Event)
        .options(joinedload(Event.article))
        .filter(Event.event_id == event_id)
        .one_or_none()
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.status == EventStatus.ARCHIVED:
        return ArchiveResponse(event_id=event.event_id, status="already_archived", archived_at=event.archived_at.isoformat() if event.archived_at else None, message="事件已归档")
    result = ArchiveService(db).archive_event(event, source="user")
    return ArchiveResponse(
        event_id=event.event_id,
        status=result["status"],
        archived_at=result.get("archived_at"),
        message=result.get("message", ""),
    )


@router.post("/events/{event_id}/unarchive", response_model=ArchiveResponse)
def unarchive_event(event_id: str, db: Session = Depends(get_db)) -> ArchiveResponse:
    """取消归档：恢复事件状态为 extracted。"""
    event = db.query(Event).filter(Event.event_id == event_id).one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    result = ArchiveService(db).unarchive_event(event)
    return ArchiveResponse(
        event_id=event.event_id,
        status=result["status"],
        archived_at=None,
        message=result.get("message", ""),
    )


@router.post("/events/cleanup-expired", response_model=CleanupExpiredResponse)
def cleanup_expired_events(db: Session = Depends(get_db)) -> CleanupExpiredResponse:
    """扫描所有活跃事件，将过期事件的状态更新为 expired_hidden（保留在飞书表格中）。"""
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


@router.put("/events/{event_id}")
def update_event(event_id: str, body: dict, db: Session = Depends(get_db)) -> dict:
    """编辑活动信息。"""
    from app.utils.time import utcnow

    event = (
        db.query(Event)
        .options(joinedload(Event.article))
        .filter(Event.event_id == event_id)
        .one_or_none()
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    editable_fields = [
        "title", "start_time", "end_time", "location", "category_1", "category_2",
        "activity_kind", "speaker", "organizer", "summary",
    ]
    for field in editable_fields:
        if field in body:
            setattr(event, field, body[field] or "")

    if "tags" in body and isinstance(body["tags"], list):
        from app.utils.jsonx import dumps_list
        event.tags = dumps_list(body["tags"])

    from app.services.event_policy import EventPolicyService
    EventPolicyService(db).apply(event)
    event.updated_at = utcnow()
    db.commit()

    if event.feishu_record_id:
        try:
            FeishuAdapter(db).sync_event(event)
        except Exception as exc:
            logger.warning("Failed to sync updated event to Feishu: %s", exc)

    return {"status": "updated", "event_id": event.event_id}


@router.post("/events/batch")
def batch_action(body: dict, db: Session = Depends(get_db)) -> dict:
    """批量操作活动。"""
    action = body.get("action", "")
    event_ids = body.get("event_ids", [])

    if not action or not event_ids:
        raise HTTPException(status_code=400, detail="action and event_ids required")

    processed = 0
    failed = 0
    errors = []

    for eid in event_ids:
        event = db.query(Event).filter(Event.event_id == eid).one_or_none()
        if not event:
            failed += 1
            errors.append(f"{eid}: not found")
            continue

        try:
            if action == "archive":
                ArchiveService(db).archive_event(event, source="user")
            elif action == "sync":
                FeishuAdapter(db).sync_event(event)
            elif action == "keep":
                event.user_keep = True
                db.commit()
            else:
                raise ValueError(f"Unknown action: {action}")
            processed += 1
        except Exception as exc:
            failed += 1
            errors.append(f"{eid}: {str(exc)[:80]}")

    return {"processed": processed, "failed": failed, "errors": errors}
