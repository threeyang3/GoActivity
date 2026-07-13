"""Automation health, collection, and reconciliation routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.services.automation_guard import AutomationGuardService

router = APIRouter(prefix="/automation", tags=["automation"])


@router.get("/accounts-health")
def accounts_health(db: Session = Depends(get_db)) -> list[dict]:
    return AutomationGuardService(db).account_health()


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
    return AutomationGuardService(db).trigger_priority_collection()
