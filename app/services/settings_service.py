"""统一设置服务。"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import AppSetting

logger = logging.getLogger(__name__)

SETTINGS_SCHEMA: list[dict[str, Any]] = [
    {"key": "app_name", "label": "应用名称", "category": "service", "type": "string", "default": "GoActivity", "requires_restart": True, "is_secret": False},
    {"key": "app_host", "label": "监听地址", "category": "service", "type": "string", "default": "127.0.0.1", "requires_restart": True, "is_secret": False, "help": "默认仅监听本机。"},
    {"key": "app_port", "label": "监听端口", "category": "service", "type": "integer", "default": 8000, "requires_restart": True, "is_secret": False},
    {"key": "allow_lan_access", "label": "允许局域网访问", "category": "service", "type": "boolean", "default": False, "requires_restart": True, "is_secret": False},
    {"key": "admin_token", "label": "管理令牌", "category": "service", "type": "string", "default": "", "requires_restart": False, "is_secret": True},
    {"key": "database_url", "label": "数据库地址", "category": "database", "type": "string", "default": "sqlite:///storage/app.db", "requires_restart": True, "is_secret": False},
    {"key": "storage_dir", "label": "存储目录", "category": "database", "type": "string", "default": "storage", "requires_restart": True, "is_secret": False},
    {"key": "ocr_provider", "label": "OCR 提供者", "category": "ocr", "type": "select", "options": ["mock", "disabled", "rapid", "openai", "openai_compatible"], "default": "mock", "requires_restart": False, "is_secret": False},
    {"key": "ocr_api_key", "label": "OCR API 密钥", "category": "ocr", "type": "string", "default": "", "requires_restart": False, "is_secret": True},
    {"key": "ocr_api_base_url", "label": "OCR API 地址", "category": "ocr", "type": "string", "default": "https://api.openai.com/v1", "requires_restart": False, "is_secret": False},
    {"key": "ocr_api_model", "label": "OCR 模型", "category": "ocr", "type": "string", "default": "gpt-4o-mini", "requires_restart": False, "is_secret": False},
    {"key": "ocr_api_timeout_seconds", "label": "OCR 超时（秒）", "category": "ocr", "type": "number", "default": 60.0, "requires_restart": False, "is_secret": False},
    {"key": "ocr_max_images", "label": "OCR 最大图片数", "category": "ocr", "type": "integer", "default": 5, "requires_restart": False, "is_secret": False},
    {"key": "vision_api_provider", "label": "Vision 提供者", "category": "vision", "type": "select", "options": ["mock", "openai", "openai_compatible", "textai"], "default": "mock", "requires_restart": False, "is_secret": False},
    {"key": "vision_api_key", "label": "Vision API 密钥", "category": "vision", "type": "string", "default": "", "requires_restart": False, "is_secret": True},
    {"key": "vision_api_base_url", "label": "Vision API 地址", "category": "vision", "type": "string", "default": "https://api.openai.com/v1", "requires_restart": False, "is_secret": False},
    {"key": "vision_api_model", "label": "Vision 模型", "category": "vision", "type": "string", "default": "gpt-4.1-mini", "requires_restart": False, "is_secret": False},
    {"key": "vision_api_timeout_seconds", "label": "Vision 超时（秒）", "category": "vision", "type": "number", "default": 60.0, "requires_restart": False, "is_secret": False},
    {"key": "vision_max_images", "label": "Vision 最大图片数", "category": "vision", "type": "integer", "default": 5, "requires_restart": False, "is_secret": False},
    {"key": "vision_max_tokens", "label": "Vision 最大 Token", "category": "vision", "type": "integer", "default": 4096, "requires_restart": False, "is_secret": False},
    {"key": "text_ai_provider", "label": "文本 AI 提供者", "category": "text_ai", "type": "select", "options": ["disabled", "mock", "openai", "openai_compatible"], "default": "disabled", "requires_restart": False, "is_secret": False},
    {"key": "text_ai_api_key", "label": "文本 AI 密钥", "category": "text_ai", "type": "string", "default": "", "requires_restart": False, "is_secret": True},
    {"key": "text_ai_api_base_url", "label": "文本 AI 地址", "category": "text_ai", "type": "string", "default": "https://api.openai.com/v1", "requires_restart": False, "is_secret": False},
    {"key": "text_ai_api_model", "label": "文本 AI 模型", "category": "text_ai", "type": "string", "default": "gpt-4.1-mini", "requires_restart": False, "is_secret": False},
    {"key": "text_ai_api_timeout_seconds", "label": "文本 AI 超时（秒）", "category": "text_ai", "type": "number", "default": 60.0, "requires_restart": False, "is_secret": False},
    {"key": "text_ai_max_tokens", "label": "文本 AI 最大 Token", "category": "text_ai", "type": "integer", "default": 4096, "requires_restart": False, "is_secret": False},
    {"key": "we_mp_rss_base_url", "label": "WeRSS 地址", "category": "werss", "type": "string", "default": "http://localhost:8001", "requires_restart": False, "is_secret": False},
    {"key": "we_mp_rss_api_base", "label": "WeRSS API 路径", "category": "werss", "type": "string", "default": "/api/v1/wx", "requires_restart": False, "is_secret": False},
    {"key": "we_mp_rss_access_key", "label": "WeRSS Access Key", "category": "werss", "type": "string", "default": "", "requires_restart": False, "is_secret": True},
    {"key": "we_mp_rss_secret_key", "label": "WeRSS Secret Key", "category": "werss", "type": "string", "default": "", "requires_restart": False, "is_secret": True},
    {"key": "feishu_provider", "label": "飞书提供者", "category": "feishu", "type": "select", "options": ["auto", "lark_cli", "openapi"], "default": "auto", "requires_restart": False, "is_secret": False},
    {"key": "feishu_cli_path", "label": "lark-cli 路径", "category": "feishu", "type": "string", "default": "lark-cli", "requires_restart": False, "is_secret": False},
    {"key": "feishu_base_url", "label": "飞书 API 地址", "category": "feishu", "type": "string", "default": "https://open.feishu.cn", "requires_restart": False, "is_secret": False},
    {"key": "feishu_app_id", "label": "飞书 App ID", "category": "feishu", "type": "string", "default": "", "requires_restart": False, "is_secret": True},
    {"key": "feishu_app_secret", "label": "飞书 App Secret", "category": "feishu", "type": "string", "default": "", "requires_restart": False, "is_secret": True},
    {"key": "feishu_bitable_app_token", "label": "飞书多维表格 App Token", "category": "feishu", "type": "string", "default": "", "requires_restart": False, "is_secret": False},
    {"key": "feishu_bitable_table_id", "label": "飞书多维表格 Table ID", "category": "feishu", "type": "string", "default": "", "requires_restart": False, "is_secret": False},
    {"key": "feishu_dry_run", "label": "飞书 Dry Run", "category": "feishu", "type": "boolean", "default": True, "requires_restart": False, "is_secret": False},
    {"key": "feishu_bot_enabled", "label": "启用飞书机器人", "category": "feishu_bot", "type": "boolean", "default": False, "requires_restart": True, "is_secret": False},
    {"key": "feishu_bot_app_id", "label": "机器人 App ID", "category": "feishu_bot", "type": "string", "default": "", "requires_restart": True, "is_secret": True},
    {"key": "feishu_bot_app_secret", "label": "机器人 App Secret", "category": "feishu_bot", "type": "string", "default": "", "requires_restart": True, "is_secret": True},
    {"key": "auto_sync_cron", "label": "自动同步 Cron", "category": "automation", "type": "string", "default": "0 * * * *", "requires_restart": False, "is_secret": False},
    {"key": "auto_archive_expired_days", "label": "自动归档天数", "category": "automation", "type": "integer", "default": 30, "requires_restart": False, "is_secret": False},
    {"key": "feishu_report_daily_enabled", "label": "启用日报", "category": "reports", "type": "boolean", "default": True, "requires_restart": False, "is_secret": False},
    {"key": "feishu_report_daily_cron", "label": "日报 Cron", "category": "reports", "type": "string", "default": "0 9 * * *", "requires_restart": False, "is_secret": False},
    {"key": "feishu_report_weekly_enabled", "label": "启用周报", "category": "reports", "type": "boolean", "default": True, "requires_restart": False, "is_secret": False},
    {"key": "feishu_report_weekly_cron", "label": "周报 Cron", "category": "reports", "type": "string", "default": "0 9 * * 1", "requires_restart": False, "is_secret": False},
    {"key": "feishu_report_chat_id", "label": "报告群聊 ID", "category": "reports", "type": "string", "default": "", "requires_restart": False, "is_secret": False},
    {"key": "feishu_report_user_id", "label": "报告用户 ID", "category": "reports", "type": "string", "default": "", "requires_restart": False, "is_secret": False},
]

_SCHEMA_MAP: dict[str, dict[str, Any]] = {item["key"]: item for item in SETTINGS_SCHEMA}
HOT_RELOAD_KEYS: set[str] = {item["key"] for item in SETTINGS_SCHEMA if not item.get("requires_restart", False)}
RESTART_REQUIRED_KEYS: set[str] = {item["key"] for item in SETTINGS_SCHEMA if item.get("requires_restart", False)}
RESCHEDULE_KEYS: set[str] = {
    "auto_sync_cron",
    "feishu_report_daily_cron",
    "feishu_report_weekly_cron",
    "feishu_report_daily_enabled",
    "feishu_report_weekly_enabled",
}


def mask_secret(value: str) -> dict[str, Any]:
    if not value:
        return {"configured": False, "masked_value": ""}
    if len(value) <= 8:
        return {"configured": True, "masked_value": "****"}
    return {"configured": True, "masked_value": f"{value[:4]}****{value[-4:]}"}


class SettingsService:
    """统一设置服务。"""

    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    def get_schema(self) -> list[dict[str, Any]]:
        return SETTINGS_SCHEMA

    def get_current_values(self) -> dict[str, Any]:
        values = self.load_effective_values()
        result: dict[str, Any] = {}
        for item in SETTINGS_SCHEMA:
            key = item["key"]
            value = values.get(key, item.get("default", ""))
            result[key] = mask_secret(str(value)) if item.get("is_secret") else value
        return result

    def validate_updates(self, updates: dict[str, Any]) -> tuple[list[str], list[str], list[dict[str, str]]]:
        applied: list[str] = []
        restart_required: list[str] = []
        errors: list[dict[str, str]] = []

        for key, value in updates.items():
            schema = _SCHEMA_MAP.get(key)
            if not schema:
                errors.append({"key": key, "error": f"未知配置项: {key}"})
                continue
            try:
                self._coerce_value(value, schema)
            except (TypeError, ValueError) as exc:
                errors.append({"key": key, "error": str(exc)})
                continue
            applied.append(key)
            if schema.get("requires_restart"):
                restart_required.append(key)

        if updates.get("allow_lan_access") is True:
            effective = self.load_effective_values()
            token = updates.get("admin_token") or effective.get("admin_token")
            if not token:
                errors.append({"key": "allow_lan_access", "error": "启用局域网访问前必须配置 admin_token"})
                applied = [key for key in applied if key != "allow_lan_access"]
                restart_required = [key for key in restart_required if key != "allow_lan_access"]

        return applied, restart_required, errors

    def update_settings(
        self,
        normal_updates: dict[str, Any],
        secret_updates: dict[str, str],
        clear_secrets: list[str] | None = None,
    ) -> tuple[list[str], list[str], list[str], list[dict[str, str]]]:
        applied, restart_required, errors = self.validate_updates(normal_updates)
        secret_applied: list[str] = []
        clear_secrets = clear_secrets or []

        for key in secret_updates:
            if key not in _SCHEMA_MAP or not _SCHEMA_MAP[key].get("is_secret"):
                errors.append({"key": key, "error": f"未知密钥项: {key}"})
            else:
                secret_applied.append(key)
        for key in clear_secrets:
            if key not in _SCHEMA_MAP or not _SCHEMA_MAP[key].get("is_secret"):
                errors.append({"key": key, "error": f"未知密钥项: {key}"})

        if errors and not applied and not secret_applied and not clear_secrets:
            return [], [], [], errors

        with self._session_scope() as db:
            for key in applied:
                schema = _SCHEMA_MAP[key]
                self._upsert_setting(db, key, normal_updates[key], schema)
            if applied:
                db.commit()

        secret_store = self._load_secret_store()
        for key in secret_applied:
            secret_store[key] = secret_updates[key]
        for key in clear_secrets:
            secret_store.pop(key, None)
        if secret_applied or clear_secrets:
            self._save_secret_store(secret_store)

        changed = applied + secret_applied + clear_secrets
        rescheduled = [key for key in changed if key in RESCHEDULE_KEYS]
        return changed, rescheduled, restart_required, errors

    def reset_settings(self, keys: list[str]) -> list[str]:
        with self._session_scope() as db:
            for key in keys:
                db.query(AppSetting).filter(AppSetting.key == key).delete()
            db.commit()
        secret_store = self._load_secret_store()
        changed = False
        for key in keys:
            if key in secret_store:
                secret_store.pop(key, None)
                changed = True
        if changed:
            self._save_secret_store(secret_store)
        return keys

    def load_effective_values(self) -> dict[str, Any]:
        settings = get_settings()
        values = {item["key"]: getattr(settings, item["key"], item.get("default", "")) for item in SETTINGS_SCHEMA}
        with self._session_scope() as db:
            for record in db.query(AppSetting).all():
                schema = _SCHEMA_MAP.get(record.key)
                if schema:
                    values[record.key] = self._deserialize_value(record.value, schema)
        for key, value in self._load_secret_store().items():
            values[key] = value
        return values

    def apply_runtime_settings(self) -> None:
        effective = self.load_effective_values()
        for key, value in effective.items():
            if value is None:
                continue
            os.environ[key.upper()] = self._stringify(value)
        get_settings.cache_clear()

    def reload_runtime(self, app: Any | None = None) -> dict[str, list[str]]:
        self.apply_runtime_settings()
        reloaded: list[str] = []
        rescheduled: list[str] = []
        if app is not None:
            scheduler = getattr(app.state, "report_scheduler", None)
            if scheduler and hasattr(scheduler, "reload_settings"):
                scheduler.reload_settings()
                reloaded.append("report_scheduler")
                rescheduled.append("report_scheduler")
            auto_sync = getattr(app.state, "auto_sync", None)
            if auto_sync and hasattr(auto_sync, "reload_settings"):
                auto_sync.reload_settings()
                reloaded.append("auto_sync")
                rescheduled.append("auto_sync")
            bot_consumer = getattr(app.state, "bot_consumer", None)
            if bot_consumer and hasattr(bot_consumer, "reload_settings"):
                bot_consumer.reload_settings()
                reloaded.append("bot_consumer")
        return {"reloaded": reloaded, "rescheduled": rescheduled}

    def _session_scope(self):
        if self.db is not None:
            return _StaticSessionContext(self.db)
        return _ManagedSessionContext()

    def _upsert_setting(self, db: Session, key: str, value: Any, schema: dict[str, Any]) -> None:
        record = db.query(AppSetting).filter(AppSetting.key == key).one_or_none()
        if record is None:
            record = AppSetting(key=key)
            db.add(record)
        record.value = self._stringify(self._coerce_value(value, schema))
        record.value_type = schema.get("type", "string")
        record.category = schema.get("category", "general")
        record.is_secret = bool(schema.get("is_secret"))
        record.requires_restart = bool(schema.get("requires_restart"))

    def _coerce_value(self, value: Any, schema: dict[str, Any]) -> Any:
        value_type = schema.get("type", "string")
        if value_type == "integer":
            return int(value)
        if value_type == "number":
            return float(value)
        if value_type == "boolean":
            if isinstance(value, bool):
                return value
            if str(value).lower() in {"true", "1", "yes", "on"}:
                return True
            if str(value).lower() in {"false", "0", "no", "off"}:
                return False
            raise ValueError(f"布尔值应为 true/false，收到: {value}")
        if value_type == "select":
            text = str(value)
            options = schema.get("options", [])
            if options and text not in options:
                raise ValueError(f"可选值为 {options}，收到: {value}")
            return text
        return str(value) if value is not None else ""

    def _deserialize_value(self, value: str, schema: dict[str, Any]) -> Any:
        value_type = schema.get("type", "string")
        if value_type == "integer":
            return int(value)
        if value_type == "number":
            return float(value)
        if value_type == "boolean":
            return value.lower() in {"true", "1", "yes", "on"}
        return value

    def _secret_path(self) -> Path:
        settings = get_settings()
        return settings.storage_dir / "settings.secrets.json"

    def _load_secret_store(self) -> dict[str, str]:
        path = self._secret_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to read secret store %s: %s", path, exc)
            return {}

    def _save_secret_store(self, data: dict[str, str]) -> None:
        path = self._secret_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            logger.warning("Secret store permissions could not be tightened on this platform")

    @staticmethod
    def _stringify(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)


class _ManagedSessionContext:
    def __enter__(self) -> Session:
        self.db = SessionLocal()
        return self.db

    def __exit__(self, exc_type, exc, tb) -> None:
        self.db.close()


class _StaticSessionContext:
    def __init__(self, db: Session) -> None:
        self.db = db

    def __enter__(self) -> Session:
        return self.db

    def __exit__(self, exc_type, exc, tb) -> None:
        return None
