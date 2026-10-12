"""Automation health, collection, and reconciliation routes."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.services.automation_guard import AutomationGuardService

router = APIRouter(prefix="/automation", tags=["automation"])


@router.get("/accounts-health")
def accounts_health(db: Session = Depends(get_db)) -> list[dict]:
    return AutomationGuardService(db).account_health(include_remote=True)


@router.get("/status")
def automation_status(request: Request, db: Session = Depends(get_db)) -> dict:
    auto_sync = getattr(request.app.state, "auto_sync", None)
    scheduler = auto_sync.get_scheduler_status() if auto_sync else {"status": "unknown"}
    from app.config import get_settings
    from app.services.backup_status import backup_status
    backup = backup_status(get_settings())
    return {
        "scheduler": scheduler,
        "maintenance": AutomationGuardService(db).maintenance_status(),
        "collection": AutomationGuardService(db).collection_health(),
        "backup": backup,
    }


@router.get("/feishu-reconcile")
def feishu_reconcile_preview(db: Session = Depends(get_db)) -> dict:
    return AutomationGuardService(db).reconcile_feishu(repair_missing=False)


@router.post("/feishu-reconcile")
def feishu_reconcile_repair(
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin),
) -> dict:
    return AutomationGuardService(db).reconcile_feishu(repair_missing=True)


@router.post("/collect-priority")
def collect_priority(
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin),
) -> dict:
    guard = AutomationGuardService(db)
    result = guard.trigger_priority_collection()
    guard.record_maintenance_result(
        "priority_collection",
        "degraded" if result.get("failed") or result.get("blocked") else "completed",
        result,
    )
    guard.send_alerts(collection_result=result)
    return result
