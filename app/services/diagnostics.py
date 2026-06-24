from pathlib import Path

from app.config import get_settings


class DiagnosticsService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def config_checks(self) -> list[dict[str, str | bool]]:
        uses_openapi = self.settings.feishu_provider in {"auto", "openapi"}
        return [
            self._check("WE_MP_RSS_ACCESS_KEY", bool(self.settings.we_mp_rss_access_key.strip()), "env", "Required for JSON article sync."),
            self._check("WE_MP_RSS_SECRET_KEY", bool(self.settings.we_mp_rss_secret_key.strip()), "env", "Required for JSON article sync."),
            self._check("VISION_API_KEY", bool(self.settings.vision_api_key.strip()), "env", "Required when OCR_PROVIDER or VISION_API_PROVIDER uses openai."),
            self._check("FEISHU_CLI_PATH", bool(self.settings.feishu_cli_path.strip()), "env", "Used by FeishuAdapter subprocess calls."),
            self._check("FEISHU_CLI_AS", bool(self.settings.feishu_cli_as.strip()), "env", "Identity type used by lark-cli or compatible CLI."),
            self._check(
                "FEISHU_POSTER_ATTACHMENT_FIELD",
                bool(self.settings.feishu_poster_attachment_field.strip()),
                "env",
                "Bitable attachment field name used for poster uploads when lark-cli sync is enabled.",
            ),
            self._check("FEISHU_APP_ID", bool(self.settings.feishu_app_id.strip()) if uses_openapi else True, "env", "Required when Feishu OpenAPI sync is enabled."),
            self._check(
                "FEISHU_APP_SECRET",
                bool(self.settings.feishu_app_secret.strip()) if uses_openapi else True,
                "env",
                "Required when Feishu OpenAPI sync is enabled.",
            ),
            self._check(
                "FEISHU_BITABLE_APP_TOKEN",
                bool(self.settings.feishu_bitable_app_token.strip()) if uses_openapi else True,
                "env",
                "Required when writing event records into Feishu Bitable via OpenAPI.",
            ),
            self._check(
                "FEISHU_BITABLE_TABLE_ID",
                bool(self.settings.feishu_bitable_table_id.strip()) if uses_openapi else True,
                "env",
                "Required when writing event records into Feishu Bitable via OpenAPI.",
            ),
            self._check(".env", Path(".env").exists(), "filesystem", "Project runtime config file."),
            self._check("storage/", self.settings.storage_dir.exists(), "filesystem", "Local storage directory for DB, markdown, images, logs."),
            self._check("OCR_PROVIDER", True, "config", f"Current value: {self.settings.ocr_provider}"),
            self._check("VISION_API_PROVIDER", True, "config", f"Current value: {self.settings.vision_api_provider}"),
            self._check("FEISHU_DRY_RUN", True, "config", f"Current value: {self.settings.feishu_dry_run}"),
            self._check("FEISHU_PROVIDER", True, "config", f"Current value: {self.settings.feishu_provider}"),
            self._check("FEISHU_REPORT_USER_ID", bool(self.settings.feishu_report_user_id.strip()), "env", "User ID for sending reports directly."),
            self._check("FEISHU_REPORT_CHAT_ID", bool(self.settings.feishu_report_chat_id.strip()), "env", "Chat ID for sending reports to group."),
            self._check("FEISHU_REPORT_DAILY_CRON", True, "config", f"Current value: {self.settings.feishu_report_daily_cron}"),
            self._check("FEISHU_REPORT_WEEKLY_CRON", True, "config", f"Current value: {self.settings.feishu_report_weekly_cron}"),
            self._check("FEISHU_REPORT_DAILY_ENABLED", True, "config", f"Current value: {self.settings.feishu_report_daily_enabled}"),
            self._check("FEISHU_REPORT_WEEKLY_ENABLED", True, "config", f"Current value: {self.settings.feishu_report_weekly_enabled}"),
        ]

    @staticmethod
    def _check(key: str, configured: bool, source: str, detail: str) -> dict[str, str | bool]:
        return {
            "key": key,
            "configured": configured,
            "source": source,
            "detail": detail,
        }
