"""飞书机器人消息处理器测试。"""

from unittest.mock import MagicMock, patch

from app.services.bot_handler import BotHandler, HELP_TEXT, _RATE_LIMIT_MAX


class TestBotHandler:
    def setup_method(self) -> None:
        self.db = MagicMock()
        self.db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        self.handler = BotHandler(self.db)

    def test_empty_text_returns_help(self) -> None:
        assert self.handler.handle("") == HELP_TEXT

    def test_help_command(self) -> None:
        assert self.handler.handle("帮助") == HELP_TEXT
        assert self.handler.handle("help") == HELP_TEXT

    def test_rate_limit(self) -> None:
        user_id = "test_user_rate"
        # 先清理可能的残留
        self.handler._rate_timestamps.pop(user_id, None)

        # 前 N 条应该正常处理
        for _ in range(_RATE_LIMIT_MAX):
            self.handler._is_rate_limited(user_id)  # just consume

        # 第 N+1 条应该被限流
        assert self.handler._is_rate_limited(user_id) is True

    def test_conversation_history(self) -> None:
        user_id = "test_user_hist"
        self.handler._conversation_history.pop(user_id, None)

        self.handler._append_history(user_id, "user", "hello")
        self.handler._append_history(user_id, "assistant", "hi")

        assert len(self.handler._conversation_history[user_id]) == 2
        assert self.handler._conversation_history[user_id][0]["role"] == "user"

    def test_conversation_history_max_turns(self) -> None:
        user_id = "test_user_hist_max"
        self.handler._conversation_history.pop(user_id, None)

        # 添加超过上限的历史
        for i in range(20):
            self.handler._append_history(user_id, "user", f"msg{i}")
            self.handler._append_history(user_id, "assistant", f"reply{i}")

        # 应该被截断到 _HISTORY_MAX_TURNS * 2
        from app.services.bot_handler import _HISTORY_MAX_TURNS
        assert len(self.handler._conversation_history[user_id]) == _HISTORY_MAX_TURNS * 2

    @patch("app.services.bot_handler.requests.post")
    def test_ask_llm_no_api_key(self, mock_post) -> None:
        self.handler.settings = MagicMock()
        self.handler.settings.vision_api_key = ""
        result = self.handler._ask_llm("test", "data")
        assert "未配置" in result
        mock_post.assert_not_called()

    @patch("app.services.bot_handler.requests.post")
    def test_ask_llm_success(self, mock_post) -> None:
        self.handler.settings = MagicMock()
        self.handler.settings.vision_api_key = "test-key"
        self.handler.settings.vision_api_base_url = "https://api.test.com/v1"
        self.handler.settings.vision_api_model = "test-model"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "测试回复"}}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = self.handler._ask_llm("有什么活动？", "活动数据")
        assert result == "测试回复"
