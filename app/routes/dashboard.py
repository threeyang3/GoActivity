"""仪表板 API 路由。

提供 Web 管理界面所需的数据接口。
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Article, Event, SyncLog, SyncRun
from app.utils.constants import EventStatus

router = APIRouter(tags=["dashboard"])
logger = logging.getLogger(__name__)


@router.get("/dashboard/stats")
def get_stats(db: Session = Depends(get_db)) -> dict[str, Any]:
    """获取统计数据。"""
    # 文章统计
    total_articles = db.query(func.count(Article.id)).scalar() or 0

    # 事件统计 - 合并为单次查询
    event_stats = db.query(
        func.count(Event.id).label("total"),
        func.sum(case((Event.status == EventStatus.SYNCED, 1), else_=0)).label("synced"),
        func.sum(case((Event.status.in_([EventStatus.EXTRACTED, EventStatus.PENDING_AI]), 1), else_=0)).label("pending"),
        func.sum(case((Event.status == EventStatus.FAILED_SYNC, 1), else_=0)).label("failed"),
    ).first()

    total_events = event_stats.total if event_stats else 0
    synced_events = event_stats.synced if event_stats else 0
    pending_events = event_stats.pending if event_stats else 0
    failed_events = event_stats.failed if event_stats else 0

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
        .filter(Event.status.notin_([EventStatus.IGNORED_NON_EVENT, EventStatus.EXPIRED_HIDDEN]))
        .order_by(Event.created_at.desc())
        .limit(10)
        .all()
    )

    return {
        "articles": {"total": total_articles},
        "events": {
            "total": total_events,
            "synced": synced_events,
            "pending": pending_events,
            "failed": failed_events,
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

    query = db.query(Event)

    if status:
        query = query.filter(Event.status == status)
    else:
        # 默认排除已忽略的事件
        query = query.filter(Event.status.notin_([EventStatus.IGNORED_NON_EVENT, EventStatus.EXPIRED_HIDDEN]))

    if category:
        query = query.filter(Event.category_1 == category)

    # 时间范围筛选
    now = datetime.now(SHANGHAI_TZ)
    if time_range == "today":
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        query = query.filter(
            Event.start_time >= today_start.strftime("%Y-%m-%d"),
            Event.start_time < today_end.strftime("%Y-%m-%d"),
        )
    elif time_range == "week":
        week_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)
        query = query.filter(
            Event.start_time >= week_start.strftime("%Y-%m-%d"),
            Event.start_time < week_end.strftime("%Y-%m-%d"),
        )
    elif time_range == "month":
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1)
        query = query.filter(
            Event.start_time >= month_start.strftime("%Y-%m-%d"),
            Event.start_time < month_end.strftime("%Y-%m-%d"),
        )
    elif time_range == "upcoming":
        query = query.filter(
            Event.start_time >= now.strftime("%Y-%m-%d %H:%M:%S"),
            Event.event_time_status == "upcoming",
        )
    elif time_range == "past":
        query = query.filter(Event.event_time_status == "past")

    total = query.count()
    offset = (page - 1) * page_size
    events = query.order_by(Event.start_time.asc()).offset(offset).limit(page_size).all()

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
                "start_time": e.start_time,
                "end_time": e.end_time,
                "location": e.location,
                "status": e.status,
                "event_time_status": e.event_time_status,
                "retention_decision": e.retention_decision,
                "confidence": e.confidence,
                "feishu_record_id": e.feishu_record_id,
                "created_at": e.created_at.isoformat() if e.created_at else None,
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
        "start_time": event.start_time,
        "end_time": event.end_time,
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
        Event.status.notin_([EventStatus.IGNORED_NON_EVENT, EventStatus.EXPIRED_HIDDEN]),
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
    from datetime import datetime, timedelta
    from app.utils.time import SHANGHAI_TZ

    now = datetime.now(SHANGHAI_TZ)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # 查找今日活动（开始时间在今天范围内）
    events = db.query(Event).filter(
        Event.status.notin_([EventStatus.IGNORED_NON_EVENT, EventStatus.EXPIRED_HIDDEN]),
        Event.start_time >= today_start.strftime("%Y-%m-%d"),
        Event.start_time < today_end.strftime("%Y-%m-%d"),
    ).order_by(Event.start_time.asc()).all()

    # 查找即将到来的活动（未来 7 天）
    week_end = today_start + timedelta(days=7)
    upcoming_events = db.query(Event).filter(
        Event.status.notin_([EventStatus.IGNORED_NON_EVENT, EventStatus.EXPIRED_HIDDEN]),
        Event.start_time >= today_end.strftime("%Y-%m-%d"),
        Event.start_time < week_end.strftime("%Y-%m-%d"),
    ).order_by(Event.start_time.asc()).limit(10).all()

    return {
        "today": [
            {
                "event_id": e.event_id,
                "title": e.title or "(无标题)",
                "category_1": e.category_1,
                "start_time": e.start_time,
                "end_time": e.end_time,
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
                "start_time": e.start_time,
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
def get_feishu_link() -> dict[str, Any]:
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
        "app_token": app_token,
        "table_id": table_id,
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
