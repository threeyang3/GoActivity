"""Unattended automation checks for sources, Feishu consistency, and alerts."""

import hashlib
import json
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

    def account_health(self, include_remote: bool = False) -> list[dict[str, Any]]:
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
        local_by_name = {row.mp_name: row for row in rows}
        remote_by_name: dict[str, dict[str, Any]] = {}
        remote_error = ""
        if include_remote:
            try:
                remote_by_name = {
                    str(item.get("mp_name") or item.get("name") or ""): item
                    for item in self._list_remote_accounts()
                    if item.get("mp_name") or item.get("name")
                }
            except Exception as exc:
                remote_error = str(exc)[:200]
                logger.warning("Failed to load remote account health: %s", exc)

        account_names = sorted(set(local_by_name) | set(remote_by_name))
        now = utcnow()
        threshold = max(1, self.settings.account_stale_hours)
        result = []
        for mp_name in account_names:
            row = local_by_name.get(mp_name)
            age_hours = None
            latest_ingested = row.latest_ingested if row else None
            latest_publish = row.latest_publish if row else None
            article_count = row.article_count if row else 0
            if latest_ingested:
                age_hours = round((now - row.latest_ingested).total_seconds() / 3600, 1)
            publish_epoch = parse_to_epoch(latest_publish or "")
            publication_age_hours = None
            if publish_epoch is not None:
                publication_age_hours = round(max(0, datetime.now().timestamp() - publish_epoch) / 3600, 1)
            if not row:
                health_status = "never_collected"
            elif age_hours is None:
                health_status = "never_collected"
            elif age_hours >= threshold:
                health_status = "quiet_source" if (
                    publication_age_hours is not None and publication_age_hours >= threshold
                ) else "stale_data"
            else:
                health_status = "fresh"
            status = "ok" if health_status in {"fresh", "quiet_source"} else "stale"
            remote_account = remote_by_name.get(mp_name, {})
            result.append({
                "mp_name": mp_name,
                "mp_id": str(remote_account.get("mp_id") or remote_account.get("id") or ""),
                "remote_subscribed": bool(remote_account),
                "article_count": article_count,
                "event_count": event_counts.get(mp_name, 0),
                "latest_publish_time": latest_publish,
                "latest_publish_epoch": publish_epoch,
                "latest_ingested_at": latest_ingested.isoformat() if latest_ingested else None,
                "stale_hours": age_hours,
                "stale_days": int(age_hours // 24) if age_hours is not None else None,
                "latest_publication_age_hours": publication_age_hours,
                "sla_hours": threshold,
                "status": status,
                "health_status": health_status,
                "remote_error": remote_error or None,
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
        skipped = []
        for item in selected:
            mp_id = str(item.get("mp_id") or item.get("id") or "")
            if not mp_id:
                skipped.append(item.get("mp_name") or "unknown")
                continue
            try:
                response = requests.get(
                    f"{self._mps_url()}/update/{mp_id}",
                    headers=self._rss_headers(),
                    timeout=30,
                )
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict) and payload.get("code", 0) != 0:
                    if payload.get("code") == 42901:
                        skipped.append(item.get("mp_name") or mp_id)
                        continue
                    raise ValueError(str(payload.get("message") or "采集请求未被接受"))
                triggered.append(item.get("mp_name") or mp_id)
            except Exception as exc:
                failed.append({"mp_name": item.get("mp_name") or mp_id, "error": str(exc)[:200]})
        return {
            "selected": len(selected),
            "attempted": len(triggered) + len(failed),
            "triggered": triggered,
            "failed": failed,
            "skipped": skipped,
        }

    def reconcile_feishu(self, repair_missing: bool = False) -> dict[str, Any]:
        remote = self._list_feishu_records()
        remote_by_id = {item["record_id"]: item for item in remote if item.get("record_id")}
        tracked_events = self.db.query(Event).filter(Event.feishu_record_id != "").all()
        events = [event for event in tracked_events if event.status not in EventStatus.TERMINAL_STATUSES]
        if events and not remote_by_id:
            raise FeishuError("飞书记录查询返回空集，已停止对账，避免将读取异常误判为记录缺失")
        matched_records = sum(event.feishu_record_id in remote_by_id for event in events)
        missing = []
        drifted = []
        attachment_missing = []
        repaired = []
        repair_failed = []
        poster_field = self.settings.feishu_poster_attachment_field

        local_record_ids = {event.feishu_record_id for event in tracked_events if event.feishu_record_id}
        remote_only = sorted(set(remote_by_id) - local_record_ids)
        missing_ratio = round(
            len([event for event in events if event.feishu_record_id])
            and sum(event.feishu_record_id not in remote_by_id for event in events)
            / len([event for event in events if event.feishu_record_id]),
            4,
        )
        missing_ids = [event.event_id for event in events if event.feishu_record_id not in remote_by_id]
        missing = list(missing_ids)
        snapshot = {
            "remote_signature": self._signature(sorted(remote_by_id)),
            "remote_count": len(remote_by_id),
            "missing_signature": self._signature(sorted(missing_ids)),
            "missing_ids": sorted(missing_ids),
            "observed_at": utcnow().isoformat(),
        }
        previous_snapshot = self._load_internal_json("automation:feishu_reconcile:last")
        snapshot_confirmed = self._snapshot_matches(previous_snapshot, snapshot)
        max_missing_ratio = min(
            0.9, max(0.0, float(self.settings.feishu_reconcile_max_missing_ratio))
        )
        safe_to_repair = not missing or (
            matched_records > 0
            and missing_ratio <= max_missing_ratio
            and snapshot_confirmed
        )

        # A repair request performs an independent second read. This protects against
        # a transient or partial Feishu response that happens to contain one match.
        if repair_missing and missing and safe_to_repair:
            confirmation = self._list_feishu_records()
            confirmation_ids = {
                item.get("record_id") for item in confirmation if item.get("record_id")
            }
            if self._signature(sorted(confirmation_ids)) != snapshot["remote_signature"]:
                safe_to_repair = False
                self._save_internal_json("automation:feishu_reconcile:last", snapshot)
                raise FeishuError("飞书记录两次读取结果不一致，已取消自动修复")

        if repair_missing and missing and not safe_to_repair:
            self._save_internal_json("automation:feishu_reconcile:last", snapshot)
            if matched_records == 0:
                raise FeishuError("本地记录与飞书查询结果没有交集，已拒绝自动修复，请先确认 Base 和数据表配置")
            raise FeishuError("检测到飞书缺失记录，但尚未通过稳定快照确认；请先执行一次只读对账后重试")

        for event in events:
            record = remote_by_id.get(event.feishu_record_id)
            if not record:
                if repair_missing:
                    event.feishu_record_id = ""
                    event.status = EventStatus.EXTRACTED
                    try:
                        result = FeishuAdapter(self.db).sync_event(event)
                        if result.get("status") == EventStatus.SYNCED:
                            repaired.append(event.event_id)
                        else:
                            repair_failed.append(event.event_id)
                    except Exception as exc:
                        repair_failed.append(event.event_id)
                        logger.error("Failed to repair Feishu event %s: %s", event.event_id, exc)
                continue
            remote_fields = record.get("fields") or {}
            expected = build_record_fields(event)
            if self._plain(remote_fields.get("标题")) != self._plain(expected.get("标题")):
                drifted.append(event.event_id)
            if existing_poster_files(event) and not remote_fields.get(poster_field):
                attachment_missing.append(event.event_id)

        self._save_internal_json("automation:feishu_reconcile:last", snapshot)
        return {
            "local_records": len(events),
            "skipped_terminal_records": len(tracked_events) - len(events),
            "remote_records": len(remote),
            "matched_records": matched_records,
            "missing_ratio": missing_ratio,
            "max_missing_ratio": max_missing_ratio,
            "snapshot_confirmed": snapshot_confirmed,
            "safe_to_repair": safe_to_repair,
            "missing_record_ids": missing,
            "field_drift_event_ids": drifted,
            "missing_attachment_event_ids": attachment_missing,
            "repaired_event_ids": repaired,
            "repair_failed_event_ids": repair_failed,
            "remote_only_record_ids": remote_only,
        }

    @staticmethod
    def _signature(values: list[str]) -> str:
        return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]

    def _load_internal_json(self, key: str) -> dict[str, Any] | None:
        record = self.db.query(AppSetting).filter(AppSetting.key == key).one_or_none()
        if not record:
            return None
        try:
            value = json.loads(record.value)
            return value if isinstance(value, dict) else None
        except (TypeError, ValueError):
            return None

    def _save_internal_json(self, key: str, value: dict[str, Any]) -> None:
        record = self.db.query(AppSetting).filter(AppSetting.key == key).one_or_none()
        if record is None:
            record = AppSetting(key=key, category="automation_internal")
            self.db.add(record)
        record.value = json.dumps(value, ensure_ascii=False)
        record.value_type = "json"
        record.category = "automation_internal"
        self.db.commit()

    def _snapshot_matches(self, previous: dict[str, Any] | None, current: dict[str, Any]) -> bool:
        if not previous:
            return False
        if previous.get("remote_signature") != current.get("remote_signature"):
            return False
        if previous.get("missing_signature") != current.get("missing_signature"):
            return False
        try:
            observed_at = datetime.fromisoformat(str(previous.get("observed_at")))
        except (TypeError, ValueError):
            return False
        age = utcnow() - observed_at.replace(tzinfo=None)
        return age <= timedelta(hours=max(1, self.settings.feishu_reconcile_snapshot_hours))

    def send_alerts(
        self,
        sync_result: dict[str, Any] | None = None,
        reconcile: dict[str, Any] | None = None,
        collection_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.settings.automation_alerts_enabled:
            return {"sent": False, "reason": "disabled"}
        issue_entries: list[tuple[str, str]] = []
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
            issue_entries.append(("failed_sync", f"飞书同步失败待重试：{failed_sync} 条（已耗尽：{exhausted} 条）"))
        if stale:
            issue_entries.append(("account_stale", "公众号超过 SLA：" + "、".join(item["mp_name"] for item in stale[:8])))
        if pending >= 10:
            issue_entries.append(("pending_events", f"待同步事件积压：{pending} 条"))
        if low_confidence >= 10:
            issue_entries.append(("low_confidence", f"低置信度待复核：{low_confidence} 条"))
        if consecutive_failures >= 2:
            issue_entries.append(("consecutive_failures", f"自动同步连续失败：{consecutive_failures} 次"))
        if sync_result and sync_result.get("events_failed"):
            issue_entries.append(("sync_events_failed", f"本轮飞书写入失败：{sync_result['events_failed']} 条"))
        if sync_result and sync_result.get("articles_failed"):
            issue_entries.append(("article_ingest_failed", f"本轮文章处理失败：{sync_result['articles_failed']} 篇"))
        if sync_result and sync_result.get("run_status") == "degraded":
            issue_entries.append(("sync_degraded", "本轮自动同步完成但存在部分失败"))
        if sync_result and sync_result.get("run_error"):
            issue_entries.append(("sync_error", f"本轮同步异常：{str(sync_result['run_error'])[:160]}"))
        if collection_result and collection_result.get("failed"):
            issue_entries.append(("priority_collection_failed", f"重点公众号采集触发失败：{len(collection_result['failed'])} 个"))
        if reconcile:
            if reconcile.get("run_error"):
                issue_entries.append(("reconcile_error", f"飞书对账异常：{str(reconcile['run_error'])[:160]}"))
            if reconcile.get("missing_record_ids"):
                issue_entries.append(("reconcile_missing", f"飞书缺失记录：{len(reconcile['missing_record_ids'])} 条"))
            if reconcile.get("field_drift_event_ids"):
                issue_entries.append(("reconcile_drift", f"飞书字段漂移：{len(reconcile['field_drift_event_ids'])} 条"))
            if reconcile.get("missing_attachment_event_ids"):
                issue_entries.append(("reconcile_attachment", f"飞书附件缺失：{len(reconcile['missing_attachment_event_ids'])} 条"))
            if reconcile.get("repair_failed_event_ids"):
                issue_entries.append(("reconcile_repair_failed", f"飞书缺失记录修复失败：{len(reconcile['repair_failed_event_ids'])} 条"))
            if reconcile.get("remote_only_record_ids"):
                issue_entries.append(("reconcile_remote_only", f"飞书存在本地未关联记录：{len(reconcile['remote_only_record_ids'])} 条"))
        issues = [message for _, message in issue_entries]
        if not issues:
            return {"sent": False, "reason": "no_issues"}

        fingerprint = hashlib.sha256(
            "|".join(sorted(key for key, _ in issue_entries)).encode("utf-8")
        ).hexdigest()[:16]
        if self._in_cooldown(fingerprint):
            return {"sent": False, "reason": "cooldown", "issues": issues}
        content = "## GoActivity 自动化告警\n\n" + "\n".join(f"- {issue}" for issue in issues)
        result = FeishuMessenger().send_daily_report(content)
        if result.get("ok"):
            self._mark_alert(fingerprint)
        return {"sent": bool(result.get("ok")), "issues": issues, "error": result.get("error", "")}

    def record_maintenance_result(
        self,
        job: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: str = "",
    ) -> None:
        self._save_internal_json(
            f"automation:maintenance:{job}",
            {
                "job": job,
                "status": status,
                "result": result or {},
                "error": error[:500],
                "finished_at": utcnow().isoformat(),
            },
        )

    def maintenance_status(self) -> dict[str, Any]:
        result = {}
        for job in ("priority_collection", "feishu_reconcile", "startup_archive"):
            value = self._load_internal_json(f"automation:maintenance:{job}")
            if value:
                result[job] = value
        return result

    def _list_remote_accounts(self) -> list[dict[str, Any]]:
        accounts: list[dict[str, Any]] = []
        offset = 0
        # WeRSS validates this endpoint at 100 rows per page.
        limit = 100
        while True:
            response = requests.get(
                self._mps_url(),
                params={"limit": limit, "offset": offset},
                headers=self._rss_headers(),
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data", payload)
            if isinstance(data, dict):
                page = data.get("list") or data.get("items") or []
                has_more = data.get("has_more")
            else:
                page = data if isinstance(data, list) else []
                has_more = None
            if not isinstance(page, list):
                raise FeishuError("公众号列表返回了无法识别的数据结构")
            accounts.extend(item for item in page if isinstance(item, dict))
            if has_more is False or (has_more is None and len(page) < limit):
                break
            if not page:
                raise FeishuError("公众号列表分页返回空页但仍声明存在后续数据")
            offset += len(page)
        return accounts

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
        cutoff = utcnow() - timedelta(days=30)
        for old in self.db.query(AppSetting).filter(
            AppSetting.category == "automation_internal",
            AppSetting.key.like("alert:%"),
        ).all():
            try:
                old_sent_at = datetime.fromisoformat(old.value)
            except ValueError:
                old_sent_at = cutoff - timedelta(seconds=1)
            if old_sent_at < cutoff and old.key != f"alert:{fingerprint}":
                self.db.delete(old)
        key = f"alert:{fingerprint}"
        record = self.db.query(AppSetting).filter(AppSetting.key == key).one_or_none()
        if record is None:
            record = AppSetting(key=key, category="automation_internal")
            self.db.add(record)
        record.value = utcnow().isoformat()
        self.db.commit()
