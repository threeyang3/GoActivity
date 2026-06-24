from sqlalchemy.orm import Session

from app.models import SyncLog


class SyncLogService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_logs(self, limit: int = 20, target: str | None = None) -> list[SyncLog]:
        query = self.db.query(SyncLog)
        if target:
            query = query.filter(SyncLog.target == target)
        return query.order_by(SyncLog.created_at.desc()).limit(limit).all()

    def summary(self, limit: int = 500, failure_limit: int = 5) -> dict:
        logs = self.db.query(SyncLog).order_by(SyncLog.created_at.desc()).limit(limit).all()
        grouped: dict[str, dict] = {}
        for log in logs:
            target_summary = grouped.setdefault(
                log.target,
                {
                    "target": log.target,
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                    "latest_created_at": log.created_at.isoformat(),
                    "latest_target_id": log.target_id,
                },
            )
            target_summary["total"] += 1
            if log.return_code == 0:
                target_summary["success"] += 1
            else:
                target_summary["failed"] += 1

        latest_failures = [
            {
                "target": log.target,
                "target_id": log.target_id,
                "return_code": log.return_code,
                "stderr_preview": log.stderr[:300],
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
            if log.return_code != 0
        ][:failure_limit]

        return {
            "total_logs": len(logs),
            "latest_sync_at": logs[0].created_at.isoformat() if logs else None,
            "targets": list(grouped.values()),
            "latest_failures": latest_failures,
        }
