"""项目级共享常量。"""

# 活动类型中英文映射
ACTIVITY_KIND_LABELS: dict[str, str] = {
    "volunteer_recruitment": "志愿者招募",
    "lecture": "讲座",
    "performance": "演出·放映",
    "competition": "比赛·征稿",
    "general_recruitment": "普通招募",
    "general_event": "普通活动",
    "non_event": "非活动",
}


def activity_kind_label(kind: str) -> str:
    """活动类型编码 → 中文标签，未知类型返回 '普通活动'。"""
    return ACTIVITY_KIND_LABELS.get(kind or "", "普通活动")


# ---------------------------------------------------------------------------
# 事件状态常量
# ---------------------------------------------------------------------------

class EventStatus:
    """事件状态枚举。"""
    PENDING = "pending"
    PENDING_AI = "pending_ai"
    EXTRACTED = "extracted"
    SYNCED = "synced"
    FAILED_EXTRACT = "failed_extract"
    FAILED_SYNC = "failed_sync"
    IGNORED_NON_EVENT = "ignored_non_event"
    EXPIRED_HIDDEN = "expired_hidden"
    FILTERED_OUT = "filtered_out"
    NEEDS_IMAGE_RETRY = "needs_image_retry"

    # 需要排除的状态（不显示在活动列表中）
    TERMINAL_STATUSES = {IGNORED_NON_EVENT, EXPIRED_HIDDEN, FILTERED_OUT}

    # 已同步到飞书的状态
    SYNCED_STATUSES = {SYNCED, EXTRACTED}


# ---------------------------------------------------------------------------
# 保留决策常量
# ---------------------------------------------------------------------------

class RetentionDecision:
    """保留决策枚举。"""
    KEEP = "keep"
    KEEP_USER = "keep_user"
    KEEP_RECAP = "keep_recap"
    KEEP_RECAP_LOWEST = "keep_recap_lowest"
    DROP_PAST_EVENT = "drop_past_event"
    SKIP_OLDER_THAN_30_DAYS = "skip_older_than_30_days"
    SKIP_OLDER_THAN_60_DAYS = "skip_older_than_60_days"


# ---------------------------------------------------------------------------
# 时间状态常量
# ---------------------------------------------------------------------------

class EventTimeStatus:
    """事件时间状态枚举。"""
    UNKNOWN = "unknown"
    UPCOMING = "upcoming"
    PAST = "past"
    ONGOING = "ongoing"
    ENDED = "ended"
    EXPIRED = "expired"
    SCHEDULED = "scheduled"
