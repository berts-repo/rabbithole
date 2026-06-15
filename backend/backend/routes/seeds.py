"""Seed bookmark CRUD.

PLAN.md:293 — ``GET/POST /api/seeds``, ``DELETE /api/seeds/:url``. URL is
the table's PK (``db/core.py:147``), so we accept it as a query parameter
on DELETE rather than route-encoding it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import crawl as crawl_db
from ..db import settings as settings_db
from ..db.core import CrawlDB
from ..security.net import EgressError
from .deps import get_active_db


router = APIRouter()


class CreateSeedBody(BaseModel):
    url: str
    label: str | None = None


class PatchSeedBody(BaseModel):
    label: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@router.get("/api/seeds")
def list_seeds(db: CrawlDB = Depends(get_active_db)) -> dict[str, Any]:
    return {"seeds": crawl_db.list_seeds(db)}


@router.post("/api/seeds")
def add_seed(
    body: CreateSeedBody, db: CrawlDB = Depends(get_active_db)
) -> Any:
    try:
        url = settings_db.validate_intake_url(db, body.url)
    except EgressError as exc:
        return JSONResponse(
            {"error": "bad_url", "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    added = crawl_db.add_seed(db, url=url, label=body.label, when=_now_iso())
    return {"ok": True, "url": url, "added": added}


@router.delete("/api/seeds")
def delete_seed(
    url: str, db: CrawlDB = Depends(get_active_db)
) -> dict[str, Any]:
    removed = crawl_db.remove_seed(db, url)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_seed", "url": url},
        )
    return {"ok": True}


@router.patch("/api/seeds")
def patch_seed(
    body: PatchSeedBody,
    url: str,
    db: CrawlDB = Depends(get_active_db),
) -> dict[str, Any]:
    updated = crawl_db.update_seed_label(db, url=url, label=body.label)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_seed", "url": url},
        )
    return {"ok": True, "url": url, "label": body.label}


__all__ = ["router"]
