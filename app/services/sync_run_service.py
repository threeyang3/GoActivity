from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import SyncRun
from app.utils.ids import stable_id
from app.utils.jsonx import dumps_json
from app.utils.time import utcnow


class SyncRunService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def start_run(self, source: str, params: dict) -> SyncRun:
        run = SyncRun(
            run_id=stable_id("sync_run", source, utcnow().isoformat()),
            source=source,
            status="running",
            params_json=dumps_json(params),
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def finish_success(self, run: SyncRun, imported_count: int, results: list[dict]) -> SyncRun:
        run.status = "completed"
        run.imported_count = imported_count
        run.result_preview = dumps_json(results[:5])
        run.completed_at = utcnow()
        self.db.commit()
        self.db.refresh(run)
        return run

    def finish_failure(self, run: SyncRun, error_message: str) -> SyncRun:
        run.status = "failed"
        run.error_message = error_message
        run.completed_at = utcnow()
        self.db.commit()
        self.db.refresh(run)
        return run

    def list_runs(self, limit: int = 20, source: str | None = None) -> list[SyncRun]:
        query = self.db.query(SyncRun)
        if source:
            query = query.filter(SyncRun.source == source)
        return query.order_by(SyncRun.started_at.desc()).limit(limit).all()

    def get_run(self, run_id: str) -> SyncRun | None:
        return self.db.query(SyncRun).filter(SyncRun.run_id == run_id).one_or_none()

    def latest_run(self, source: str) -> SyncRun | None:
        return (
            self.db.query(SyncRun)
            .filter(SyncRun.source == source)
            .order_by(SyncRun.started_at.desc())
            .first()
        )

    def summary(self, limit: int = 10) -> dict:
        runs = self.db.query(SyncRun).order_by(SyncRun.started_at.desc()).limit(limit).all()
        return {
            "total_runs": len(runs),
            "latest_run_at": runs[0].started_at.isoformat() if runs else None,
            "latest_runs": runs[:limit],
        }
