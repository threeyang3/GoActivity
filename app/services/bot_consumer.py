"""飞书机器人事件消费者。

通过 lark-cli event consume 持续监听飞书消息事件，
解析后分发给 BotHandler 处理。
"""

import json
import logging
import subprocess
import sys
import threading
from typing import Any

from app.config import get_settings
from app.db import SessionLocal
from app.services.bot_handler import BotHandler
from app.services.feishu_messenger import FeishuMessenger
from app.utils.lark_cli import build_lark_cli_command

logger = logging.getLogger(__name__)


class BotEventConsumer:
    """飞书机器人事件消费者。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._process: subprocess.Popen | None = None
        self._restart_count = 0
        self._max_restarts = 5
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        """启动事件消费线程。"""
        if not self.settings.feishu_bot_enabled:
            logger.info("Feishu bot disabled (FEISHU_BOT_ENABLED=false)")
            return

        if self._thread and self._thread.is_alive():
            logger.warning("Bot consumer already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._consume_loop, daemon=True, name="feishu-bot")
        self._thread.start()
        logger.info("Feishu bot consumer started")

    def shutdown(self) -> None:
        """停止事件消费。"""
        self._stop_event.set()
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
        if self._thread:
            self._thread.join(timeout=10)
        self._running = False
        logger.info("Feishu bot consumer stopped")

    def _consume_loop(self) -> None:
        """消费循环：运行 lark-cli event consume，自动重启。"""
        while not self._stop_event.is_set():
            if self._restart_count >= self._max_restarts:
                logger.error("Bot consumer exceeded max restarts (%d), giving up", self._max_restarts)
                break

            try:
                self._run_consumer()
            except Exception as exc:
                logger.error("Bot consumer crashed: %s", exc)
                self._restart_count += 1
                if not self._stop_event.is_set():
                    logger.info("Restarting bot consumer (%d/%d)...", self._restart_count, self._max_restarts)
                    self._stop_event.wait(5)  # 等待 5 秒后重启

    def _run_consumer(self) -> None:
        """运行 lark-cli event consume 子进程。"""
        cli_path = self.settings.feishu_cli_path
        command = [
            *build_lark_cli_command(cli_path),
            "event",
            "consume",
            "im.message.receive_v1",
            "--as",
            "bot",
        ]

        logger.info("Starting bot consumer: %s", " ".join(command))

        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        self._running = True
        self._restart_count = 0  # 成功启动，重置计数

        try:
            for line in self._process.stdout:  # type: ignore[union-attr]
                if self._stop_event.is_set():
                    break
                line = line.strip()
                if not line:
                    continue
                self._handle_line(line)
        finally:
            if self._process:
                self._process.terminate()
                self._process.wait(timeout=5)
            self._running = False

    def _handle_line(self, line: str) -> None:
        """处理一行 NDJSON 输出。"""
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("Non-JSON line from bot consumer: %s", line[:100])
            return

        # lark-cli event consume 输出的事件数据在顶层（不在 event 嵌套中）
        chat_type = event.get("chat_type", "")
        message_type = event.get("message_type", "")
        chat_id = event.get("chat_id", "")
        message_id = event.get("message_id", "")
        sender = event.get("sender") or {}
        user_id = sender.get("id", "") if isinstance(sender, dict) else ""

        # 处理文本消息
        if message_type == "text":
            raw_content = event.get("content", "")
            try:
                content = json.loads(raw_content)
                text = content.get("text", "").strip()
            except (json.JSONDecodeError, TypeError):
                text = str(raw_content).strip()

            if not text:
                return

            text = self._strip_mention(text, event)
            logger.info("Bot received [%s] from %s: %s", chat_type, chat_id, text[:50])

            try:
                db = SessionLocal()
                try:
                    handler = BotHandler(db)
                    reply = handler.handle(text, user_id=user_id)
                except Exception as exc:
                    db.rollback()
                    raise
                finally:
                    db.close()
            except Exception as exc:
                logger.error("Bot handler error: %s", exc)
                reply = "⚠️ 处理消息时出错，请稍后再试。"

            self._reply(chat_id, message_id, reply)

        elif message_type == "image":
            logger.info("Bot received image message from %s", chat_id)
            self._reply(chat_id, message_id, "📸 收到图片！目前图片识别功能开发中，请用文字描述你想查询的活动。")

        else:
            logger.debug("Ignoring message type: %s", message_type)

    def _strip_mention(self, text: str, event: dict) -> str:
        """去掉 @bot 的 mention 前缀。"""
        mentions = event.get("mentions") or []
        if not isinstance(mentions, list):
            return text
        for mention in mentions:
            if not isinstance(mention, dict):
                continue
            key = mention.get("key", "")
            if key:
                text = text.replace(key, "").strip()
        return text

    def _reply(self, chat_id: str, message_id: str, content: str) -> None:
        """回复飞书消息。"""
        messenger = FeishuMessenger()
        # 使用 reply 模式回复特定消息
        cli_path = self.settings.feishu_cli_path
        command = [
            *build_lark_cli_command(cli_path),
            "im",
            "+messages-reply",
            "--as",
            "bot",
            "--message-id",
            message_id,
            "--markdown",
            content,
            "--format",
            "json",
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                logger.error("Bot reply failed: %s", result.stderr or result.stdout)
                # 回退到直接发送
                messenger.send_message(content, chat_id=chat_id, msg_type="markdown")
        except Exception as exc:
            logger.error("Bot reply error: %s", exc)
            # 回退到直接发送
            try:
                messenger.send_message(content, chat_id=chat_id, msg_type="markdown")
            except Exception as exc:
                logger.warning("Fallback messenger also failed: %s", exc)
