"""Entity queries — shared-across-nodes endpoint used by the cluster workspace.

PLAN.md:323. Read-only — no graph-cache invalidation.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from ..db import findings as findings_db
from ..db.core import CrawlDB
from .deps import get_active_db


router = APIRouter()


def _parse_node_ids(raw: str | None) -> list[int]:
    if not raw:
        raise ValueError("bad_node_ids")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        raise ValueError("bad_node_ids")
    try:
        return [int(p) for p in parts]
    except ValueError as exc:
        raise ValueError("bad_node_ids") from exc


@router.get("/api/entities/common")
def common_entities(
    node_ids: str | None = None,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    try:
        parsed = _parse_node_ids(node_ids)
    except ValueError:
        return JSONResponse(
            {"error": "bad_node_ids"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        rows = findings_db.list_common(db, parsed)
    except ValueError as exc:
        return JSONResponse(
            {"error": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST
        )
    return {"entities": rows}


__all__ = ["router"]
