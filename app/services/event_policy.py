import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import Article, Event
from app.utils.constants import EventStatus, RetentionDecision, EventTimeStatus
from app.utils.time import SHANGHAI_TZ, from_storage_datetime, parse_datetime_str, to_storage_datetime
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
    """分类文章类型。

    改进：区分"活动回顾"和"含回顾关键词的新闻报道"。
    只有标题中直接含回顾类关键词时才归类为 recap，
    正文中偶然出现的关键词不再触发 recap 分类。
    """
    title_haystack = title or ""
    content_haystack = content or ""

    # 优先检查标题中的强回顾信号（标题级关键词权重更高）
    strong_recap = ("活动回顾", "精彩回顾", "活动总结", "课程回顾", "圆满落幕", "圆满收官", "圆满结束")
    for keyword in strong_recap:
        if keyword in title_haystack:
            return "recap", keyword

    # 标题中的弱回顾信号（需同时检查内容中是否有活动时间信息）
    weak_recap_in_title = ("回顾", "总结", "综述", "纪实", "纪要", "风采展示", "成果展示")
    for keyword in weak_recap_in_title:
        if keyword in title_haystack:
            return "recap", keyword

    # 内容中的回顾信号 — 只匹配明确的活动回顾短语，不匹配单个词
    strong_content_recap = ("活动回顾", "精彩回顾", "活动总结", "圆满举行", "圆满落幕",
                            "圆满结束", "圆满收官", "成功举办", "顺利举行", "顺利开展")
    for keyword in strong_content_recap:
        if keyword in content_haystack:
            return "recap", keyword

    # 招募类
    for keyword in RECRUITMENT_KEYWORDS:
        if keyword in title_haystack:
            return "recruitment", keyword

    # 公告类
    for keyword in ANNOUNCEMENT_KEYWORDS:
        if keyword in title_haystack:
            return "announcement", keyword

    return "other", ""


def _is_article_recent(publish_time: str, days: int = 7) -> bool:
    """判断文章是否在最近 N 天内发布。"""
    published_at = parse_datetime(publish_time)
    if not published_at:
        return False
    return now_shanghai() - published_at <= timedelta(days=days)


def evaluate_article_gate(title: str, content: str, publish_time: str) -> ArticleGateDecision:
    """判断文章是否应被跳过（不入库）。

    改进：
    - 60 天以上的文章一律跳过
    - 30 天以上的公告/招募/其他跳过，但回顾类不在此处跳过（由 EventPolicyService 处理）
    - 近 7 天的文章一律不跳过
    """
    article_type, reason = classify_article_type(title, content)
    published_at = parse_datetime(publish_time)
    now = now_shanghai()

    if not published_at:
        return ArticleGateDecision(article_type, reason, RetentionDecision.KEEP, False)

    age = now - published_at

    # 近 7 天的文章一律不跳过
    if age <= timedelta(days=7):
        return ArticleGateDecision(article_type, reason, RetentionDecision.KEEP, False)

    # 超过 60 天的文章跳过
    if age > timedelta(days=60):
        return ArticleGateDecision(article_type, reason, RetentionDecision.SKIP_OLDER_THAN_60_DAYS, True)

    # 30 天以上的公告/招募/其他跳过（回顾类由 EventPolicyService 单独处理）
    if article_type in {"announcement", "recruitment", "other"} and age > timedelta(days=30):
        return ArticleGateDecision(article_type, reason, RetentionDecision.SKIP_OLDER_THAN_30_DAYS, True)

    return ArticleGateDecision(article_type, reason, RetentionDecision.KEEP, False)


def parse_datetime(value: str) -> datetime | None:
    """解析时间字符串，委托给统一的 parse_datetime_str。"""
    return parse_datetime_str(value)


def event_time_status(
    start_time: str,
    end_time: str,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    tz_name: str = "Asia/Shanghai",
) -> str:
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

    end_at = from_storage_datetime(end_at, tz_name) if end_at else parse_datetime(end_time)
    start_at = from_storage_datetime(start_at, tz_name) if start_at else parse_datetime(start_time)
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
        time_status = event_time_status(
            event.start_time,
            event.end_time,
            start_at=event.start_at,
            end_at=event.end_at,
            tz_name=event.timezone or "Asia/Shanghai",
        )
        gate = evaluate_article_gate(article.title or event.title, article.processed_markdown or article.raw_markdown, article.publish_time)
        is_recent = _is_article_recent(article.publish_time, days=7)

        if event.user_keep:
            decision = EventPolicyDecision(article_type, reason, time_status, RetentionDecision.KEEP_USER, False)
        elif gate.retention_decision == RetentionDecision.SKIP_OLDER_THAN_60_DAYS:
            decision = EventPolicyDecision(article_type, reason, time_status, gate.retention_decision, True)
        elif is_recent:
            # 近 7 天发布的文章不过滤 — 即使活动已结束，新发布的文章仍应展示
            decision = EventPolicyDecision(article_type, reason, time_status, RetentionDecision.KEEP, False)
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
        event.start_at = to_storage_datetime(event.start_time, event.timezone or "Asia/Shanghai")
        event.end_at = to_storage_datetime(event.end_time, event.timezone or "Asia/Shanghai")
        if decision.should_remove_from_feishu and not event.user_keep:
            if event.feishu_record_id:
                event.status = EventStatus.EXPIRED_HIDDEN
            else:
                event.status = EventStatus.FILTERED_OUT
        return decision
