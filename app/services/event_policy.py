import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import Article, Event
from app.utils.constants import EventStatus, RetentionDecision, EventTimeStatus
from app.utils.time import parse_datetime_str, SHANGHAI_TZ
RECAP_KEYWORDS = (
    "回顾",
    "总结",
    "综述",
    "纪实",
    "纪要",
    "风采",
    "顺利举行",
    "圆满举行",
    "圆满落幕",
    "圆满结束",
    "圆满收官",
    "成功举办",
    "顺利开展",
    "圆满完成",
    "精彩回顾",
    "活动回顾",
    "活动总结",
    "成果展示",
    "风采展示",
    "标兵",
    "人物专访",
    "事迹介绍",
)
RECRUITMENT_KEYWORDS = (
    "招募",
    "招新",
    "报名",
    "征集",
    "征稿",
    "招聘",
    "申请",
)
ANNOUNCEMENT_KEYWORDS = (
    "通知",
    "预告",
    "讲座",
    "活动",
    "培训",
    "比赛",
    "大赛",
    "专场",
    "宣讲",
    "启动",
    "截止",
)


@dataclass
class ArticleGateDecision:
    article_type: str
    article_type_reason: str
    retention_decision: str
    should_skip: bool


@dataclass
class EventPolicyDecision:
    article_type: str
    article_type_reason: str
    event_time_status: str
    retention_decision: str
    should_remove_from_feishu: bool


def now_shanghai() -> datetime:
    return datetime.now(SHANGHAI_TZ)


def classify_article_type(title: str, content: str) -> tuple[str, str]:
    haystack = f"{title}\n{content}"
    for keyword in RECAP_KEYWORDS:
        if keyword in haystack:
            return "recap", keyword
    for keyword in RECRUITMENT_KEYWORDS:
        if keyword in haystack:
            return "recruitment", keyword
    for keyword in ANNOUNCEMENT_KEYWORDS:
        if keyword in haystack:
            return "announcement", keyword
    return "other", ""


def evaluate_article_gate(title: str, content: str, publish_time: str) -> ArticleGateDecision:
    article_type, reason = classify_article_type(title, content)
    published_at = parse_datetime(publish_time)
    now = now_shanghai()
    if published_at and now - published_at > timedelta(days=60):
        return ArticleGateDecision(article_type, reason, RetentionDecision.SKIP_OLDER_THAN_60_DAYS, True)
    if article_type in {"announcement", "recruitment", "other"} and published_at and now - published_at > timedelta(days=30):
        return ArticleGateDecision(article_type, reason, RetentionDecision.SKIP_OLDER_THAN_30_DAYS, True)
    return ArticleGateDecision(article_type, reason, RetentionDecision.KEEP, False)


def parse_datetime(value: str) -> datetime | None:
    """解析时间字符串，委托给统一的 parse_datetime_str。"""
    return parse_datetime_str(value)


def event_time_status(start_time: str, end_time: str) -> str:
    """根据开始/结束时间判断事件的时间状态。

    返回值：
    - unknown:  无任何时间信息
    - upcoming: 开始时间在未来
    - ongoing:  当前时间在 start_time 和 end_time 之间
    - ended:    结束时间在过去 7 天内
    - expired:  结束时间在 7 天前（或开始时间在 7 天前且无结束时间）
    - past:     通用回退（有时间但无法细分）
    """
    from datetime import timedelta

    end_at = parse_datetime(end_time)
    start_at = parse_datetime(start_time)
    now = now_shanghai()

    # 无任何时间信息
    if not start_at and not end_at:
        return EventTimeStatus.UNKNOWN

    # 有结束时间：基于结束时间判断
    if end_at:
        if end_at < now:
            # 已结束
            if now - end_at <= timedelta(days=7):
                return EventTimeStatus.ENDED
            return EventTimeStatus.EXPIRED
        # 结束时间在未来
        if start_at and start_at <= now:
            return EventTimeStatus.ONGOING
        return EventTimeStatus.UPCOMING

    # 只有开始时间
    if start_at:
        if start_at < now:
            # 开始时间已过，无结束时间 → 假设活动已结束
            if now - start_at <= timedelta(days=7):
                return EventTimeStatus.ENDED
            return EventTimeStatus.EXPIRED
        return EventTimeStatus.UPCOMING

    return EventTimeStatus.UNKNOWN


class EventPolicyService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def apply(self, event: Event) -> EventPolicyDecision:
        # 归档事件不走策略引擎，直接返回当前状态
        if event.status == EventStatus.ARCHIVED:
            return EventPolicyDecision(
                event.article_type or "unknown",
                event.article_type_reason or "archived",
                event.event_time_status or EventTimeStatus.UNKNOWN,
                event.retention_decision or RetentionDecision.AUTO_ARCHIVED,
                False,
            )

        article = self.db.query(Article).filter(Article.article_id == event.article_id).one_or_none()
        if article is None:
            return EventPolicyDecision("unknown", "article not found", EventTimeStatus.UNKNOWN, RetentionDecision.KEEP, False)
        article_type, reason = classify_article_type(article.title or event.title, article.processed_markdown or article.raw_markdown)
        time_status = event_time_status(event.start_time, event.end_time)
        gate = evaluate_article_gate(article.title or event.title, article.processed_markdown or article.raw_markdown, article.publish_time)

        if event.user_keep:
            decision = EventPolicyDecision(article_type, reason, time_status, RetentionDecision.KEEP_USER, False)
        elif gate.retention_decision == RetentionDecision.SKIP_OLDER_THAN_60_DAYS:
            decision = EventPolicyDecision(article_type, reason, time_status, gate.retention_decision, True)
        elif article_type in {"announcement", "recruitment"} and time_status in {EventTimeStatus.PAST, EventTimeStatus.ENDED, EventTimeStatus.EXPIRED}:
            decision = EventPolicyDecision(article_type, reason, time_status, RetentionDecision.DROP_PAST_EVENT, True)
        elif gate.retention_decision == RetentionDecision.SKIP_OLDER_THAN_30_DAYS:
            decision = EventPolicyDecision(article_type, reason, time_status, gate.retention_decision, True)
        elif article_type == "recap":
            if time_status in {EventTimeStatus.UPCOMING, EventTimeStatus.ONGOING}:
                # 推文含回顾关键词但活动时间在未来或进行中，不应标记为回顾
                decision = EventPolicyDecision(article_type, reason, time_status, RetentionDecision.KEEP, False)
            else:
                # 回顾类文章：已结束的活动，不写入飞书（用户可手动 keep 恢复）
                decision = EventPolicyDecision(article_type, reason, time_status, RetentionDecision.KEEP_RECAP_LOWEST, True)
        else:
            decision = EventPolicyDecision(article_type, reason, time_status, RetentionDecision.KEEP, False)

        event.article_type = decision.article_type
        event.article_type_reason = decision.article_type_reason
        event.event_time_status = decision.event_time_status
        event.retention_decision = decision.retention_decision
        if decision.should_remove_from_feishu and not event.user_keep:
            if event.feishu_record_id:
                event.status = EventStatus.EXPIRED_HIDDEN
            else:
                event.status = EventStatus.FILTERED_OUT
        return decision
