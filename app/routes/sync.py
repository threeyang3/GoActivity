"""同步相关路由：文章同步、日志、运行记录。"""

import requests
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.exceptions import SyncError
from app.routes.helpers import sync_run_to_out
from app.schemas import (
    SyncFailureSummary,
    SyncLogOut,
    SyncResponse,
    SyncRunOut,
    SyncRunSummaryResponse,
    SyncSummaryResponse,
    SyncTargetSummary,
    WebhookResponse,
)
from app.services.article_service import ArticleService
from app.services.sync_log_service import SyncLogService
from app.services.sync_run_service import SyncRunService

router = APIRouter(tags=["sync"])


@router.post("/sync/we-mp-rss/articles", response_model=SyncResponse)
def sync_we_mp_rss_articles(limit: int = 20, offset: int = 0, include_no_content: bool = False, db: Session = Depends(get_db)) -> SyncResponse:
    run = SyncRunService(db).start_run("we-mp-rss-json", {"limit": limit, "offset": offset, "include_no_content": include_no_content})
    try:
        results = ArticleService(db).sync_from_we_mp_rss_articles(limit=limit, offset=offset, include_no_content=include_no_content)
        SyncRunService(db).finish_success(run, imported_count=len(results), results=results)
    except (RuntimeError, SyncError) as exc:
        SyncRunService(db).finish_failure(run, str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except requests.RequestException as exc:
        SyncRunService(db).finish_failure(run, f"Failed to fetch articles from we-mp-rss: {exc}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch articles from we-mp-rss: {exc}") from exc
    return SyncResponse(source="we-mp-rss-json", imported=len(results), results=[WebhookResponse(**item) for item in results])


@router.post("/sync/we-mp-rss/rss/{feed_id}", response_model=SyncResponse)
def sync_we_mp_rss_rss(feed_id: str, limit: int = 20, offset: int = 0, db: Session = Depends(get_db)) -> SyncResponse:
    run = SyncRunService(db).start_run(f"we-mp-rss-rss:{feed_id}", {"limit": limit, "offset": offset, "feed_id": feed_id})
    try:
        results = ArticleService(db).sync_from_we_mp_rss_rss(feed_id=feed_id, limit=limit, offset=offset)
        SyncRunService(db).finish_success(run, imported_count=len(results), results=results)
    except (RuntimeError, SyncError) as exc:
        SyncRunService(db).finish_failure(run, str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except requests.RequestException as exc:
        SyncRunService(db).finish_failure(run, f"Failed to fetch RSS from we-mp-rss: {exc}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch RSS from we-mp-rss: {exc}") from exc
    return SyncResponse(source=f"we-mp-rss-rss:{feed_id}", imported=len(results), results=[WebhookResponse(**item) for item in results])


@router.get("/sync/logs", response_model=list[SyncLogOut])
def list_sync_logs(limit: int = 20, target: str | None = None, db: Session = Depends(get_db)) -> list[SyncLogOut]:
    logs = SyncLogService(db).list_logs(limit=limit, target=target)
    return [
        SyncLogOut(
            id=log.id,
            run_id=log.run_id or "",
            target=log.target,
            target_id=log.target_id,
            command=log.command,
            return_code=log.return_code,
            stdout_preview=log.stdout[:300],
            stderr_preview=log.stderr[:300],
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]


@router.get("/sync/summary", response_model=SyncSummaryResponse)
def sync_summary(failure_limit: int = 5, db: Session = Depends(get_db)) -> SyncSummaryResponse:
    summary = SyncLogService(db).summary(failure_limit=failure_limit)
    return SyncSummaryResponse(
        total_logs=summary["total_logs"],
        latest_sync_at=summary["latest_sync_at"],
        targets=[SyncTargetSummary(**target) for target in summary["targets"]],
        latest_failures=[SyncFailureSummary(**failure) for failure in summary["latest_failures"]],
    )


@router.get("/sync/runs", response_model=list[SyncRunOut])
def list_sync_runs(limit: int = 20, source: str | None = None, db: Session = Depends(get_db)) -> list[SyncRunOut]:
    runs = SyncRunService(db).list_runs(limit=limit, source=source)
    return [sync_run_to_out(run) for run in runs]


@router.get("/sync/runs/summary", response_model=SyncRunSummaryResponse)
def sync_runs_summary(limit: int = 10, db: Session = Depends(get_db)) -> SyncRunSummaryResponse:
    summary = SyncRunService(db).summary(limit=limit)
    return SyncRunSummaryResponse(
        total_runs=summary["total_runs"],
        latest_run_at=summary["latest_run_at"],
        latest_runs=[sync_run_to_out(run) for run in summary["latest_runs"]],
    )


@router.get("/sync/runs/latest/{source}", response_model=SyncRunOut)
def get_latest_sync_run(source: str, db: Session = Depends(get_db)) -> SyncRunOut:
    run = SyncRunService(db).latest_run(source)
    if not run:
        raise HTTPException(status_code=404, detail="No sync run found for source")
    return sync_run_to_out(run)


@router.get("/sync/runs/{run_id}", response_model=SyncRunOut)
def get_sync_run(run_id: str, db: Session = Depends(get_db)) -> SyncRunOut:
    run = SyncRunService(db).get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Sync run not found")
    return sync_run_to_out(run)
