from typing import Any

from pydantic import BaseModel, Field


class WebhookResponse(BaseModel):
    article_id: str
    event_id: str
    image_count: int
    status: str


class EventOut(BaseModel):
    event_id: str
    article_id: str
    title: str
    category_1: str
    category_2: str
    start_time: str
    end_time: str
    location: str
    speaker: str
    organizer: str
    registration: str
    summary: str
    article_type: str
    article_type_reason: str
    activity_kind: str
    activity_kind_reason: str
    is_event_related: bool
    relevance_reason: str
    event_time_status: str
    retention_decision: str
    user_keep: bool
    tags: list[str] = Field(default_factory=list)
    poster_images: list[str] = Field(default_factory=list)
    cover_image: str = ""
    status: str
    confidence: float
    feishu_record_id: str

    # 演出信息
    performance_type: str = ""
    performance_name: str = ""
    performer: str = ""
    ticket_info: str = ""

    # 讲座信息
    lecture_topic: str = ""
    speaker_title: str = ""
    lecture_series: str = ""

    # 比赛信息
    competition_name: str = ""
    competition_type: str = ""
    deadline: str = ""
    prize_info: str = ""

    # 报名信息
    registration_url: str = ""
    registration_deadline: str = ""
    participant_limit: str = ""
    dedup_key: str = ""


class ExtractResponse(BaseModel):
    event_id: str
    status: str
    result: dict[str, Any]


class FeishuSyncResponse(BaseModel):
    event_id: str
    status: str
    dry_run: bool
    stdout: str
    stderr: str


class EventKeepResponse(BaseModel):
    event_id: str
    user_keep: bool
    retention_decision: str
    status: str


class CleanupExpiredResponse(BaseModel):
    checked: int
    removed: int
    kept: int
    skipped: int
    affected_event_ids: list[str] = Field(default_factory=list)


class SyncResponse(BaseModel):
    source: str
    imported: int
    results: list[WebhookResponse] = Field(default_factory=list)


class ConfigCheckItem(BaseModel):
    key: str
    configured: bool
    source: str
    detail: str


class DiagnosticsResponse(BaseModel):
    app_name: str
    we_mp_rss_base_url: str
    checks: list[ConfigCheckItem] = Field(default_factory=list)


class SyncLogOut(BaseModel):
    id: int
    run_id: str = ""
    target: str
    target_id: str
    command: str
    return_code: int
    stdout_preview: str
    stderr_preview: str
    created_at: str


class SyncTargetSummary(BaseModel):
    target: str
    total: int
    success: int
    failed: int
    latest_created_at: str
    latest_target_id: str


class SyncFailureSummary(BaseModel):
    target: str
    target_id: str
    return_code: int
    stderr_preview: str
    created_at: str


class SyncSummaryResponse(BaseModel):
    total_logs: int
    latest_sync_at: str | None
    targets: list[SyncTargetSummary] = Field(default_factory=list)
    latest_failures: list[SyncFailureSummary] = Field(default_factory=list)


class SyncRunOut(BaseModel):
    run_id: str
    source: str
    status: str
    imported_count: int
    params_json: str
    error_message: str
    result_preview: str
    started_at: str
    completed_at: str | None


class SyncRunSummaryResponse(BaseModel):
    total_runs: int
    latest_run_at: str | None
    latest_runs: list[SyncRunOut] = Field(default_factory=list)


class ViewSetupResultItem(BaseModel):
    name: str
    action: str  # created | skipped | failed
    view_id: str = ""
    error: str = ""


class FeishuViewSetupResponse(BaseModel):
    total: int
    created: int
    updated: int = 0
    skipped: int
    failed: int
    results: list[ViewSetupResultItem] = Field(default_factory=list)
