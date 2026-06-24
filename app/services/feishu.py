import json
import logging
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.exceptions import FeishuError
from app.models import Event, SyncLog
from app.services.event_policy import EventPolicyService
from app.utils.constants import EventStatus
from app.utils.lark_cli import build_lark_cli_command, is_lark_cli
from app.utils.time import utcnow

# 字段构建逻辑拆分到独立模块，此处 re-export 保持外部 import 兼容
from app.services.feishu_fields import (
    SELECT_OPTIONS,
    build_record_fields,
    checkbox,
    existing_poster_files,
    multi_select_texts,
    number,
    select_text,
    to_datetime_str,
    url_link,
)

logger = logging.getLogger(__name__)


class FeishuAdapter:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.client = _build_client(db)

    def sync_event(self, event: Event) -> dict[str, Any]:
        decision = EventPolicyService(self.db).apply(event)
        if not event.is_event_related and not event.user_keep:
            result = self.client.delete_event(event) if event.feishu_record_id else {
                "return_code": 0,
                "stdout": "Skipped Feishu sync for non-event promotional content.",
                "stderr": event.relevance_reason,
                "dry_run": self.client.settings.feishu_dry_run,
                "record_id": "",
            }
            event.feishu_record_id = ""
            event.status = EventStatus.IGNORED_NON_EVENT
            event.updated_at = utcnow()
            self.db.commit()
            return {
                "status": event.status,
                "dry_run": result["dry_run"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
            }
        if decision.should_remove_from_feishu and not event.user_keep:
            result = self.client.delete_event(event) if event.feishu_record_id else {
                "return_code": 0,
                "stdout": "Skipped Feishu sync for expired or stale event without an existing record.",
                "stderr": "",
                "dry_run": self.client.settings.feishu_dry_run,
                "record_id": "",
            }
            event.feishu_record_id = ""
            event.updated_at = utcnow()
            self.db.commit()
            return {
                "status": event.status,
                "dry_run": result["dry_run"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
            }
        result = self.client.upsert_event(event)
        if result["return_code"] == 0:
            event.status = EventStatus.SYNCED
            if not event.feishu_record_id:
                event.feishu_record_id = result.get("record_id", "")
            event.updated_at = utcnow()
        else:
            event.status = EventStatus.FAILED_SYNC
        self.db.commit()
        return {
            "status": event.status,
            "dry_run": result["dry_run"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
        }


class BaseFeishuClient:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def _log(self, target: str, target_id: str, command: str, result: dict[str, Any], attempt: int) -> None:
        self.db.add(
            SyncLog(
                target=target,
                target_id=target_id,
                command=f"attempt={attempt} {command}",
                return_code=result["return_code"],
                stdout=result["stdout"],
                stderr=result["stderr"],
            )
        )
        self.db.flush()

    def delete_event(self, event: Event) -> dict[str, Any]:
        raise NotImplementedError


class FeishuCLIClient(BaseFeishuClient):
    def upsert_event(self, event: Event) -> dict[str, Any]:
        payload = {"record_id": event.feishu_record_id, "fields": build_record_fields(event)}
        command = [self.settings.feishu_cli_path, "bitable", "record", "upsert", json.dumps(payload, ensure_ascii=False)]
        if self.settings.feishu_dry_run:
            stdout = json.dumps({"dry_run": True, "provider": "cli", "payload": payload}, ensure_ascii=False)
            result = {
                "return_code": 0,
                "stdout": stdout,
                "stderr": "",
                "dry_run": True,
                "record_id": event.feishu_record_id,
            }
            self._log("feishu_event", event.event_id, " ".join(command), result, attempt=1)
            return result
        last_result: dict[str, Any] | None = None
        for attempt in range(1, self.settings.feishu_max_retries + 1):
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
            record_id = _parse_record_id(completed.stdout) or event.feishu_record_id
            last_result = {
                "return_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "dry_run": False,
                "record_id": record_id,
            }
            self._log("feishu_event", event.event_id, " ".join(command), last_result, attempt=attempt)
            if completed.returncode == 0:
                return last_result
            if attempt < self.settings.feishu_max_retries:
                time.sleep(self.settings.feishu_retry_delay_seconds)
        return last_result or {
            "return_code": 1,
            "stdout": "",
            "stderr": "Feishu sync failed without a process result.",
            "dry_run": False,
            "record_id": event.feishu_record_id,
        }

    def send_message(self, content: str) -> dict[str, Any]:
        command = [self.settings.feishu_cli_path, "message", "send", content]
        if self.settings.feishu_dry_run:
            result = {"return_code": 0, "stdout": content, "stderr": "", "dry_run": True}
            self._log("feishu_message", "", " ".join(command), result, attempt=1)
            return result
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
        result = {
            "return_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "dry_run": False,
        }
        self._log("feishu_message", "", " ".join(command), result, attempt=1)
        return result

    def delete_event(self, event: Event) -> dict[str, Any]:
        raise NotImplementedError("Legacy feishu CLI delete is not implemented in V1.")


class LarkCLIClient(BaseFeishuClient):
    def upsert_event(self, event: Event) -> dict[str, Any]:
        payload = build_record_fields(event)
        command = [
            *self._command_prefix(),
            "base",
            "+record-upsert",
            "--as",
            self.settings.feishu_cli_as,
            "--base-token",
            self.settings.feishu_bitable_app_token,
            "--table-id",
            self.settings.feishu_bitable_table_id,
            "--json",
            json.dumps(payload, ensure_ascii=False),
            "--format",
            "json",
        ]
        if event.feishu_record_id:
            command.extend(["--record-id", event.feishu_record_id])
        if self.settings.feishu_dry_run:
            stdout = json.dumps({"dry_run": True, "provider": "lark-cli", "payload": payload}, ensure_ascii=False)
            result = {
                "return_code": 0,
                "stdout": stdout,
                "stderr": "",
                "dry_run": True,
                "record_id": event.feishu_record_id,
            }
            self._log("feishu_event", event.event_id, " ".join(command), result, attempt=1)
            return result
        self._ensure_cli_config()
        last_result: dict[str, Any] | None = None
        for attempt in range(1, self.settings.feishu_max_retries + 1):
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
            record_id = _parse_lark_record_id(completed.stdout) or event.feishu_record_id
            last_result = {
                "return_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "dry_run": False,
                "record_id": record_id,
            }
            self._log("feishu_event", event.event_id, " ".join(command), last_result, attempt=attempt)
            if completed.returncode == 0:
                if record_id:
                    self._upload_poster_attachments(event, record_id)
                return last_result
            if attempt < self.settings.feishu_max_retries:
                time.sleep(self.settings.feishu_retry_delay_seconds)
        return last_result or {
            "return_code": 1,
            "stdout": "",
            "stderr": "Lark CLI sync failed without a process result.",
            "dry_run": False,
            "record_id": event.feishu_record_id,
        }

    def send_message(self, content: str) -> dict[str, Any]:
        raise NotImplementedError("Lark CLI message sending is not implemented in V1.")

    def delete_event(self, event: Event) -> dict[str, Any]:
        if not event.feishu_record_id:
            return {"return_code": 0, "stdout": "No Feishu record to delete.", "stderr": "", "dry_run": False, "record_id": ""}
        command = [
            *self._command_prefix(),
            "base",
            "+record-delete",
            "--as",
            self.settings.feishu_cli_as,
            "--base-token",
            self.settings.feishu_bitable_app_token,
            "--table-id",
            self.settings.feishu_bitable_table_id,
            "--record-id",
            event.feishu_record_id,
            "--yes",
            "--format",
            "json",
        ]
        if self.settings.feishu_dry_run:
            result = {
                "return_code": 0,
                "stdout": json.dumps({"dry_run": True, "provider": "lark-cli", "delete_record_id": event.feishu_record_id}, ensure_ascii=False),
                "stderr": "",
                "dry_run": True,
                "record_id": "",
            }
            self._log("feishu_delete", event.event_id, " ".join(command), result, attempt=1)
            return result
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
        result = {
            "return_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "dry_run": False,
            "record_id": "",
        }
        self._log("feishu_delete", event.event_id, " ".join(command), result, attempt=1)
        return result

    def _ensure_cli_config(self) -> None:
        required = {
            "FEISHU_CLI_PATH": self.settings.feishu_cli_path,
            "FEISHU_CLI_AS": self.settings.feishu_cli_as,
            "FEISHU_BITABLE_APP_TOKEN": self.settings.feishu_bitable_app_token,
            "FEISHU_BITABLE_TABLE_ID": self.settings.feishu_bitable_table_id,
        }
        missing = [key for key, value in required.items() if not value.strip()]
        if missing:
            raise FeishuError(f"Missing Lark CLI config: {', '.join(missing)}")

    def _command_prefix(self) -> list[str]:
        return build_lark_cli_command(self.settings.feishu_cli_path)

    def _upload_poster_attachments(self, event: Event, record_id: str) -> None:
        files = existing_poster_files(event)
        if not files:
            return
        command = [
            *self._command_prefix(),
            "base",
            "+record-upload-attachment",
            "--as",
            self.settings.feishu_cli_as,
            "--base-token",
            self.settings.feishu_bitable_app_token,
            "--table-id",
            self.settings.feishu_bitable_table_id,
            "--record-id",
            record_id,
            "--field-id",
            self.settings.feishu_poster_attachment_field,
        ]
        for file_path in files:
            command.extend(["--file", file_path])
        command.extend(["--format", "json"])
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        result = {
            "return_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "dry_run": False,
        }
        self._log("feishu_attachment", event.event_id, " ".join(command), result, attempt=1)
        if completed.returncode != 0:
            raise FeishuError(completed.stderr or "Failed to upload poster attachments with lark-cli.")


class FeishuOpenAPIClient(BaseFeishuClient):
    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.base_url = self.settings.feishu_base_url.rstrip("/")
        self._access_token = ""
        self._token_expire_at = 0.0

    def upsert_event(self, event: Event) -> dict[str, Any]:
        payload = {"fields": build_record_fields(event)}
        if self.settings.feishu_dry_run:
            stdout = json.dumps({"dry_run": True, "provider": "openapi", "payload": payload}, ensure_ascii=False)
            result = {
                "return_code": 0,
                "stdout": stdout,
                "stderr": "",
                "dry_run": True,
                "record_id": event.feishu_record_id,
            }
            self._log("feishu_event", event.event_id, self._command_preview(event), result, attempt=1)
            return result

        self._ensure_openapi_config()
        last_result: dict[str, Any] | None = None
        for attempt in range(1, self.settings.feishu_max_retries + 1):
            try:
                record_id = self._write_record(event, payload)
                stdout = json.dumps({"provider": "openapi", "record_id": record_id}, ensure_ascii=False)
                result = {
                    "return_code": 0,
                    "stdout": stdout,
                    "stderr": "",
                    "dry_run": False,
                    "record_id": record_id,
                }
                self._log("feishu_event", event.event_id, self._command_preview(event), result, attempt=attempt)
                # 上传海报附件
                self._upload_poster_attachments(event, record_id)
                return result
            except requests.RequestException as exc:
                last_result = {
                    "return_code": 1,
                    "stdout": "",
                    "stderr": str(exc),
                    "dry_run": False,
                    "record_id": event.feishu_record_id,
                }
                self._log("feishu_event", event.event_id, self._command_preview(event), last_result, attempt=attempt)
                if attempt < self.settings.feishu_max_retries:
                    time.sleep(self.settings.feishu_retry_delay_seconds)
        return last_result or {
            "return_code": 1,
            "stdout": "",
            "stderr": "Feishu OpenAPI sync failed without a request result.",
            "dry_run": False,
            "record_id": event.feishu_record_id,
        }

    def send_message(self, content: str) -> dict[str, Any]:
        raise NotImplementedError("OpenAPI message sending is not implemented in V1.")

    def delete_event(self, event: Event) -> dict[str, Any]:
        if not event.feishu_record_id:
            return {"return_code": 0, "stdout": "No Feishu record to delete.", "stderr": "", "dry_run": False, "record_id": ""}
        if self.settings.feishu_dry_run:
            result = {
                "return_code": 0,
                "stdout": json.dumps({"dry_run": True, "provider": "openapi", "delete_record_id": event.feishu_record_id}, ensure_ascii=False),
                "stderr": "",
                "dry_run": True,
                "record_id": "",
            }
            self._log("feishu_delete", event.event_id, self._command_preview(event), result, attempt=1)
            return result
        try:
            response = requests.delete(
                self._record_url(event.feishu_record_id),
                headers=self._headers(),
                timeout=60,
            )
            response.raise_for_status()
            result = {"return_code": 0, "stdout": response.text, "stderr": "", "dry_run": False, "record_id": ""}
            self._log("feishu_delete", event.event_id, self._command_preview(event), result, attempt=1)
            return result
        except requests.RequestException as exc:
            result = {"return_code": 1, "stdout": "", "stderr": str(exc), "dry_run": False, "record_id": ""}
            self._log("feishu_delete", event.event_id, self._command_preview(event), result, attempt=1)
            return result

    def _write_record(self, event: Event, payload: dict[str, Any]) -> str:
        url = self._record_url(event.feishu_record_id)
        body = {"fields": payload["fields"]}
        response = requests.request(
            method="PUT" if event.feishu_record_id else "POST",
            url=url,
            headers=self._headers(),
            json=body,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("code", 0) != 0:
            raise requests.HTTPError(data.get("msg", "Feishu OpenAPI error"), response=response)
        record = data.get("data", {}).get("record", {})
        record_id = str(record.get("record_id") or data.get("data", {}).get("record_id") or event.feishu_record_id)
        if not record_id:
            raise requests.HTTPError("Feishu OpenAPI response did not include record_id.", response=response)
        return record_id

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._tenant_access_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def _tenant_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._token_expire_at:
            return self._access_token
        response = requests.post(
            f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.settings.feishu_app_id, "app_secret": self.settings.feishu_app_secret},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("code", 0) != 0:
            raise requests.HTTPError(data.get("msg", "Failed to obtain Feishu tenant access token"), response=response)
        self._access_token = str(data.get("tenant_access_token", ""))
        expire = int(data.get("expire", 0) or 0)
        self._token_expire_at = now + max(expire - 60, 60)
        if not self._access_token:
            raise requests.HTTPError("Feishu tenant access token missing in response.", response=response)
        return self._access_token

    def _record_url(self, record_id: str) -> str:
        base = (
            f"{self.base_url}/open-apis/bitable/v1/apps/{self.settings.feishu_bitable_app_token}"
            f"/tables/{self.settings.feishu_bitable_table_id}/records"
        )
        return f"{base}/{record_id}" if record_id else base

    def _ensure_openapi_config(self) -> None:
        required = {
            "FEISHU_APP_ID": self.settings.feishu_app_id,
            "FEISHU_APP_SECRET": self.settings.feishu_app_secret,
            "FEISHU_BITABLE_APP_TOKEN": self.settings.feishu_bitable_app_token,
            "FEISHU_BITABLE_TABLE_ID": self.settings.feishu_bitable_table_id,
        }
        missing = [key for key, value in required.items() if not value.strip()]
        if missing:
            raise FeishuError(f"Missing Feishu OpenAPI config: {', '.join(missing)}")

    def _command_preview(self, event: Event) -> str:
        action = "update" if event.feishu_record_id else "create"
        return (
            f"openapi:{action} "
            f"app={self.settings.feishu_bitable_app_token} "
            f"table={self.settings.feishu_bitable_table_id}"
        )

    def _upload_poster_attachments(self, event: Event, record_id: str) -> None:
        """通过 OpenAPI 上传海报图片到飞书 Bitable 附件字段。"""
        files = existing_poster_files(event)
        if not files:
            return

        file_tokens: list[str] = []
        for file_path in files:
            try:
                token = self._upload_file(file_path)
                if token:
                    file_tokens.append(token)
            except Exception as exc:
                logger.warning("Failed to upload %s: %s", file_path, exc)

        if not file_tokens:
            return

        # 将 file_token 写入附件字段
        attachment_field = self.settings.feishu_poster_attachment_field
        try:
            url = self._record_url(record_id)
            body = {"fields": {attachment_field: [{"file_token": t} for t in file_tokens]}}
            response = requests.put(url, headers=self._headers(), json=body, timeout=60)
            response.raise_for_status()
            data = response.json()
            if data.get("code", 0) != 0:
                logger.warning("Failed to write attachment field: %s", data.get("msg"))
            else:
                logger.info("Uploaded %d poster attachments for event %s", len(file_tokens), event.event_id)
        except requests.RequestException as exc:
            logger.warning("Failed to update attachment field for event %s: %s", event.event_id, exc)

    def _upload_file(self, file_path: str) -> str:
        """上传单个文件到飞书，返回 file_token。"""
        from pathlib import Path

        path = Path(file_path)
        if not path.exists():
            return ""
        file_size = path.stat().st_size
        # 飞书 upload_all API 限制 20MB
        max_size = 20 * 1024 * 1024
        if file_size > max_size:
            logger.warning("File %s too large (%d bytes > %d), skipping", path.name, file_size, max_size)
            return ""
        if file_size == 0:
            logger.warning("File %s is empty, skipping", path.name)
            return ""
        url = f"{self.base_url}/open-apis/drive/v1/medias/upload_all"
        with open(path, "rb") as f:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {self._tenant_access_token()}"},
                data={
                    "file_name": path.name,
                    "parent_type": "bitable_image",
                    "parent_node": self.settings.feishu_bitable_app_token,
                    "size": str(file_size),
                },
                files={"file": (path.name, f)},
                timeout=120,
            )
        response.raise_for_status()
        data = response.json()
        if data.get("code", 0) != 0:
            logger.warning("Upload file failed: %s", data.get("msg"))
            return ""
        return str(data.get("data", {}).get("file_token", ""))


def _build_client(db: Session) -> BaseFeishuClient:
    settings = get_settings()
    provider = settings.feishu_provider.lower().strip()
    if provider == "cli":
        return FeishuCLIClient(db)
    if provider == "lark_cli":
        return LarkCLIClient(db)
    if provider == "openapi":
        return FeishuOpenAPIClient(db)
    if provider == "auto":
        if is_lark_cli(settings.feishu_cli_path) and _has_lark_cli_config(settings):
            return LarkCLIClient(db)
        if _has_openapi_config(settings):
            return FeishuOpenAPIClient(db)
        return FeishuCLIClient(db)
    raise FeishuError(f"Unsupported FEISHU_PROVIDER: {settings.feishu_provider}")


def _has_openapi_config(settings: Settings) -> bool:
    return all(
        [
            settings.feishu_app_id.strip(),
            settings.feishu_app_secret.strip(),
            settings.feishu_bitable_app_token.strip(),
            settings.feishu_bitable_table_id.strip(),
        ]
    )


def _has_lark_cli_config(settings: Settings) -> bool:
    return all(
        [
            settings.feishu_cli_path.strip(),
            settings.feishu_cli_as.strip(),
            settings.feishu_bitable_app_token.strip(),
            settings.feishu_bitable_table_id.strip(),
        ]
    )


def _parse_record_id(stdout: str) -> str:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return ""
    return str(data.get("record_id") or data.get("id") or "")


def _parse_lark_record_id(stdout: str) -> str:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return ""
    record_ids = data.get("data", {}).get("record", {}).get("record_id_list") or []
    if record_ids:
        return str(record_ids[0])
    return ""

