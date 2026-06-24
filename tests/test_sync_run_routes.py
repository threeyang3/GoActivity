from fastapi.testclient import TestClient
from datetime import timedelta

from app.db import SessionLocal, init_db
from app.main import app
from app.models import SyncRun
from app.utils.time import utcnow


def test_list_sync_runs_returns_entries() -> None:
    init_db()
    db = SessionLocal()
    run = SyncRun(
        run_id="sync_run_test_1",
        source="we-mp-rss-rss:all",
        status="completed",
        imported_count=2,
        params_json='{"limit":2}',
        result_preview='[{"article_id":"a"}]',
    )
    db.add(run)
    db.commit()
    try:
        with TestClient(app) as client:
            response = client.get("/sync/runs", params={"limit": 5})

        assert response.status_code == 200
        body = response.json()
        assert any(item["run_id"] == "sync_run_test_1" for item in body)
    finally:
        db.query(SyncRun).filter(SyncRun.run_id == "sync_run_test_1").delete()
        db.commit()
        db.close()


def test_sync_runs_summary_returns_latest_runs() -> None:
    init_db()
    db = SessionLocal()
    run = SyncRun(
        run_id="sync_run_test_2",
        source="we-mp-rss-json",
        status="failed",
        imported_count=0,
        params_json='{"limit":20}',
        error_message="missing credentials",
    )
    db.add(run)
    db.commit()
    try:
        with TestClient(app) as client:
            response = client.get("/sync/runs/summary", params={"limit": 5})

        assert response.status_code == 200
        body = response.json()
        assert body["total_runs"] >= 1
        assert any(item["run_id"] == "sync_run_test_2" for item in body["latest_runs"])
    finally:
        db.query(SyncRun).filter(SyncRun.run_id == "sync_run_test_2").delete()
        db.commit()
        db.close()


def test_get_sync_run_returns_detail() -> None:
    init_db()
    db = SessionLocal()
    run = SyncRun(
        run_id="sync_run_test_3",
        source="we-mp-rss-rss:all",
        status="completed",
        imported_count=1,
        params_json='{"limit":1}',
        result_preview='[{"article_id":"demo"}]',
    )
    db.add(run)
    db.commit()
    try:
        with TestClient(app) as client:
            response = client.get("/sync/runs/sync_run_test_3")

        assert response.status_code == 200
        body = response.json()
        assert body["run_id"] == "sync_run_test_3"
        assert body["source"] == "we-mp-rss-rss:all"
    finally:
        db.query(SyncRun).filter(SyncRun.run_id == "sync_run_test_3").delete()
        db.commit()
        db.close()


def test_get_latest_sync_run_returns_latest_for_source() -> None:
    init_db()
    db = SessionLocal()
    now = utcnow()
    older = SyncRun(
        run_id="sync_run_test_4_old",
        source="we-mp-rss-json",
        status="failed",
        imported_count=0,
        params_json='{"limit":20}',
        error_message="old",
        started_at=now - timedelta(minutes=5),
    )
    newer = SyncRun(
        run_id="sync_run_test_4_new",
        source="we-mp-rss-json",
        status="completed",
        imported_count=3,
        params_json='{"limit":20}',
        result_preview='[{"article_id":"x"}]',
        started_at=now,
    )
    db.add_all([older, newer])
    db.commit()
    try:
        with TestClient(app) as client:
            response = client.get("/sync/runs/latest/we-mp-rss-json")

        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "we-mp-rss-json"
        assert body["run_id"] == "sync_run_test_4_new"
    finally:
        db.query(SyncRun).filter(SyncRun.run_id.in_(["sync_run_test_4_old", "sync_run_test_4_new"])).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()
