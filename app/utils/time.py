"""时间工具函数。"""

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def utcnow() -> datetime:
    """返回 naive UTC 时间（兼容 SQLite DateTime 列）。

    替代已废弃的 datetime.utcnow()。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_datetime_str(value: str) -> datetime | None:
    """将字符串解析为 datetime 对象。

    支持格式：
    - Unix 时间戳（秒或毫秒）
    - 中文日期格式（2026年6月24日 14:00）
    - 标准格式（2026-06-24 14:00:00）
    - RFC 2822 格式（Mon, 24 Jun 2026 14:00:00 +0800）
    """
    raw = (value or "").strip()
    if not raw:
        return None

    # 时间戳
    if raw.isdigit():
        timestamp = int(raw)
        if len(raw) >= 13:
            timestamp = timestamp // 1000
        return datetime.fromtimestamp(timestamp, tz=SHANGHAI_TZ)

    # 中文日期格式
    normalized = (
        raw.replace("年", "-")
        .replace("月", "-")
        .replace("日", " ")
        .replace("号", " ")
        .replace("/", "-")
        .replace(".", "-")
        .replace("T", " ")
        .replace("：", ":")
        .replace("点", ":")
    )
    # 去除括号内容
    normalized = re.sub(r"[（(][^）)]*[）)]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    # 标准格式
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt).replace(tzinfo=SHANGHAI_TZ)
        except ValueError:
            continue

    # RFC 2822 格式
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError, OverflowError):
        pass

    return None


def parse_to_epoch(value: str) -> int | None:
    """将字符串解析为 Unix 时间戳（秒）。"""
    dt = parse_datetime_str(value)
    if dt is None:
        return None
    return int(dt.timestamp())
