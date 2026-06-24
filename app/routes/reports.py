"""日报/周报路由。"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.feishu_messenger import FeishuMessenger
from app.services.report_service import ReportService

router = APIRouter(tags=["reports"])


@router.post("/reports/daily")
def daily_report(
    send_to_feishu: bool = False,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    content = ReportService(db).daily_report()
    result: dict[str, Any] = {"content": content}
    if send_to_feishu:
        messenger = FeishuMessenger()
        send_result = messenger.send_daily_report(content)
        result["feishu_sent"] = send_result.get("ok", False)
        if not send_result.get("ok"):
            result["feishu_error"] = send_result.get("error", "")
    return result


@router.post("/reports/weekly")
def weekly_report(
    send_to_feishu: bool = False,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    content = ReportService(db).weekly_report()
    result: dict[str, Any] = {"content": content}
    if send_to_feishu:
        messenger = FeishuMessenger()
        send_result = messenger.send_weekly_report(content)
        result["feishu_sent"] = send_result.get("ok", False)
        if not send_result.get("ok"):
            result["feishu_error"] = send_result.get("error", "")
    return result
