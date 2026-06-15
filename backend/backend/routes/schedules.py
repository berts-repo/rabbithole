"""Scheduled-crawl CRUD.

URL is the table's PK (``db/core.py:269``). The crawl queue runner
(``services/crawl_queue_runner.py``) reads ``active=1`` rows on every tick
and creates a pending crawl ``job`` (``kind='crawl'``,
``payload.source='schedule'``) when ``interval_hours`` has elapsed since the
seed's last intended fire (read from schedule-sourced crawl jobs, not
``crawls.started_at`` — audit-trail item 3 in
``docs/work/active/2026-05-25-durable-crawl-queue/plan.md``).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..db import crawl as crawl_db
from ..db import settings as settings_db
from ..db.core import CrawlDB
from ..security.net import EgressError
from .deps import get_active_db


router = APIRouter()


class CreateScheduleBody(BaseModel):
    url: str
    interval_hours: float = Field(gt=0)
    mode: str
    label: str | None = None
    collection_id: int | None = None
    active: bool = True


class PatchScheduleBody(BaseModel):
    interval_hours: float | None = Field(default=None, gt=0)
    mode: str | None = None
    label: str | None = None
    collection_id: int | None = None
    active: bool | None = None


@router.get("/api/schedules")
def list_schedules(
    db: CrawlDB = Depends(get_active_db),
) -> dict[str, Any]:
    return {"schedules": crawl_db.list_schedules(db)}


@router.post("/api/schedules")
def create_schedule(
    body: CreateScheduleBody, db: CrawlDB = Depends(get_active_db)
) -> Any:
    if body.mode not in crawl_db.VALID_MODES:
        return JSONResponse(
            {"error": "bad_mode", "allowed": list(crawl_db.VALID_MODES)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        url = settings_db.validate_intake_url(db, body.url)
    except EgressError as exc:
        return JSONResponse(
            {"error": "bad_url", "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    crawl_db.upsert_schedule(
        db,
        url=url,
        label=body.label,
        interval_hours=body.interval_hours,
        mode=body.mode,
        collection_id=body.collection_id,
        active=body.active,
    )
    return {"ok": True, "url": url}


@router.patch("/api/schedules")
def patch_schedule(
    url: str,
    body: PatchScheduleBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    if body.mode is not None and body.mode not in crawl_db.VALID_MODES:
        return JSONResponse(
            {"error": "bad_mode", "allowed": list(crawl_db.VALID_MODES)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    updated = crawl_db.patch_schedule(
        db,
        url,
        label=body.label,
        interval_hours=body.interval_hours,
        mode=body.mode,
        collection_id=body.collection_id,
        active=body.active,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_schedule", "url": url},
        )
    return {"ok": True}


@router.delete("/api/schedules")
def delete_schedule(
    url: str, db: CrawlDB = Depends(get_active_db)
) -> dict[str, Any]:
    if not crawl_db.remove_schedule(db, url):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_schedule", "url": url},
        )
    return {"ok": True}


__all__ = ["router"]
