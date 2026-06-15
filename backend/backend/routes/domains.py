"""Domain profile + alias rename.

PLAN.md:324. Alias rename invalidates the graph cache (labels in the graph
payload derive from alias when set).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import domains as domains_db
from ..db import findings as findings_db
from ..db.core import CrawlDB
from .deps import get_active_db


router = APIRouter()


class RenameAliasBody(BaseModel):
    alias: str | None = None


@router.get("/api/domains")
def list_domains(
    db: CrawlDB = Depends(get_active_db),
) -> dict[str, Any]:
    return {"domains": domains_db.list_domains(db)}


@router.get("/api/domains/{host}")
def get_domain(
    host: str, db: CrawlDB = Depends(get_active_db)
) -> Any:
    profile = domains_db.get_profile(db, host)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_host", "host": host},
        )
    return profile


@router.get("/api/domains/{host}/pages")
def list_domain_pages(
    host: str, db: CrawlDB = Depends(get_active_db)
) -> Any:
    if domains_db.get_profile(db, host) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_host", "host": host},
        )
    return {"pages": domains_db.list_pages(db, host)}


@router.get("/api/domains/{host}/entities")
def list_domain_entities(
    host: str, db: CrawlDB = Depends(get_active_db)
) -> Any:
    if domains_db.get_profile(db, host) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_host", "host": host},
        )
    return {"entities": findings_db.list_for_domain(db, host)}


@router.get("/api/domains/{host}/snapshots")
def list_domain_snapshots(
    host: str, db: CrawlDB = Depends(get_active_db)
) -> Any:
    """Distinct crawl dates available as snapshot-comparison boundaries."""
    if domains_db.get_profile(db, host) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_host", "host": host},
        )
    return {"dates": domains_db.list_snapshot_dates(db, host)}


@router.get("/api/domains/{host}/compare")
def compare_domain_snapshots(
    host: str,
    a: str,
    b: str,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    """Per-page added/removed/drifted/identical between two as-of dates."""
    if domains_db.get_profile(db, host) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_host", "host": host},
        )
    return domains_db.compare_snapshots(db, host, a, b)


@router.patch("/api/domains/{host}")
def patch_domain(
    request: Request,
    host: str,
    body: RenameAliasBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    try:
        result = domains_db.rename_alias(db, host, body.alias)
    except ValueError as exc:
        code = str(exc)
        http_status = (
            status.HTTP_409_CONFLICT
            if code == "duplicate_alias"
            else status.HTTP_400_BAD_REQUEST
        )
        return JSONResponse({"error": code}, status_code=http_status)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_host", "host": host},
        )
    request.app.state.project_state.graph_cache.invalidate()
    return result


__all__ = ["router"]
