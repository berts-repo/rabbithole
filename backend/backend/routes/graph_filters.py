"""Hidden sub-tab — server-side ``graph_filters`` CRUD.

PLAN.md:325. Add/remove invalidate the graph cache so the next ``/api/graph``
read rebuilds the payload without the matching nodes (or with them, on
remove).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import graph_filters as graph_filters_db
from ..db.core import CrawlDB
from .deps import get_active_db


router = APIRouter()


class CreateFilterBody(BaseModel):
    term: str


@router.get("/api/graph-filters")
def list_filters(db: CrawlDB = Depends(get_active_db)) -> dict[str, Any]:
    return {"terms": graph_filters_db.list_terms(db)}


@router.post("/api/graph-filters")
def add_filter(
    request: Request,
    body: CreateFilterBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    try:
        stored = graph_filters_db.add_term(db, body.term)
    except ValueError as exc:
        code = str(exc)
        http_status = (
            status.HTTP_409_CONFLICT
            if code == "duplicate_term"
            else status.HTTP_400_BAD_REQUEST
        )
        return JSONResponse({"error": code}, status_code=http_status)
    request.app.state.project_state.graph_cache.invalidate()
    return {"term": stored}


@router.delete("/api/graph-filters/{term:path}")
def remove_filter(
    request: Request,
    term: str,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    if not graph_filters_db.remove_term(db, term):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_term", "term": term},
        )
    request.app.state.project_state.graph_cache.invalidate()
    return {"ok": True}


__all__ = ["router"]
