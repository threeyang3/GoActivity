"""校园活动日报/周报服务。

支持按时间筛选、分类统计、分组输出。
"""

from collections import Counter
from datetime import datetime, timedelta
from itertools import groupby

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Event
from app.utils.constants import ACTIVITY_KIND_LABELS
from app.utils.jsonx import loads_list
from app.utils.time import utcnow

# 可见的活动状态（排除已忽略和已过期）
VISIBLE_EVENT_STATUSES = (
    "pending",
    "pending_ai",
    "needs_image_retry",
    "extracted",
    "synced",
    "failed_sync",
    "failed_extract",
)

# 保留决策优先级（用于排序）
_RETENTION_DECISION_PRIORITY = {
    "keep": 1,           # 正常保留
    "keep_user": 2,      # 用户手动保留
    "keep_recap": 3,     # 回顾类文章（低优先级）
    "keep_recap_lowest": 4,  # 回顾类文章（最低优先级）
}

# 时间字符串解析格式（按优先级尝试）
_TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
)


def _parse_time(time_str: str | None) -> datetime | None:
    """将时间字符串解析为 datetime 对象。解析失败返回 None。"""
    if not time_str:
        return None
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue
    return None


class ReportService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.now = utcnow()
        self.today = self.now.date()

    def daily_report(self) -> str:
        """生成今日活动日报。"""
        return self._generate_report(
            days=1,
            title=f"# 校园活动日报 {self.today.isoformat()}",
            subtitle="",
            top_n=5,
            recap_limit=5,
            show_status_stats=False,
        )

    def weekly_report(self) -> str:
        """生成本周活动周报。"""
        return self._generate_report(
            days=7,
            title="# 校园活动周报",
            subtitle=f"报告周期：{self._week_start().isoformat()} ~ {self.today.isoformat()}",
            top_n=10,
            recap_limit=10,
            show_status_stats=True,
        )

    def _generate_report(
        self,
        days: int,
        title: str,
        subtitle: str,
        top_n: int,
        recap_limit: int,
        show_status_stats: bool,
    ) -> str:
        """日报/周报的公共生成逻辑。"""
        events = self._query_events_for_period(days=days)
        stats = self._compute_stats(events)

        # 分离正常活动和回顾类活动
        normal_events = [e for e in events if e.retention_decision not in ("keep_recap", "keep_recap_lowest")]
        recap_events = [e for e in events if e.retention_decision in ("keep_recap", "keep_recap_lowest")]

        lines = [title]
        if subtitle:
            lines.append(subtitle)
        lines.extend([
            "",
            "## 📊 概览",
            f"- 活动总数：{stats['total']} 场",
            f"- 新录入：{stats['new_count']} 条",
            f"- 即将开始：{stats['upcoming']} 场",
            f"- 进行中：{stats['ongoing']} 场",
            f"- 已结束/回顾：{len(recap_events)} 条",
            "",
        ])

        # 分类统计（只统计正常活动）
        normal_kind_stats = Counter(e.activity_kind for e in normal_events if e.activity_kind)
        if normal_kind_stats:
            lines.append("## 📈 分类统计")
            for kind, count in normal_kind_stats.most_common():
                label = ACTIVITY_KIND_LABELS.get(kind, kind)
                lines.append(f"- {label}：{count} 场")
            lines.append("")

        # 状态统计（仅周报）
        if show_status_stats and stats["by_status"]:
            lines.append("## 📊 状态统计")
            for status, count in stats["by_status"].most_common():
                lines.append(f"- {status}：{count} 条")
            lines.append("")

        # 推荐活动（置信度最高的 Top N，排除回顾类）
        top_events = sorted(normal_events, key=lambda e: e.confidence or 0, reverse=True)[:top_n]
        if top_events:
            lines.append(f"## ⭐ 推荐 TOP{top_n}")
            for i, event in enumerate(top_events, 1):
                lines.append(f"{i}. **{event.title or '未命名活动'}**")
                lines.extend(self._format_event_detail(event))
            lines.append("")

        # 按活动类型分组（正常活动）
        lines.append("## 📋 活动列表")
        if not normal_events:
            lines.append("暂无活动。")
        else:
            sorted_events = sorted(normal_events, key=lambda e: e.activity_kind or "")
            for kind, kind_events in groupby(sorted_events, key=lambda e: e.activity_kind):
                kind_label = ACTIVITY_KIND_LABELS.get(kind, kind)
                kind_list = list(kind_events)
                lines.append(f"\n### {kind_label}（{len(kind_list)} 场）")
                for event in kind_list:
                    lines.append(f"- **{event.title or '未命名活动'}**")
                    lines.extend(self._format_event_detail(event, indent=2))

        # 回顾类活动（单独分组，放在最后）
        if recap_events:
            lines.append("\n## 📰 近期回顾")
            lines.append("（已结束的活动，仅供参考）")
            for event in recap_events[:recap_limit]:
                lines.append(f"- {event.title or '未命名活动'}")
            if len(recap_events) > recap_limit:
                lines.append(f"- ... 还有 {len(recap_events) - recap_limit} 条")

        return "\n".join(lines)

    def _query_events_for_period(self, days: int) -> list[Event]:
        """查询指定时间范围内的活动。

        查询条件：
        1. 开始时间在时间范围内
        2. 结束时间在时间范围内
        3. 创建时间在时间范围内（新录入）
        排除 ignored_non_event 和 expired
        """
        period_start = self.today - timedelta(days=days - 1)
        period_end = self.today + timedelta(days=1)  # 包含今天

        # 查询条件
        conditions = [
            # 开始时间在范围内
            Event.start_time.between(
                period_start.isoformat(),
                period_end.isoformat(),
            ),
            # 结束时间在范围内
            Event.end_time.between(
                period_start.isoformat(),
                period_end.isoformat(),
            ),
            # 创建时间在范围内（新录入）
            Event.created_at.between(
                datetime.combine(period_start, datetime.min.time()),
                datetime.combine(period_end, datetime.min.time()),
            ),
        ]

        # 排除的状态
        exclude_statuses = ("ignored_non_event", "expired_hidden", "filtered_out")

        query = (
            self.db.query(Event)
            .filter(
                or_(*conditions),
                Event.status.notin_(exclude_statuses),
            )
        )

        # 获取结果并按优先级排序
        events = query.all()

        # 按保留决策优先级排序（回顾类文章放最后）
        def sort_key(event: Event) -> tuple[int, str]:
            priority = _RETENTION_DECISION_PRIORITY.get(event.retention_decision, 5)
            return (priority, event.start_time or "")

        events.sort(key=sort_key)
        return events

    def _compute_stats(self, events: list[Event]) -> dict:
        """计算统计信息。"""
        # 分类统计
        by_kind = Counter(e.activity_kind for e in events if e.activity_kind)
        by_status = Counter(e.status for e in events if e.status)

        # 新录入统计（创建时间在今天）
        new_count = len([e for e in events if e.created_at and e.created_at.date() == self.today])

        # 即将开始（开始时间在未来）
        upcoming = 0
        ongoing = 0
        for e in events:
            start = _parse_time(e.start_time)
            if not start:
                continue
            if start > self.now:
                upcoming += 1
            else:
                end = _parse_time(e.end_time)
                if end and start <= self.now <= end:
                    ongoing += 1

        return {
            "total": len(events),
            "new_count": new_count,
            "upcoming": upcoming,
            "ongoing": ongoing,
            "by_kind": by_kind,
            "by_status": by_status,
        }

    def _format_event_detail(self, event: Event, indent: int = 3) -> list[str]:
        """格式化活动详情。"""
        lines = []
        prefix = " " * indent + "- "

        # 基本信息
        kind_label = ACTIVITY_KIND_LABELS.get(event.activity_kind, event.activity_kind)
        lines.append(f"{prefix}类型：{kind_label}")

        time_str = event.start_time or "时间待定"
        if event.end_time:
            time_str += f" ~ {event.end_time}"
        lines.append(f"{prefix}时间：{time_str}")

        if event.location:
            lines.append(f"{prefix}地点：{event.location}")

        if event.organizer:
            lines.append(f"{prefix}主办方：{event.organizer}")

        # 演出信息
        if event.performance_type:
            lines.append(f"{prefix}演出类型：{event.performance_type}")
        if event.performance_name:
            lines.append(f"{prefix}演出作品：{event.performance_name}")
        if event.performer:
            lines.append(f"{prefix}演出团体：{event.performer}")
        if event.ticket_info:
            lines.append(f"{prefix}票价：{event.ticket_info}")

        # 讲座信息
        if event.lecture_topic:
            lines.append(f"{prefix}讲座主题：{event.lecture_topic}")
        if event.speaker:
            lines.append(f"{prefix}主讲人：{event.speaker}")
        if event.speaker_title:
            lines.append(f"{prefix}主讲人头衔：{event.speaker_title}")
        if event.lecture_series:
            lines.append(f"{prefix}讲座系列：{event.lecture_series}")

        # 比赛信息
        if event.competition_name:
            lines.append(f"{prefix}比赛名称：{event.competition_name}")
        if event.competition_type:
            lines.append(f"{prefix}比赛类型：{event.competition_type}")
        if event.deadline:
            lines.append(f"{prefix}截止时间：{event.deadline}")
        if event.prize_info:
            lines.append(f"{prefix}奖项设置：{event.prize_info}")

        # 报名信息
        if event.registration:
            lines.append(f"{prefix}报名方式：{event.registration}")
        if event.registration_url:
            lines.append(f"{prefix}报名链接：{event.registration_url}")
        if event.registration_deadline:
            lines.append(f"{prefix}报名截止：{event.registration_deadline}")
        if event.participant_limit:
            lines.append(f"{prefix}人数限制：{event.participant_limit}")

        # 标签
        if event.tags:
            tags = loads_list(event.tags)
            if tags:
                lines.append(f"{prefix}标签：{', '.join(tags)}")

        # 摘要
        if event.summary:
            summary = event.summary[:100] + "..." if len(event.summary) > 100 else event.summary
            lines.append(f"{prefix}简介：{summary}")

        return lines

    def _week_start(self) -> datetime:
        """获取本周一的日期。"""
        return self.today - timedelta(days=self.today.weekday())
