from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    @field_validator("we_mp_rss_base_url")
    @classmethod
    def local_collector_ipv4(cls, value: str) -> str:
        # Windows may wait on an unused IPv6 loopback address before trying
        # IPv4. The locally managed collector explicitly binds IPv4.
        from urllib.parse import urlsplit, urlunsplit
        parsed = urlsplit(value)
        if parsed.netloc == "localhost" or parsed.netloc.startswith("localhost:"):
            parsed = parsed._replace(netloc=parsed.netloc.replace("localhost", "127.0.0.1", 1))
        return urlunsplit(parsed)

    app_name: str = "GoActivity"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    allow_lan_access: bool = False
    admin_token: str = ""
    database_url: str = "sqlite:///storage/app.db"
    storage_dir: Path = Path("storage")
    we_mp_rss_base_url: str = "http://localhost:8001"
    we_mp_rss_api_base: str = "/api/v1/wx"
    we_mp_rss_access_key: str = ""
    we_mp_rss_secret_key: str = ""
    we_mp_rss_webhook_token: str = ""
    feishu_provider: str = "auto"
    feishu_cli_path: str = "lark-cli"
    feishu_cli_as: str = "user"
    feishu_base_url: str = "https://open.feishu.cn"
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_bitable_app_token: str = ""
    feishu_bitable_table_id: str = ""
    feishu_poster_attachment_field: str = "海报附件"
    feishu_activity_kind_field: str = "活动类型"
    feishu_activity_kind_code_field: str = "活动类型编码"
    feishu_dry_run: bool = True
    feishu_max_retries: int = 3
    feishu_retry_delay_seconds: float = 1.0
    feishu_sync_retry_max: int = 6
    feishu_sync_retry_base_minutes: int = 15
    feishu_reconcile_enabled: bool = True
    feishu_reconcile_cron: str = "30 3 * * *"
    feishu_reconcile_max_missing_ratio: float = 0.2
    feishu_reconcile_snapshot_hours: int = 24
    automation_alerts_enabled: bool = True
    automation_alert_cooldown_hours: int = 6
    account_stale_hours: int = 36
    priority_accounts: str = ""
    priority_collection_cron: str = "*/30 * * * *"
    auto_sync_stale_minutes: int = 180
    # OCR Provider 配置
    ocr_provider: str = "mock"  # mock | disabled | rapid | openai_compatible
    ocr_api_key: str = ""
    ocr_api_base_url: str = "https://api.openai.com/v1"
    ocr_api_model: str = "gpt-4o-mini"
    ocr_api_timeout_seconds: float = 60.0
    ocr_max_images: int = 5

    # Vision Provider 配置（多模态）
    vision_api_provider: str = "mock"  # mock | openai_compatible | textai
    vision_api_key: str = ""
    vision_api_base_url: str = "https://api.openai.com/v1"
    vision_api_model: str = "gpt-4.1-mini"
    vision_api_timeout_seconds: float = 60.0
    vision_max_images: int = 5
    vision_max_tokens: int = 4096

    # 文本 AI Provider 配置（纯文本分析）
    text_ai_provider: str = "disabled"  # disabled | mock | openai_compatible
    text_ai_api_key: str = ""
    text_ai_api_base_url: str = "https://api.openai.com/v1"
    text_ai_api_model: str = "gpt-4.1-mini"
    text_ai_api_timeout_seconds: float = 60.0
    text_ai_max_tokens: int = 4096
    feishu_report_chat_id: str = ""
    feishu_report_user_id: str = ""
    feishu_report_daily_cron: str = "0 9 * * *"
    feishu_report_weekly_cron: str = "0 9 * * 1"
    feishu_report_daily_enabled: bool = True
    feishu_report_weekly_enabled: bool = True
    auto_sync_cron: str = "0 * * * *"  # 默认每小时同步一次
    auto_archive_expired_days: int = 30  # 过期活动自动归档天数，0 表示禁用
    feishu_bot_enabled: bool = False
    feishu_bot_app_id: str = ""
    feishu_bot_app_secret: str = ""
    feishu_bot_rate_limit: int = 10  # 每用户每分钟最多消息数

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def articles_dir(self) -> Path:
        return self.storage_dir / "articles"

    @property
    def images_dir(self) -> Path:
        return self.storage_dir / "images"

    @property
    def logs_dir(self) -> Path:
        return self.storage_dir / "logs"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.articles_dir.mkdir(parents=True, exist_ok=True)
    settings.images_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    return settings


def validate_settings(settings: Settings) -> list[str]:
    """校验当前配置下必需的环境变量，返回缺失项的警告列表。

    只检查当前启用功能所需的变量，不阻止启动。
    """
    warnings: list[str] = []
    # 飞书 Bitable 相关（lark_cli 和 auto 模式都需要）
    if settings.feishu_provider in ("lark_cli", "auto"):
        if not settings.feishu_bitable_app_token:
            warnings.append("FEISHU_BITABLE_APP_TOKEN 未配置（飞书多维表格同步需要）")
        if not settings.feishu_bitable_table_id:
            warnings.append("FEISHU_BITABLE_TABLE_ID 未配置（飞书多维表格同步需要）")
    # 飞书 OpenAPI 相关
    if settings.feishu_provider in ("openapi", "auto"):
        if not settings.feishu_app_id:
            warnings.append("FEISHU_APP_ID 未配置（飞书 OpenAPI 模式需要）")
        if not settings.feishu_app_secret:
            warnings.append("FEISHU_APP_SECRET 未配置（飞书 OpenAPI 模式需要）")
    # 飞书机器人
    if settings.feishu_bot_enabled:
        if not settings.feishu_bot_app_id:
            warnings.append("FEISHU_BOT_APP_ID 未配置（飞书机器人已启用但缺少 App ID）")
    # Vision API（非 mock 模式）
    if settings.ocr_provider in ("openai", "openai_compatible") and not settings.ocr_api_key:
        warnings.append("OCR_API_KEY 未配置（OCR API 已启用但缺少密钥）")
    if settings.vision_api_provider != "mock":
        if not settings.vision_api_key:
            warnings.append("VISION_API_KEY 未配置（Vision API 已启用但缺少密钥）")
    if settings.text_ai_provider in ("openai", "openai_compatible") and not settings.text_ai_api_key:
        warnings.append("TEXT_AI_API_KEY 未配置（文本 AI 已启用但缺少密钥）")
    # 报告发送
    if settings.feishu_report_daily_enabled or settings.feishu_report_weekly_enabled:
        if not settings.feishu_report_chat_id and not settings.feishu_report_user_id:
            warnings.append("FEISHU_REPORT_CHAT_ID 和 FEISHU_REPORT_USER_ID 均未配置（报告发送需要至少一个）")
    return warnings
