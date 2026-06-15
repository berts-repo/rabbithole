"""Uptime monitor CRUD.

PLAN.md:319. Monitor state isn't part of the graph payload, so these
routes don't invalidate ``graph_cache``.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import monitors as monitors_db
from ..db.core import CrawlDB
from .deps import get_active_db


router = APIRouter()


class CreateMonitorBody(BaseModel):
    url: str
    label: str | None = None
    interval_hours: float
    alert_on_change: bool | None = None
    alert_on_restore: bool | None = None
    downtime_threshold_hours: float | None = None


class UpdateMonitorBody(BaseModel):
    enabled: bool | None = None
    label: str | None = None
    interval_hours: float | None = None
    alert_on_change: bool | None = None
    alert_on_restore: bool | None = None
    downtime_threshold_hours: float | None = None


_DUPLICATE_CODES = {"duplicate_url"}


def _value_error_response(exc: ValueError) -> JSONResponse:
    code = str(exc)
    if code in _DUPLICATE_CODES:
        return JSONResponse(
            {"error": code}, status_code=status.HTTP_409_CONFLICT
        )
    return JSONResponse(
        {"error": code}, status_code=status.HTTP_400_BAD_REQUEST
    )


@router.get("/api/monitors")
def list_monitors(
    host: str | None = None,
    db: CrawlDB = Depends(get_active_db),
) -> dict[str, Any]:
    return {"monitors": monitors_db.list_monitors(db, host=host)}


@router.post("/api/monitors")
def create_monitor(
    body: CreateMonitorBody, db: CrawlDB = Depends(get_active_db)
) -> Any:
    kwargs: dict[str, Any] = {
        "url": body.url,
        "label": body.label,
        "interval_hours": body.interval_hours,
    }
    if body.alert_on_change is not None:
        kwargs["alert_on_change"] = body.alert_on_change
    if body.alert_on_restore is not None:
        kwargs["alert_on_restore"] = body.alert_on_restore
    if body.downtime_threshold_hours is not None:
        kwargs["downtime_threshold_hours"] = body.downtime_threshold_hours
    try:
        mid = monitors_db.create_monitor(db, **kwargs)
    except ValueError as exc:
        return _value_error_response(exc)
    return monitors_db.get_monitor(db, mid)


@router.patch("/api/monitors/{mid}")
def patch_monitor(
    mid: int,
    body: UpdateMonitorBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    fields = body.model_dump(exclude_unset=True)
    try:
        updated = monitors_db.update_monitor(db, mid, **fields)
    except ValueError as exc:
        return _value_error_response(exc)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_monitor", "id": mid},
        )
    return updated


@router.delete("/api/monitors/{mid}")
def delete_monitor(
    mid: int, db: CrawlDB = Depends(get_active_db)
) -> Any:
    if not monitors_db.delete_monitor(db, mid):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_monitor", "id": mid},
        )
    return {"ok": True}


__all__ = ["router"]
