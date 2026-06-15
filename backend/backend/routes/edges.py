"""Analyst edge create/delete.

Crawl-discovered edges (``source='crawl'``) are derived data — written by
the runtime and never touched by these routes. Only ``source='analyst'``
edges are mutable here. SQL lives in ``db/edges.py``.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import edges as edges_db
from ..db.core import CrawlDB
from .deps import get_active_db


router = APIRouter()


class CreateEdgeBody(BaseModel):
    from_id: int
    to_id: int
    label: str | None = None
    anchor_text: str | None = None


@router.post("/api/edges")
def create_edge(
    request: Request,
    body: CreateEdgeBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    if body.from_id == body.to_id:
        return JSONResponse(
            {"error": "self_loop"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        edges_db.create_analyst_edge(
            db,
            from_id=body.from_id,
            to_id=body.to_id,
            anchor_text=body.anchor_text,
            label=body.label,
        )
    except edges_db.EdgeConflictError as exc:
        return JSONResponse(
            {"error": "edge_conflict", "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    request.app.state.project_state.graph_cache.invalidate()
    return {"ok": True}


@router.delete("/api/edges")
def delete_edge(
    request: Request,
    from_id: int,
    to_id: int,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    source = edges_db.get_edge_source(db, from_id=from_id, to_id=to_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_edge", "from_id": from_id, "to_id": to_id},
        )
    if source != "analyst":
        return JSONResponse(
            {"error": "not_analyst_edge", "source": source},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    edges_db.delete_analyst_edge(db, from_id=from_id, to_id=to_id)
    request.app.state.project_state.graph_cache.invalidate()
    return {"ok": True}


__all__ = ["router"]
