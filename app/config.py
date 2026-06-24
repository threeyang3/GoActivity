from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Campus Activity Knowledge Hub"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_url: str = "sqlite:///storage/app.db"
    storage_dir: Path = Path("storage")
    we_mp_rss_base_url: str = "http://localhost:8001"
    we_mp_rss_api_base: str = "/api/v1/wx"
    we_mp_rss_access_key: str = ""
    we_mp_rss_secret_key: str = ""
    feishu_provider: str = "auto"
    feishu_cli_path: str = "feishu"
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
    ocr_provider: str = "mock"
    vision_api_provider: str = "mock"
    vision_api_key: str = ""
    vision_api_base_url: str = "https://api.openai.com/v1"
    vision_api_model: str = "gpt-4.1-mini"
    vision_api_timeout_seconds: float = 60.0
    feishu_report_chat_id: str = ""
    feishu_report_user_id: str = ""
    feishu_report_daily_cron: str = "0 9 * * *"
    feishu_report_weekly_cron: str = "0 9 * * 1"
    feishu_report_daily_enabled: bool = True
    feishu_report_weekly_enabled: bool = True
    auto_sync_cron: str = "0 * * * *"  # 默认每小时同步一次
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
