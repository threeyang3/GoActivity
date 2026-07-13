"""Unattended automation checks for sources, Feishu consistency, and alerts."""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any

import requests
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.exceptions import FeishuError
from app.models import AppSetting, Article, Event, SyncRun
from app.services.feishu import FeishuAdapter
from app.services.feishu_fields import build_record_fields, existing_poster_files
from app.services.feishu_messenger import FeishuMessenger
from app.utils.constants import EventStatus
from app.utils.lark_cli import build_lark_cli_command, run_cli_command
from app.utils.time import parse_to_epoch, utcnow

logger = logging.getLogger(__name__)


class AutomationGuardService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def account_health(self) -> list[dict[str, Any]]:
        rows = (
            self.db.query(
                Article.mp_name,
                func.count(Article.id).label("article_count"),
                func.max(Article.publish_time).label("latest_publish"),
                func.max(Article.created_at).label("latest_ingested"),
            )
            .filter(Article.mp_name != "")
            .group_by(Article.mp_name)
            .all()
        )
        event_counts = dict(
            self.db.query(Article.mp_name, func.count(Event.id))
            .join(Event, Event.article_id == Article.article_id)
            .filter(Article.mp_name != "")
            .group_by(Article.mp_name)
            .all()
        )
        now = utcnow()
        threshold = max(1, self.settings.account_stale_hours)
        result = []
        for row in rows:
            age_hours = None
            if row.latest_ingested:
                age_hours = round((now - row.latest_ingested).total_seconds() / 3600, 1)
            result.append({
                "mp_name": row.mp_name,
                "article_count": row.article_count,
                "event_count": event_counts.get(row.mp_name, 0),
                "latest_publish_time": row.latest_publish,
                "latest_publish_epoch": parse_to_epoch(row.latest_publish or ""),
                "latest_ingested_at": row.latest_ingested.isoformat() if row.latest_ingested else None,
                "stale_hours": age_hours,
                "stale_days": int(age_hours // 24) if age_hours is not None else None,
                "sla_hours": threshold,
                "status": "stale" if age_hours is None or age_hours >= threshold else "ok",
            })
        return sorted(result, key=lambda item: (item["status"] != "stale", item["mp_name"]))

    def trigger_priority_collection(self) -> dict[str, Any]:
        accounts = self._list_remote_accounts()
        configured = {
            name.strip() for name in self.settings.priority_accounts.split(",") if name.strip()
        }
        selected = [item for item in accounts if not configured or item.get("mp_name") in configured]
        triggered = []
        failed = []
        for item in selected[:50]:
            mp_id = str(item.get("mp_id") or item.get("id") or "")
            if not mp_id:
                continue
            try:
                response = requests.get(
                    f"{self._mps_url()}/update/{mp_id}",
                    headers=self._rss_headers(),
                    timeout=30,
                )
                response.raise_for_status()
                triggered.append(item.get("mp_name") or mp_id)
            except Exception as exc:
                failed.append({"mp_name": item.get("mp_name") or mp_id, "error": str(exc)[:200]})
        return {"selected": len(selected), "triggered": triggered, "failed": failed}

    def reconcile_feishu(self, repair_missing: bool = False) -> dict[str, Any]:
        remote = self._list_feishu_records()
        remote_by_id = {item["record_id"]: item for item in remote if item.get("record_id")}
        tracked_events = self.db.query(Event).filter(Event.feishu_record_id != "").all()
        events = [event for event in tracked_events if event.status not in EventStatus.TERMINAL_STATUSES]
        if events and not remote_by_id:
            raise FeishuError("飞书记录查询返回空集，已停止对账，避免将读取异常误判为记录缺失")
        matched_records = sum(event.feishu_record_id in remote_by_id for event in events)
        if repair_missing and events and matched_records == 0:
            raise FeishuError("本地记录与飞书查询结果没有交集，已拒绝自动修复，请检查 Base 和数据表配置")
        missing = []
        drifted = []
        attachment_missing = []
        repaired = []
        poster_field = self.settings.feishu_poster_attachment_field

        for event in events:
            record = remote_by_id.get(event.feishu_record_id)
            if not record:
                missing.append(event.event_id)
                if repair_missing:
                    event.feishu_record_id = ""
                    event.status = EventStatus.EXTRACTED
                    result = FeishuAdapter(self.db).sync_event(event)
                    if result.get("status") == EventStatus.SYNCED:
                        repaired.append(event.event_id)
                continue
            remote_fields = record.get("fields") or {}
            expected = build_record_fields(event)
            if self._plain(remote_fields.get("标题")) != self._plain(expected.get("标题")):
                drifted.append(event.event_id)
            if existing_poster_files(event) and not remote_fields.get(poster_field):
                attachment_missing.append(event.event_id)

        return {
            "local_records": len(events),
            "skipped_terminal_records": len(tracked_events) - len(events),
            "remote_records": len(remote),
            "matched_records": matched_records,
            "safe_to_repair": not events or not missing or matched_records > 0,
            "missing_record_ids": missing,
            "field_drift_event_ids": drifted,
            "missing_attachment_event_ids": attachment_missing,
            "repaired_event_ids": repaired,
        }

    def send_alerts(
        self,
        sync_result: dict[str, Any] | None = None,
        reconcile: dict[str, Any] | None = None,
        collection_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.settings.automation_alerts_enabled:
            return {"sent": False, "reason": "disabled"}
        issues = []
        failed_sync = self.db.query(func.count(Event.id)).filter(Event.status == EventStatus.FAILED_SYNC).scalar() or 0
        exhausted = self.db.query(func.count(Event.id)).filter(
            Event.status == EventStatus.FAILED_SYNC,
            Event.feishu_retry_count >= self.settings.feishu_sync_retry_max,
        ).scalar() or 0
        stale = [item for item in self.account_health() if item["status"] == "stale"]
        pending = self.db.query(func.count(Event.id)).filter(
            Event.status.in_([EventStatus.EXTRACTED, EventStatus.PENDING_AI]),
            Event.feishu_record_id == "",
        ).scalar() or 0
        low_confidence = self.db.query(func.count(Event.id)).filter(
            Event.confidence > 0,
            Event.confidence < 0.3,
            Event.status.notin_(EventStatus.TERMINAL_STATUSES),
        ).scalar() or 0
        recent_runs = self.db.query(SyncRun).filter(SyncRun.source == "auto-sync").order_by(SyncRun.started_at.desc()).limit(3).all()
        consecutive_failures = 0
        for run in recent_runs:
            if run.status != "failed":
                break
            consecutive_failures += 1
        if failed_sync:
            issues.append(f"飞书同步失败待重试：{failed_sync} 条（已耗尽：{exhausted} 条）")
        if stale:
            issues.append("公众号超过 SLA：" + "、".join(item["mp_name"] for item in stale[:8]))
        if pending >= 10:
            issues.append(f"待同步事件积压：{pending} 条")
        if low_confidence >= 10:
            issues.append(f"低置信度待复核：{low_confidence} 条")
        if consecutive_failures >= 2:
            issues.append(f"自动同步连续失败：{consecutive_failures} 次")
        if sync_result and sync_result.get("events_failed"):
            issues.append(f"本轮飞书写入失败：{sync_result['events_failed']} 条")
        if sync_result and sync_result.get("run_error"):
            issues.append(f"本轮同步异常：{str(sync_result['run_error'])[:160]}")
        if collection_result and collection_result.get("failed"):
            issues.append(f"重点公众号采集触发失败：{len(collection_result['failed'])} 个")
        if reconcile:
            if reconcile.get("missing_record_ids"):
                issues.append(f"飞书缺失记录：{len(reconcile['missing_record_ids'])} 条")
            if reconcile.get("field_drift_event_ids"):
                issues.append(f"飞书字段漂移：{len(reconcile['field_drift_event_ids'])} 条")
            if reconcile.get("missing_attachment_event_ids"):
                issues.append(f"飞书附件缺失：{len(reconcile['missing_attachment_event_ids'])} 条")
        if not issues:
            return {"sent": False, "reason": "no_issues"}

        fingerprint = hashlib.sha256("\n".join(issues).encode("utf-8")).hexdigest()[:16]
        if self._in_cooldown(fingerprint):
            return {"sent": False, "reason": "cooldown", "issues": issues}
        content = "## GoActivity 自动化告警\n\n" + "\n".join(f"- {issue}" for issue in issues)
        result = FeishuMessenger().send_daily_report(content)
        if result.get("ok"):
            self._mark_alert(fingerprint)
        return {"sent": bool(result.get("ok")), "issues": issues, "error": result.get("error", "")}

    def _list_remote_accounts(self) -> list[dict[str, Any]]:
        response = requests.get(self._mps_url(), params={"limit": 200, "offset": 0}, headers=self._rss_headers(), timeout=30)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", payload)
        return data.get("list", data if isinstance(data, list) else [])

    def _mps_url(self) -> str:
        return f"{self.settings.we_mp_rss_base_url}{self.settings.we_mp_rss_api_base}/mps"

    def _rss_headers(self) -> dict[str, str]:
        return {"Authorization": f"AK-SK {self.settings.we_mp_rss_access_key}:{self.settings.we_mp_rss_secret_key}"}

    def _list_feishu_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        offset = 0
        limit = 200
        while True:
            command = [
                *build_lark_cli_command(self.settings.feishu_cli_path), "base", "+record-list",
                "--as", self.settings.feishu_cli_as,
                "--base-token", self.settings.feishu_bitable_app_token,
                "--table-id", self.settings.feishu_bitable_table_id,
                "--field-id", "标题",
                "--field-id", self.settings.feishu_poster_attachment_field,
                "--offset", str(offset),
                "--limit", str(limit),
                "--format", "json",
            ]
            result = run_cli_command(command, timeout=120)
            if result["return_code"] != 0:
                raise FeishuError(result["stderr"] or result["stdout"] or "飞书记录读取失败")
            data = result.get("data") or {}
            while isinstance(data, dict) and isinstance(data.get("data"), dict):
                data = data["data"]
            if not isinstance(data, dict):
                raise FeishuError("飞书记录列表返回了无法识别的数据结构")

            object_page = data.get("items") or data.get("records")
            if isinstance(object_page, list):
                page = [
                    {
                        "record_id": item.get("record_id") or item.get("id") or "",
                        "fields": item.get("fields") or {},
                    }
                    for item in object_page
                    if isinstance(item, dict)
                ]
            else:
                rows = data.get("data")
                record_ids = data.get("record_id_list")
                field_names = data.get("fields") or data.get("field_id_list")
                if not all(isinstance(value, list) for value in (rows, record_ids, field_names)):
                    raise FeishuError("飞书记录列表缺少 records 或字段矩阵")
                page = []
                for record_id, row in zip(record_ids, rows):
                    if isinstance(row, dict):
                        fields = row
                    elif isinstance(row, list):
                        fields = dict(zip(field_names, row))
                    else:
                        fields = {}
                    page.append({"record_id": record_id, "fields": fields})

            records.extend(page)
            has_more = data.get("has_more")
            if has_more is False or (has_more is None and len(page) < limit):
                break
            if not page:
                raise FeishuError("飞书记录分页返回空页但仍声明存在后续数据")
            offset += len(page)
        return records

    @staticmethod
    def _plain(value: Any) -> str:
        if isinstance(value, list):
            return "".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in value)
        if isinstance(value, dict):
            return str(value.get("text") or value.get("value") or value.get("link") or "")
        return str(value or "")

    def _in_cooldown(self, fingerprint: str) -> bool:
        record = self.db.query(AppSetting).filter(AppSetting.key == f"alert:{fingerprint}").one_or_none()
        if not record:
            return False
        try:
            sent_at = datetime.fromisoformat(record.value)
        except ValueError:
            return False
        return utcnow() - sent_at < timedelta(hours=max(1, self.settings.automation_alert_cooldown_hours))

    def _mark_alert(self, fingerprint: str) -> None:
        key = f"alert:{fingerprint}"
        record = self.db.query(AppSetting).filter(AppSetting.key == key).one_or_none()
        if record is None:
            record = AppSetting(key=key, category="automation_internal")
            self.db.add(record)
        record.value = utcnow().isoformat()
        self.db.commit()
