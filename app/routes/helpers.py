"""路由层共用的 ORM → Schema 转换函数。"""

from app.models import Event, SyncRun
from app.schemas import EventOut, SyncRunOut
from app.utils.jsonx import loads_list


def _s(v: str | None) -> str:
    """ORM None → 空字符串。"""
    return v or ""


def event_to_out(event: Event) -> EventOut:
    return EventOut(
        event_id=event.event_id,
        article_id=event.article_id,
        title=event.title,
        category_1=event.category_1,
        category_2=event.category_2,
        start_time=event.start_time,
        end_time=event.end_time,
        location=_s(event.location),
        speaker=_s(event.speaker),
        organizer=_s(event.organizer),
        registration=_s(event.registration),
        summary=_s(event.summary),
        article_type=event.article_type,
        article_type_reason=_s(event.article_type_reason),
        activity_kind=event.activity_kind,
        activity_kind_reason=_s(event.activity_kind_reason),
        is_event_related=event.is_event_related,
        relevance_reason=_s(event.relevance_reason),
        event_time_status=event.event_time_status,
        retention_decision=event.retention_decision,
        user_keep=event.user_keep,
        tags=loads_list(event.tags),
        poster_images=loads_list(event.poster_images),
        cover_image=_s(event.cover_image),
        status=event.status,
        confidence=event.confidence,
        feishu_record_id=_s(event.feishu_record_id),
        # 演出信息
        performance_type=_s(event.performance_type),
        performance_name=_s(event.performance_name),
        performer=_s(event.performer),
        ticket_info=_s(event.ticket_info),
        # 讲座信息
        lecture_topic=_s(event.lecture_topic),
        speaker_title=_s(event.speaker_title),
        lecture_series=_s(event.lecture_series),
        # 比赛信息
        competition_name=_s(event.competition_name),
        competition_type=_s(event.competition_type),
        deadline=_s(event.deadline),
        prize_info=_s(event.prize_info),
        # 报名信息
        registration_url=_s(event.registration_url),
        registration_deadline=_s(event.registration_deadline),
        participant_limit=_s(event.participant_limit),
        dedup_key=_s(event.dedup_key),
    )


def sync_run_to_out(run: SyncRun) -> SyncRunOut:
    return SyncRunOut(
        run_id=run.run_id,
        source=run.source,
        status=run.status,
        imported_count=run.imported_count,
        params_json=run.params_json,
        error_message=run.error_message,
        result_preview=run.result_preview,
        started_at=run.started_at.isoformat(),
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
    )
