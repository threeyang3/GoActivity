from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.models import SyncLog


def test_list_sync_logs_returns_latest_entries() -> None:
    init_db()
    db = SessionLocal()
    log = SyncLog(
        target="feishu_event",
        target_id="event_123",
        command="attempt=1 feishu bitable record upsert",
        return_code=0,
        stdout="ok",
        stderr="",
    )
    db.add(log)
    db.commit()
    try:
        with TestClient(app) as client:
            response = client.get("/sync/logs", params={"limit": 5})

        assert response.status_code == 200
        body = response.json()
        assert any(item["target_id"] == "event_123" for item in body)
    finally:
        db.query(SyncLog).filter(SyncLog.target_id == "event_123").delete()
        db.commit()
        db.close()


def test_sync_summary_aggregates_success_and_failure() -> None:
    init_db()
    db = SessionLocal()
    logs = [
        SyncLog(
            target="feishu_event",
            target_id="event_ok",
            command="attempt=1 ok",
            return_code=0,
            stdout="ok",
            stderr="",
        ),
        SyncLog(
            target="feishu_event",
            target_id="event_fail",
            command="attempt=1 fail",
            return_code=1,
            stdout="",
            stderr="failed once",
        ),
    ]
    db.add_all(logs)
    db.commit()
    try:
        with TestClient(app) as client:
            response = client.get("/sync/summary", params={"failure_limit": 5})

        assert response.status_code == 200
        body = response.json()
        assert body["total_logs"] >= 2
        target = next(item for item in body["targets"] if item["target"] == "feishu_event")
        assert target["success"] >= 1
        assert target["failed"] >= 1
        assert any(item["target_id"] == "event_fail" for item in body["latest_failures"])
    finally:
        db.query(SyncLog).filter(SyncLog.target_id.in_(["event_ok", "event_fail"])).delete(synchronize_session=False)
        db.commit()
        db.close()
