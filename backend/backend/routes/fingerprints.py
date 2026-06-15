"""Header fingerprint cluster routes.

PLAN.md:321. Read-only — no graph-cache invalidation.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse, Response

from ..db import fingerprints as fingerprints_db
from ..db.core import CrawlDB
from .deps import get_active_db


router = APIRouter()


@router.get("/api/fingerprints")
def list_clusters(
    min_sites: int = 2, db: CrawlDB = Depends(get_active_db)
) -> Any:
    try:
        clusters = fingerprints_db.list_clusters(db, min_sites=min_sites)
    except ValueError as exc:
        return JSONResponse(
            {"error": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST
        )
    return {"clusters": clusters}


@router.get("/api/fingerprints/members")
def list_cluster_members(
    key: str | None = None,
    value: str | None = None,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    if key is None or value is None:
        return JSONResponse(
            {"error": "missing_key_value"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        members = fingerprints_db.list_cluster_members(
            db, key=key, value=value
        )
    except ValueError as exc:
        return JSONResponse(
            {"error": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST
        )
    return {"members": members}


@router.get("/api/fingerprints/export.csv")
def export_clusters_csv(
    min_sites: int = 2, db: CrawlDB = Depends(get_active_db)
) -> Any:
    try:
        body = fingerprints_db.export_clusters_csv(db, min_sites=min_sites)
    except ValueError as exc:
        return JSONResponse(
            {"error": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST
        )
    return Response(
        body,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="fingerprints.csv"'
        },
    )


__all__ = ["router"]
