"""``/api/retention`` — job-history retention status + manual run.

Retention deletes terminal job-tracking rows (``done``/``failed``/``cancelled``)
finished more than ``retention.jobs_days`` days ago. The window lives in the
``settings`` table; this route reports how many rows are currently eligible and
runs the purge on demand. Automatic enforcement also happens at backend startup
(``main.py`` lifespan).

Scope is deliberately narrow: only work-tracking bookkeeping is pruned. Page
snapshots, analyses, and every other investigation artefact are never touched —
deleting those would erase the page version-history / diff record, so retention
stays off that data by design.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..db import jobs as jobs_db
from ..db.core import CrawlDB
from ..db.settings import get_setting
from .deps import get_active_db

router = APIRouter()


def _jobs_days(db: CrawlDB) -> int:
    """Read ``retention.jobs_days`` as an int; 0 (off) when unset or unparseable."""
    raw = get_setting(db, "retention.jobs_days")
    try:
        return int(raw) if raw is not None else 0
    except ValueError:
        return 0


@router.get("/api/retention/status")
def retention_status(db: CrawlDB = Depends(get_active_db)) -> dict[str, Any]:
    days = _jobs_days(db)
    return {
        "jobs_days": days,
        "eligible_jobs": jobs_db.count_prunable_terminal_jobs(
            db, older_than_days=days
        ),
    }


@router.post("/api/retention/run")
def retention_run(db: CrawlDB = Depends(get_active_db)) -> dict[str, Any]:
    days = _jobs_days(db)
    deleted = jobs_db.prune_terminal_jobs(db, older_than_days=days)
    return {"jobs_days": days, "deleted_jobs": deleted}


__all__ = ["router"]
