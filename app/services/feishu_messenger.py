"""飞书群消息发送服务。

通过 lark-cli 发送消息到飞书群聊。
"""

import json
import logging
import subprocess
from typing import Any

from app.config import get_settings
from app.utils.lark_cli import build_lark_cli_command

logger = logging.getLogger(__name__)


class FeishuMessenger:
    """飞书群消息发送服务。"""

    def __init__(self) -> None:
        self.settings = get_settings()

    def _command_prefix(self) -> list[str]:
        """构建 lark-cli 命令前缀。"""
        return build_lark_cli_command(self.settings.feishu_cli_path)

    def send_message(
        self,
        content: str,
        chat_id: str = "",
        user_id: str = "",
        msg_type: str = "markdown",
    ) -> dict[str, Any]:
        """发送消息到飞书群聊或用户。

        Args:
            content: 消息内容
            chat_id: 群聊 ID（oc_xxx）- 与 user_id 二选一
            user_id: 用户 open_id（ou_xxx）- 与 chat_id 二选一
            msg_type: 消息类型（text/markdown）

        Returns:
            dict: 包含 ok, message_id, error 等字段
        """
        if not chat_id and not user_id:
            return {"ok": False, "error": "chat_id or user_id is required"}

        command = [
            *self._command_prefix(),
            "im",
            "+messages-send",
            "--as", self.settings.feishu_cli_as,
        ]

        if chat_id:
            command.extend(["--chat-id", chat_id])
        else:
            command.extend(["--user-id", user_id])

        if msg_type == "markdown":
            command.extend(["--markdown", content])
        else:
            command.extend(["--text", content])

        command.extend(["--format", "json"])

        target = chat_id or user_id
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
                logger.error("Failed to send message to %s: %s", target, result.stderr or result.stdout)
                return {
                    "ok": False,
                    "error": result.stderr or result.stdout,
                    "return_code": result.returncode,
                }

            data = json.loads(result.stdout)
            return {
                "ok": data.get("ok", False),
                "message_id": data.get("data", {}).get("message_id", ""),
                "error": data.get("error", {}).get("message", "") if not data.get("ok") else "",
            }

        except subprocess.TimeoutExpired:
            logger.error("Timeout sending message to %s", target)
            return {"ok": False, "error": "timeout"}
        except json.JSONDecodeError as e:
            logger.error("Failed to parse response: %s", e)
            return {"ok": False, "error": f"invalid response: {e}"}
        except Exception as e:
            logger.error("Unexpected error: %s", e)
            return {"ok": False, "error": str(e)}

    def _send_report(self, content: str, report_type: str) -> dict[str, Any]:
        """发送报告到配置的群聊或用户。"""
        chat_id = self.settings.feishu_report_chat_id
        user_id = self.settings.feishu_report_user_id
        if not chat_id and not user_id:
            logger.warning("FEISHU_REPORT_CHAT_ID or FEISHU_REPORT_USER_ID not configured, skipping %s report", report_type)
            return {"ok": False, "error": "FEISHU_REPORT_CHAT_ID or FEISHU_REPORT_USER_ID not configured"}
        return self.send_message(content, chat_id=chat_id, user_id=user_id, msg_type="markdown")

    def send_daily_report(self, content: str) -> dict[str, Any]:
        """发送日报到配置的群聊或用户。"""
        return self._send_report(content, "daily")

    def send_weekly_report(self, content: str) -> dict[str, Any]:
        """发送周报到配置的群聊或用户。"""
        return self._send_report(content, "weekly")
