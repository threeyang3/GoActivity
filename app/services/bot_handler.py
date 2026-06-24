"""飞书机器人消息处理器。

接入 LLM 实现自然语言对话，同时保留关键词快速路径。
支持速率限制和对话上下文。
"""

import logging
import re
import threading
import time
from collections import defaultdict
from datetime import timedelta

import requests
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Event
from app.utils.constants import ACTIVITY_KIND_LABELS as KIND_LABELS
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

HELP_TEXT = """**🎓 校园活动助手**

我可以帮你查询校园活动信息，试试自然语言提问：

- 这周末有什么活动？
- 推荐几个讲座
- 有没有志愿者招募？
- 7月有什么演出？
- 帮我找一下关于AI的活动

也支持快捷命令：**今日活动** / **本周活动** / **推荐** / **帮助**"""

# 系统提示词
SYSTEM_PROMPT = """你是北京大学校园活动助手。用户会问你关于校园活动的问题，你需要根据提供的活动数据来回答。

规则：
1. 只根据提供的数据回答，不要编造不存在的活动
2. 如果数据中没有匹配的活动，如实告知
3. 回答要简洁、有条理，适合在飞书聊天中阅读
4. 使用 markdown 格式（加粗、列表等）
5. 如果用户的问题与活动无关，礼貌地引导回活动查询
6. 回复用中文"""

# 速率限制：每用户每分钟最多 N 条消息
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 10

# 对话历史：每用户保留最近 N 轮
_HISTORY_MAX_TURNS = 5

# 线程锁：保护 _rate_timestamps 和 _conversation_history 的并发访问
_lock = threading.Lock()


class BotHandler:
    """飞书机器人消息处理器。"""

    # 类级别共享状态（跨实例持久化）
    _rate_timestamps: dict[str, list[float]] = defaultdict(list)
    _conversation_history: dict[str, list[dict]] = defaultdict(list)

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def handle(self, text: str, user_id: str = "") -> str:
        """处理用户消息，返回 markdown 格式回复。"""
        text = text.strip()
        if not text:
            return HELP_TEXT

        # 快速路径：帮助命令
        if text in ("帮助", "help", "菜单", "功能", "怎么用"):
            return HELP_TEXT

        # 速率限制
        if user_id and self._is_rate_limited(user_id):
            return "⚠️ 消息太频繁了，请稍后再试。"

        # 获取活动数据作为上下文
        events = self._fetch_context_events()
        events_text = self._events_to_text(events)

        # 调用 LLM 生成回复
        reply = self._ask_llm(text, events_text, user_id)

        # 记录对话历史
        if user_id:
            self._append_history(user_id, "user", text)
            self._append_history(user_id, "assistant", reply)

        return reply

    def _is_rate_limited(self, user_id: str) -> bool:
        """检查用户是否触发速率限制。"""
        now = time.time()
        with _lock:
            # 每 100 次调用清理一次过期条目（惰性清理）
            if len(self._rate_timestamps) > 100:
                self._cleanup_stale(now)

            timestamps = self._rate_timestamps[user_id]
            cutoff = now - _RATE_LIMIT_WINDOW
            self._rate_timestamps[user_id] = [t for t in timestamps if t > cutoff]
            self._rate_timestamps[user_id].append(now)
            if len(self._rate_timestamps[user_id]) >= _RATE_LIMIT_MAX:
                return True
            return False

    @classmethod
    def _cleanup_stale(cls, now: float) -> None:
        """清理超过窗口期的速率限制条目和超长时间未活跃的对话历史。"""
        cutoff = now - _RATE_LIMIT_WINDOW * 2
        stale_keys = [k for k, v in cls._rate_timestamps.items() if not v or v[-1] < cutoff]
        for k in stale_keys:
            del cls._rate_timestamps[k]
        # 清理超过 2x 窗口期未活跃的对话历史（与速率限制清理保持一致）
        stale_hist = [k for k, v in cls._conversation_history.items() if not v or k not in cls._rate_timestamps]
        for k in stale_hist:
            del cls._conversation_history[k]

    def _append_history(self, user_id: str, role: str, content: str) -> None:
        """追加对话历史，超过上限时丢弃最早的。"""
        with _lock:
            history = self._conversation_history[user_id]
            history.append({"role": role, "content": content})
            # 保留最近 N 轮（每轮 2 条：user + assistant）
            max_messages = _HISTORY_MAX_TURNS * 2
            if len(history) > max_messages:
                self._conversation_history[user_id] = history[-max_messages:]

    def _fetch_context_events(self) -> list[Event]:
        """获取所有可能相关的活动作为上下文。"""
        now = utcnow()
        thirty_days_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        thirty_days_later = (now + timedelta(days=30)).strftime("%Y-%m-%d")

        return (
            self.db.query(Event)
            .filter(
                Event.status.notin_(["ignored_non_event"]),
                or_(
                    Event.retention_decision.in_(["keep", "keep_user"]),
                    Event.start_time.between(thirty_days_ago, thirty_days_later),
                ),
            )
            .order_by(Event.start_time.asc())
            .limit(50)
            .all()
        )

    def _events_to_text(self, events: list[Event]) -> str:
        """将活动列表转为 LLM 可读的文本。"""
        if not events:
            return "当前没有活动数据。"

        lines = []
        for e in events:
            kind = KIND_LABELS.get(e.activity_kind, e.activity_kind or "未知")
            status = e.status
            retention = e.retention_decision
            time_str = e.start_time[:16] if e.start_time else "时间待定"
            end_str = f" ~ {e.end_time[:16]}" if e.end_time else ""
            location = e.location or ""
            speaker = e.speaker or ""
            organizer = e.organizer or ""
            summary = (e.summary or "")[:100]

            line = f"- 【{kind}】{e.title}"
            line += f" | 时间：{time_str}{end_str}"
            if location:
                line += f" | 地点：{location}"
            if speaker:
                line += f" | 嘉宾：{speaker}"
            if organizer:
                line += f" | 主办：{organizer}"
            if summary:
                line += f" | 简介：{summary}"
            line += f" | 状态：{status} | 决策：{retention}"
            lines.append(line)

        return "\n".join(lines)

    def _ask_llm(self, question: str, events_text: str, user_id: str = "") -> str:
        """调用 LLM 生成回复。支持对话历史。"""
        api_key = self.settings.vision_api_key
        base_url = self.settings.vision_api_base_url
        model = self.settings.vision_api_model

        if not api_key:
            return "⚠️ AI 服务未配置，请联系管理员。"

        user_prompt = f"""以下是当前的校园活动数据：

{events_text}

用户问题：{question}"""

        # 构建消息列表（含历史）
        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if user_id and user_id in self._conversation_history:
            messages.extend(self._conversation_history[user_id])
        messages.append({"role": "user", "content": user_prompt})

        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 2048,
                    "messages": messages,
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content.strip() if content else "🤔 AI 没有生成回复，请换个方式提问。"
        except requests.RequestException as exc:
            logger.error("LLM request failed: %s", exc)
            return "⚠️ AI 服务暂时不可用，请稍后再试。"
