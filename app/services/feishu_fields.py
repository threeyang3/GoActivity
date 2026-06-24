"""飞书 Bitable 字段构建与类型转换。

将 Event ORM 对象转换为飞书多维表格的字段 dict。
处理 SingleSelect/MultiSelect 白名单、DateTime 格式、URL 等类型转换。
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.models import Event
from app.services.article_service import ArticleService
from app.utils.constants import activity_kind_label
from app.utils.jsonx import loads_list
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

# SingleSelect / MultiSelect 字段的合法选项白名单。
# 飞书侧必须先在字段设置里把这些选项建好，否则 SingleSelect 写入会被飞书拒绝 (code=1254000)。
# 代码侧用白名单做防御性跳过：选项不在白名单 -> 不写该字段、记 warning，不阻塞整条 record。
SELECT_OPTIONS: dict[str, set[str]] = {
    "一级分类": {"讲座", "演出", "比赛", "招募", "展览", "工作坊", "分享会", "其他"},
    "二级分类": {"学术", "科技", "艺术", "公益", "体育", "娱乐", "招聘", "其他"},
    "活动类型": {"讲座", "演出·放映", "比赛·征稿", "志愿者招募", "普通招募", "普通活动", "非活动"},
    "状态": {"pending", "extracted", "synced", "failed_sync", "failed_extract", "ignored_non_event"},
    "时间状态": {"unknown", "scheduled", "ongoing", "ended", "expired", "upcoming", "past"},
    "保留决策": {"keep", "remove", "pending_review", "keep_recap", "keep_recap_lowest", "keep_user", "drop_past_event"},
    "标签": {"免费", "收费", "线上", "线下", "报名中", "已截止", "需审核", "学生专属", "公开", "校内", "推荐"},
}


def to_datetime_str(value: str | None) -> str | None:
    """字符串时间 -> 飞书 DateTime 格式字符串。空或无法解析时返回 None。"""
    if not value:
        return None
    v = str(value).strip()
    # 如果已经是 YYYY-MM-DD HH:MM:SS 格式，直接返回
    if len(v) == 19 and v[4] == '-' and v[7] == '-' and v[10] == ' ' and v[13] == ':' and v[16] == ':':
        return v
    # 如果是 YYYY-MM-DD 格式，加上 00:00:00
    if len(v) == 10 and v[4] == '-' and v[7] == '-':
        return f"{v} 00:00:00"
    # 其他格式，尝试解析
    epoch = ArticleService._publish_time_to_epoch(v)
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")


def select_text(field: str, value: str | None) -> str | None:
    """SingleSelect 包装。空或不在白名单时返回 None（跳过）。"""
    if not value:
        return None
    settings = get_settings()
    if field == settings.feishu_activity_kind_field:
        value = activity_kind_label(value)
    allowed = SELECT_OPTIONS.get(field)
    if allowed and value not in allowed:
        logger.warning("feishu select field %r: option %r not in whitelist, skipping", field, value)
        return None
    return value


def multi_select_texts(field: str, values: list[str] | None) -> list[str] | None:
    """MultiSelect 包装。空时返回 None；白名单外的项被丢弃并记 warning。"""
    if not values:
        return None
    allowed = SELECT_OPTIONS.get(field)
    out: list[str] = []
    for v in values:
        if not v:
            continue
        if allowed and v not in allowed:
            logger.warning("feishu multi-select field %r: option %r not in whitelist, skipping", field, v)
            continue
        out.append(v)
    return out or None


def url_link(value: str | None) -> str | None:
    """URL 字段包装。空 -> None；其他 -> 返回原文本。"""
    if not value:
        return None
    return str(value).strip()


def checkbox(value: bool | None) -> bool | None:
    return None if value is None else bool(value)


def number(value: float | int | None, digits: int = 2) -> float | None:
    if value is None or value == 0:
        return None
    return round(float(value), digits)


def build_record_fields(event: Event) -> dict[str, Any]:
    """所有写路径共用：Event -> Feishu 字段 dict。空值一律跳过。"""
    f: dict[str, Any] = {}

    def set_if(key: str, val: Any) -> None:
        if val is None:
            return
        if isinstance(val, str) and not val.strip():
            return
        f[key] = val

    settings = get_settings()
    set_if("标题", event.title)
    set_if("一级分类", select_text("一级分类", event.category_1))
    set_if("二级分类", select_text("二级分类", event.category_2))
    set_if(
        settings.feishu_activity_kind_field,
        select_text(settings.feishu_activity_kind_field, event.activity_kind),
    )
    set_if("开始时间", to_datetime_str(event.start_time))
    set_if("结束时间", to_datetime_str(event.end_time))
    set_if("活动地点", event.location)
    set_if("嘉宾", event.speaker)
    set_if("主办方", event.organizer)
    set_if("摘要", event.summary)
    set_if("报名方式", event.registration)
    set_if("标签", multi_select_texts("标签", loads_list(event.tags)))
    set_if("原文链接", url_link(event.source_url))
    set_if("公众号", event.article.mp_name if event.article else "")
    # 封面：只用公众号推文封面（pic_url，CDN 链接，飞书可直接显示）
    # 不回退到 cover_image（本地路径，飞书无法访问）
    # 海报图通过「海报附件」字段上传，不走封面字段
    pic_url = event.article.pic_url if event.article else ""
    set_if("封面", pic_url)
    set_if("状态", select_text("状态", event.status))
    set_if("时间状态", select_text("时间状态", event.event_time_status))
    set_if("保留决策", select_text("保留决策", event.retention_decision))
    set_if("用户置顶", checkbox(event.user_keep))
    set_if("置信度", number(event.confidence))
    set_if("关联原因", event.relevance_reason)
    set_if("更新时间", to_datetime_str(utcnow().isoformat()))

    # 演出信息
    set_if("演出类型", event.performance_type)
    set_if("演出作品", event.performance_name)
    set_if("演出团体", event.performer)
    set_if("票价信息", event.ticket_info)

    # 讲座信息
    set_if("讲座主题", event.lecture_topic)
    set_if("主讲人头衔", event.speaker_title)
    set_if("讲座系列", event.lecture_series)

    # 比赛信息
    set_if("比赛名称", event.competition_name)
    set_if("比赛类型", event.competition_type)
    set_if("截止时间", event.deadline)
    set_if("奖项设置", event.prize_info)

    # 报名信息
    set_if("报名链接", url_link(event.registration_url))
    set_if("报名截止", event.registration_deadline)
    set_if("人数限制", event.participant_limit)

    return f


def existing_poster_files(event: Event) -> list[str]:
    """返回事件海报图片的本地相对路径列表（文件实际存在）。"""
    files: list[str] = []
    for raw_path in loads_list(event.poster_images):
        normalized = str(raw_path).replace("\\", os.sep)
        candidate = Path(normalized)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        if candidate.exists():
            files.append(f"./{candidate.relative_to(Path.cwd()).as_posix()}")
    return files
