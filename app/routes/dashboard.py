"""仪表板 API 路由。"""

import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from app.auth import require_admin
from app.config import get_settings
from app.db import get_db
from app.models import Article, Event, SyncLog, SyncRun
from app.utils.constants import EventStatus
from app.utils.time import SHANGHAI_TZ, format_display_datetime, from_storage_datetime, parse_datetime_str

router = APIRouter(tags=["dashboard"])
logger = logging.getLogger(__name__)


def _event_start_dt(event: Event) -> datetime | None:
    return from_storage_datetime(event.start_at, event.timezone or "Asia/Shanghai") or parse_datetime_str(event.start_time)


def _event_end_dt(event: Event) -> datetime | None:
    return from_storage_datetime(event.end_at, event.timezone or "Asia/Shanghai") or parse_datetime_str(event.end_time)


def _event_start_text(event: Event) -> str:
    return format_display_datetime(event.start_at, event.timezone or "Asia/Shanghai") or event.start_time


def _event_end_text(event: Event) -> str:
    return format_display_datetime(event.end_at, event.timezone or "Asia/Shanghai") or event.end_time


def _in_time_range(event: Event, time_range: str | None) -> bool:
    if not time_range:
        return True
    now = datetime.now(SHANGHAI_TZ)
    start_dt = _event_start_dt(event)
    if time_range == "past":
        return event.event_time_status == "past"
    if not start_dt:
        return False
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if time_range == "today":
        return today_start <= start_dt < today_start + timedelta(days=1)
    if time_range == "week":
        return today_start <= start_dt < today_start + timedelta(days=7)
    if time_range == "month":
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1)
        return month_start <= start_dt < month_end
    if time_range == "upcoming":
        return start_dt >= now and event.event_time_status == "upcoming"
    return True


@router.get("/dashboard/stats")
def get_stats(db: Session = Depends(get_db)) -> dict[str, Any]:
    """获取统计数据。"""
    # 文章统计
    total_articles = db.query(func.count(Article.id)).scalar() or 0

    # 事件统计 - 合并为单次查询
    event_stats = db.query(
        func.count(Event.id).label("total"),
        func.coalesce(func.sum(case((Event.status.notin_(EventStatus.TERMINAL_STATUSES), 1), else_=0)), 0).label("active"),
        func.coalesce(func.sum(case((Event.status == EventStatus.SYNCED, 1), else_=0)), 0).label("synced"),
        func.coalesce(func.sum(case((Event.status.in_([EventStatus.EXTRACTED, EventStatus.PENDING_AI]), 1), else_=0)), 0).label("pending"),
        func.coalesce(func.sum(case((Event.status == EventStatus.FAILED_SYNC, 1), else_=0)), 0).label("failed_sync"),
        func.coalesce(func.sum(case((Event.status == EventStatus.FAILED_EXTRACT, 1), else_=0)), 0).label("failed_extract"),
        func.coalesce(func.sum(case((Event.status == EventStatus.NEEDS_IMAGE_RETRY, 1), else_=0)), 0).label("needs_image_retry"),
        func.coalesce(func.sum(case((Event.status == EventStatus.ARCHIVED, 1), else_=0)), 0).label("archived"),
    ).first()

    total_events = event_stats.total if event_stats else 0
    active_events = event_stats.active if event_stats else 0
    synced_events = event_stats.synced if event_stats else 0
    pending_events = event_stats.pending if event_stats else 0
    failed_sync_events = event_stats.failed_sync if event_stats else 0
    failed_extract_events = event_stats.failed_extract if event_stats else 0
    needs_image_retry_events = event_stats.needs_image_retry if event_stats else 0
    archived_events = event_stats.archived if event_stats else 0
    failed_events = failed_sync_events + failed_extract_events + needs_image_retry_events
    review_events = pending_events + failed_extract_events + needs_image_retry_events

    # 最近同步
    latest_run = db.query(SyncRun).order_by(SyncRun.started_at.desc()).first()
    latest_sync = None
    if latest_run:
        latest_sync = {
            "run_id": latest_run.run_id,
            "source": latest_run.source,
            "status": latest_run.status,
            "started_at": latest_run.started_at.isoformat() if latest_run.started_at else None,
            "imported_count": latest_run.imported_count,
        }

    # 最近事件
    recent_events = (
        db.query(Event)
        .filter(Event.status.notin_(EventStatus.TERMINAL_STATUSES))
        .order_by(Event.created_at.desc())
        .limit(10)
        .all()
    )

    return {
        "articles": {"total": total_articles},
        "events": {
            "total": total_events,
            "active": active_events,
            "synced": synced_events,
            "pending": pending_events,
            "failed": failed_events,
            "review": review_events,
            "failed_sync": failed_sync_events,
            "failed_extract": failed_extract_events,
            "needs_image_retry": needs_image_retry_events,
            "archived": archived_events,
        },
        "latest_sync": latest_sync,
        "recent_events": [
            {
                "event_id": e.event_id,
                "title": e.title or "(无标题)",
                "category_1": e.category_1,
                "start_time": e.start_time,
                "status": e.status,
                "event_time_status": e.event_time_status,
            }
            for e in recent_events
        ],
    }


@router.get("/dashboard/events")
def list_events(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    category: str | None = None,
    activity_kind: str | None = None,
    time_range: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """分页获取事件列表。

    time_range: 时间范围筛选
    - today: 今日活动
    - week: 本周活动
    - month: 本月活动
    - upcoming: 即将到来
    - past: 已结束
    """
    from datetime import datetime, timedelta
    from app.utils.time import SHANGHAI_TZ

    query = db.query(Event).options(joinedload(Event.article))

    if status:
        query = query.filter(Event.status == status)
    else:
        # 默认排除终态事件（已忽略、已过期隐藏、已过滤、已归档）
        query = query.filter(Event.status.notin_(EventStatus.TERMINAL_STATUSES))

    # 默认视图（无 time_range 筛选时）排除已过期事件，避免过期活动堆积在列表中
    if not time_range and not status:
        query = query.filter(Event.event_time_status != "expired")

    if category:
        query = query.filter(Event.category_1 == category)

    if activity_kind:
        query = query.filter(Event.activity_kind == activity_kind)

    events = query.all()
    events = [event for event in events if _in_time_range(event, time_range)]
    events.sort(key=lambda item: _event_start_dt(item) or datetime.max.replace(tzinfo=SHANGHAI_TZ))
    total = len(events)
    offset = (page - 1) * page_size
    events = events[offset:offset + page_size]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "items": [
            {
                "event_id": e.event_id,
                "article_id": e.article_id,
                "title": e.title or "(无标题)",
                "category_1": e.category_1,
                "category_2": e.category_2,
                "activity_kind": e.activity_kind,
                "start_time": _event_start_text(e),
                "end_time": _event_end_text(e),
                "location": e.location,
                "organizer": e.organizer,
                "speaker": e.speaker,
                "summary": e.summary,
                "status": e.status,
                "event_time_status": e.event_time_status,
                "retention_decision": e.retention_decision,
                "confidence": e.confidence,
                "feishu_record_id": e.feishu_record_id,
                "user_keep": e.user_keep,
                "user_participate": e.user_participate,
                "archived_at": e.archived_at.isoformat() if e.archived_at else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "mp_name": e.article.mp_name if e.article else "",
            }
            for e in events
        ],
    }


@router.get("/dashboard/events/{event_id}")
def get_event_detail(event_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """获取活动详情。"""
    from app.utils.jsonx import loads_list

    event = db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        return {"error": "Event not found"}

    # 获取关联文章
    article = None
    if event.article_id:
        from app.models import Article
        article = db.query(Article).filter(Article.article_id == event.article_id).first()

    return {
        "event_id": event.event_id,
        "article_id": event.article_id,
        "title": event.title or "(无标题)",
        "category_1": event.category_1,
        "category_2": event.category_2,
        "activity_kind": event.activity_kind,
        "activity_kind_reason": event.activity_kind_reason,
        "start_time": _event_start_text(event),
        "end_time": _event_end_text(event),
        "start_at": format_display_datetime(event.start_at, event.timezone or "Asia/Shanghai"),
        "end_at": format_display_datetime(event.end_at, event.timezone or "Asia/Shanghai"),
        "timezone": event.timezone,
        "raw_time_text": event.raw_time_text,
        "location": event.location,
        "speaker": event.speaker,
        "organizer": event.organizer,
        "registration": event.registration,
        "summary": event.summary,
        "article_type": event.article_type,
        "article_type_reason": event.article_type_reason,
        "is_event_related": event.is_event_related,
        "relevance_reason": event.relevance_reason,
        "event_time_status": event.event_time_status,
        "retention_decision": event.retention_decision,
        "user_keep": event.user_keep,
        "tags": loads_list(event.tags),
        "poster_images": loads_list(event.poster_images),
        "cover_image": event.cover_image,
        "ocr_text": event.ocr_text[:500] if event.ocr_text else "",
        "vision_result": event.vision_result,
        "source_url": event.source_url,
        "status": event.status,
        "confidence": event.confidence,
        "feishu_record_id": event.feishu_record_id,
        "dedup_key": event.dedup_key,
        "user_participate": event.user_participate,
        "archived_at": event.archived_at.isoformat() if event.archived_at else None,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "updated_at": event.updated_at.isoformat() if event.updated_at else None,
        # 演出信息
        "performance_type": event.performance_type,
        "performance_name": event.performance_name,
        "performer": event.performer,
        "ticket_info": event.ticket_info,
        # 讲座信息
        "lecture_topic": event.lecture_topic,
        "speaker_title": event.speaker_title,
        "lecture_series": event.lecture_series,
        # 比赛信息
        "competition_name": event.competition_name,
        "competition_type": event.competition_type,
        "deadline": event.deadline,
        "prize_info": event.prize_info,
        # 报名信息
        "registration_url": event.registration_url,
        "registration_deadline": event.registration_deadline,
        "participant_limit": event.participant_limit,
        # 关联文章信息
        "article": {
            "title": article.title if article else "",
            "mp_name": article.mp_name if article else "",
            "publish_time": article.publish_time if article else "",
            "url": article.url if article else "",
            "pic_url": article.pic_url if article else "",
        } if article else None,
    }


@router.get("/dashboard/search")
def search_events(
    q: str = "",
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """搜索活动。"""
    if not q:
        return {"total": 0, "page": page, "page_size": page_size, "pages": 0, "items": []}

    query = db.query(Event).filter(
        Event.status.notin_(EventStatus.TERMINAL_STATUSES),
        (
            Event.title.contains(q) |
            Event.location.contains(q) |
            Event.speaker.contains(q) |
            Event.organizer.contains(q) |
            Event.summary.contains(q)
        ),
    )

    total = query.count()
    offset = (page - 1) * page_size
    events = query.order_by(Event.created_at.desc()).offset(offset).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "items": [
            {
                "event_id": e.event_id,
                "title": e.title or "(无标题)",
                "category_1": e.category_1,
                "start_time": e.start_time,
                "location": e.location,
                "speaker": e.speaker,
                "status": e.status,
                "event_time_status": e.event_time_status,
                "confidence": e.confidence,
            }
            for e in events
        ],
    }


@router.get("/dashboard/today")
def get_today_events(db: Session = Depends(get_db)) -> dict[str, Any]:
    """获取今日活动。"""
    now = datetime.now(SHANGHAI_TZ)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # 查找今日活动（开始时间在今天范围内）
    events = [
        event for event in db.query(Event).filter(Event.status.notin_(EventStatus.TERMINAL_STATUSES)).all()
        if _event_start_dt(event) and today_start <= _event_start_dt(event) < today_end
    ]
    events.sort(key=lambda item: _event_start_dt(item) or datetime.max.replace(tzinfo=SHANGHAI_TZ))

    # 查找即将到来的活动（未来 7 天）
    week_end = today_start + timedelta(days=7)
    upcoming_events = [
        event for event in db.query(Event).filter(Event.status.notin_(EventStatus.TERMINAL_STATUSES)).all()
        if _event_start_dt(event) and today_end <= _event_start_dt(event) < week_end
    ]
    upcoming_events.sort(key=lambda item: _event_start_dt(item) or datetime.max.replace(tzinfo=SHANGHAI_TZ))
    upcoming_events = upcoming_events[:10]

    return {
        "today": [
            {
                "event_id": e.event_id,
                "title": e.title or "(无标题)",
                "category_1": e.category_1,
                "start_time": _event_start_text(e),
                "end_time": _event_end_text(e),
                "location": e.location,
                "speaker": e.speaker,
                "status": e.status,
            }
            for e in events
        ],
        "upcoming": [
            {
                "event_id": e.event_id,
                "title": e.title or "(无标题)",
                "category_1": e.category_1,
                "start_time": _event_start_text(e),
                "location": e.location,
                "status": e.status,
            }
            for e in upcoming_events
        ],
    }


@router.get("/dashboard/pending")
def get_pending_items(db: Session = Depends(get_db)) -> dict[str, Any]:
    """获取待办事项。"""
    # 低置信度事件（需要人工审核）
    low_confidence = db.query(Event).filter(
        Event.confidence < 0.3,
        Event.confidence > 0,
        Event.status.notin_(EventStatus.TERMINAL_STATUSES),
    ).order_by(Event.created_at.desc()).limit(10).all()

    # 同步失败事件
    failed_sync = db.query(Event).filter(
        Event.status == EventStatus.FAILED_SYNC,
    ).order_by(Event.updated_at.desc()).limit(10).all()

    # 待处理事件（已抽取但未同步）
    pending_sync = db.query(Event).filter(
        Event.status.in_([EventStatus.EXTRACTED, EventStatus.PENDING_AI]),
        Event.feishu_record_id == "",
    ).order_by(Event.created_at.desc()).limit(10).all()

    # 需要图片重试的事件
    needs_retry = db.query(Event).filter(
        Event.status == EventStatus.NEEDS_IMAGE_RETRY,
    ).order_by(Event.created_at.desc()).limit(10).all()

    return {
        "low_confidence": {
            "count": len(low_confidence),
            "items": [
                {
                    "event_id": e.event_id,
                    "title": e.title or "(无标题)",
                    "confidence": e.confidence,
                    "category_1": e.category_1,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in low_confidence
            ],
        },
        "failed_sync": {
            "count": len(failed_sync),
            "items": [
                {
                    "event_id": e.event_id,
                    "title": e.title or "(无标题)",
                    "status": e.status,
                    "updated_at": e.updated_at.isoformat() if e.updated_at else None,
                }
                for e in failed_sync
            ],
        },
        "pending_sync": {
            "count": len(pending_sync),
            "items": [
                {
                    "event_id": e.event_id,
                    "title": e.title or "(无标题)",
                    "category_1": e.category_1,
                    "start_time": e.start_time,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in pending_sync
            ],
        },
        "needs_retry": {
            "count": len(needs_retry),
            "items": [
                {
                    "event_id": e.event_id,
                    "title": e.title or "(无标题)",
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in needs_retry
            ],
        },
    }


@router.get("/dashboard/sync-logs")
def list_sync_logs(
    limit: int = 20,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """获取最近的同步日志。"""
    logs = db.query(SyncLog).order_by(SyncLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": log.id,
            "target": log.target,
            "target_id": log.target_id,
            "return_code": log.return_code,
            "stdout_preview": log.stdout[:200] if log.stdout else "",
            "stderr_preview": log.stderr[:200] if log.stderr else "",
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


@router.get("/dashboard/sync-runs")
def list_sync_runs(
    limit: int = 20,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """获取最近的同步运行记录。"""
    runs = db.query(SyncRun).order_by(SyncRun.started_at.desc()).limit(limit).all()
    return [
        {
            "run_id": run.run_id,
            "source": run.source,
            "status": run.status,
            "imported_count": run.imported_count,
            "error_message": run.error_message,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
        for run in runs
    ]


@router.get("/dashboard/feishu-link")
def get_feishu_link(_auth: None = Depends(require_admin)) -> dict[str, Any]:
    """获取飞书多维表格链接。"""
    settings = get_settings()
    app_token = settings.feishu_bitable_app_token
    table_id = settings.feishu_bitable_table_id

    if not app_token:
        return {"configured": False, "url": None}

    # 飞书多维表格 URL 格式
    url = f"https://feishu.cn/base/{app_token}"
    if table_id:
        url += f"?table={table_id}"

    return {
        "configured": True,
        "url": url,
    }


@router.get("/dashboard/pipeline-status")
def get_pipeline_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    """获取数据管道状态 — 用于管理页面顶部的状态指示器。"""
    import requests as http_requests
    from app.config import get_settings

    settings = get_settings()

    # 1. we-mp-rss 服务健康检查
    rss_online = False
    try:
        resp = http_requests.get(
            f"{settings.we_mp_rss_base_url}/api/docs", timeout=3
        )
        rss_online = resp.status_code == 200
    except Exception as exc:
        logger.debug("we-mp-rss health check failed: %s", exc)

    # 2. 最新文章入库时间
    latest_article = (
        db.query(Article)
        .order_by(Article.created_at.desc())
        .first()
    )
    latest_article_ingested_at = (
        latest_article.created_at.isoformat() if latest_article else None
    )
    latest_article_mp_name = latest_article.mp_name if latest_article else None

    # 3. 最新文章的公众号发布时间
    # publish_time 格式不统一，取最近 created_at 的那篇的 publish_time
    latest_publish_time = latest_article.publish_time if latest_article else None

    # 3.5 文章新鲜度检查：如果最新文章超过 N 天未更新，说明 we-mp-rss 可能停止抓取
    article_stale_days = None
    article_stale_warning = False
    if latest_article and latest_article.created_at:
        from datetime import datetime, timezone
        age = datetime.now(timezone.utc) - latest_article.created_at.replace(tzinfo=timezone.utc)
        article_stale_days = age.days
        if article_stale_days >= 3:
            article_stale_warning = True

    # 4. 最后一次同步运行记录
    latest_run = db.query(SyncRun).order_by(SyncRun.started_at.desc()).first()
    last_sync = None
    if latest_run:
        last_sync = {
            "run_id": latest_run.run_id,
            "source": latest_run.source,
            "status": latest_run.status,
            "started_at": latest_run.started_at.isoformat() if latest_run.started_at else None,
            "completed_at": latest_run.completed_at.isoformat() if latest_run.completed_at else None,
            "imported_count": latest_run.imported_count,
        }

    # 5. 自动同步配置
    auto_sync_cron = settings.auto_sync_cron or ""

    # 6. 待同步事件数
    pending_sync_count = (
        db.query(func.count(Event.id))
        .filter(
            Event.status.in_([EventStatus.EXTRACTED, EventStatus.PENDING_AI]),
            Event.feishu_record_id == "",
        )
        .scalar()
        or 0
    )
    failed_sync_retry_count = (
        db.query(func.count(Event.id))
        .filter(
            Event.status == EventStatus.FAILED_SYNC,
            Event.feishu_retry_count < settings.feishu_sync_retry_max,
        )
        .scalar()
        or 0
    )
    failed_sync_exhausted_count = (
        db.query(func.count(Event.id))
        .filter(
            Event.status == EventStatus.FAILED_SYNC,
            Event.feishu_retry_count >= settings.feishu_sync_retry_max,
        )
        .scalar()
        or 0
    )

    # 7. 文章总数
    total_articles = db.query(func.count(Article.id)).scalar() or 0

    # 9. 已归档事件数
    archived_count = (
        db.query(func.count(Event.id))
        .filter(Event.status == EventStatus.ARCHIVED)
        .scalar()
        or 0
    )

    # 10. 自动归档配置
    auto_archive_days = settings.auto_archive_expired_days

    # 8. 飞书配置状态
    feishu_configured = bool(settings.feishu_bitable_app_token)

    return {
        "rss_online": rss_online,
        "rss_url": settings.we_mp_rss_base_url,
        "total_articles": total_articles,
        "latest_article_ingested_at": latest_article_ingested_at,
        "latest_article_mp_name": latest_article_mp_name,
        "latest_publish_time": latest_publish_time,
        "article_stale_days": article_stale_days,
        "article_stale_warning": article_stale_warning,
        "last_sync": last_sync,
        "auto_sync_cron": auto_sync_cron,
        "pending_sync_count": pending_sync_count,
        "failed_sync_retry_count": failed_sync_retry_count,
        "failed_sync_exhausted_count": failed_sync_exhausted_count,
        "feishu_configured": feishu_configured,
        "archived_count": archived_count,
        "auto_archive_expired_days": auto_archive_days,
    }


@router.get("/dashboard/accuracy")
def get_accuracy_stats(db: Session = Depends(get_db)) -> dict[str, Any]:
    """获取抽取准确率统计。"""
    from sqlalchemy import case

    # 置信度分布
    confidence_distribution = db.query(
        case(
            (Event.confidence < 0.3, "low"),
            (Event.confidence < 0.7, "medium"),
            else_="high"
        ).label("level"),
        func.count(Event.id).label("count"),
    ).filter(
        Event.status.notin_(EventStatus.TERMINAL_STATUSES),
        Event.confidence > 0,
    ).group_by("level").all()

    # 分类分布
    category_distribution = db.query(
        Event.category_1,
        func.count(Event.id).label("count"),
    ).filter(
        Event.status.notin_(EventStatus.TERMINAL_STATUSES),
    ).group_by(Event.category_1).all()

    # 活动类型分布
    activity_kind_distribution = db.query(
        Event.activity_kind,
        func.count(Event.id).label("count"),
    ).filter(
        Event.status.notin_(EventStatus.TERMINAL_STATUSES),
    ).group_by(Event.activity_kind).all()

    # 状态分布
    status_distribution = db.query(
        Event.status,
        func.count(Event.id).label("count"),
    ).group_by(Event.status).all()

    # 低置信度事件（可能需要人工审核）
    low_confidence_count = db.query(func.count(Event.id)).filter(
        Event.confidence < 0.3,
        Event.confidence > 0,
        Event.status.notin_(EventStatus.TERMINAL_STATUSES),
    ).scalar() or 0

    # 总数
    total_events = db.query(func.count(Event.id)).scalar() or 0
    total_with_confidence = db.query(func.count(Event.id)).filter(
        Event.confidence > 0,
    ).scalar() or 0

    return {
        "total_events": total_events,
        "total_with_confidence": total_with_confidence,
        "low_confidence_count": low_confidence_count,
        "confidence_distribution": [
            {"level": row.level, "count": row.count}
            for row in confidence_distribution
        ],
        "category_distribution": [
            {"category": row.category_1 or "未分类", "count": row.count}
            for row in category_distribution
        ],
        "activity_kind_distribution": [
            {"kind": row.activity_kind, "count": row.count}
            for row in activity_kind_distribution
        ],
        "status_distribution": [
            {"status": row.status, "count": row.count}
            for row in status_distribution
        ],
    }


@router.get("/dashboard/history")
def get_history(
    page: int = 1,
    page_size: int = 20,
    month: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """获取历史活动（已归档/已过期/已结束）。"""
    query = db.query(Event).filter(
        Event.status.in_(["archived", "expired_hidden"])
        | (Event.event_time_status.in_(["expired", "ended", "past"]))
    )

    if month:
        # month format: "2026-06"
        events_for_month = query.all()
        query = None
        events_for_month = [event for event in events_for_month if _event_start_text(event).startswith(f"{month}")]
    else:
        events_for_month = query.all()
    events_for_month.sort(key=lambda item: _event_start_dt(item) or datetime.min.replace(tzinfo=SHANGHAI_TZ), reverse=True)
    total = len(events_for_month)
    offset = (page - 1) * page_size
    events = events_for_month[offset:offset + page_size]

    # 获取可用月份列表
    months = (
        db.query(Event).filter(Event.start_time != "").all()
    )
    available_months = sorted(
        set(_event_start_text(event)[:7] for event in months if _event_start_text(event) and len(_event_start_text(event)) >= 7),
        reverse=True,
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total > 0 else 0,
        "months": available_months,
        "available_months": available_months,
        "items": [
            {
                "event_id": e.event_id,
                "title": e.title or "(无标题)",
                "category_1": e.category_1,
                "start_time": _event_start_text(e),
                "end_time": _event_end_text(e),
                "location": e.location,
                "status": e.status,
                "event_time_status": e.event_time_status,
                "archived_at": e.archived_at.isoformat() if e.archived_at else None,
            }
            for e in events
        ],
    }


@router.get("/dashboard/accounts-health")
def get_accounts_health(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """获取各公众号的健康状态。"""
    from app.services.automation_guard import AutomationGuardService

    return AutomationGuardService(db).account_health()
