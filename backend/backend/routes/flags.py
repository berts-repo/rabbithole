"""Investigation flag CRUD.

PLAN.md:316. Routes mutate ``flags`` and invalidate the graph cache because
``flag_status`` is part of the ``/api/graph`` node payload (joined in
``db/graph.py``).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import flags as flags_db
from ..db.core import CrawlDB
from .deps import get_active_db


router = APIRouter()


class CreateFlagBody(BaseModel):
    node_id: int
    status: str | None = None
    priority: int | None = None
    note: str | None = None


class UpdateFlagBody(BaseModel):
    status: str | None = None
    priority: int | None = None
    note: str | None = None


def _value_error_response(exc: ValueError) -> JSONResponse:
    code = str(exc)
    if code == "unknown_node":
        return JSONResponse(
            {"error": code},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return JSONResponse(
        {"error": code},
        status_code=status.HTTP_400_BAD_REQUEST,
    )


@router.get("/api/flags")
def list_flags(db: CrawlDB = Depends(get_active_db)) -> dict[str, Any]:
    return {"flags": flags_db.list_flags(db)}


@router.post("/api/flags")
def create_flag(
    request: Request,
    body: CreateFlagBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    kwargs: dict[str, Any] = {}
    if body.status is not None:
        kwargs["status"] = body.status
    if body.priority is not None:
        kwargs["priority"] = body.priority
    if body.note is not None:
        kwargs["note"] = body.note
    try:
        flag_id = flags_db.create_flag(db, body.node_id, **kwargs)
    except ValueError as exc:
        return _value_error_response(exc)
    request.app.state.project_state.graph_cache.invalidate()
    row = flags_db.get_flag(db, flag_id)
    return row


@router.patch("/api/flags/{flag_id}")
def patch_flag(
    request: Request,
    flag_id: int,
    body: UpdateFlagBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    try:
        updated = flags_db.update_flag(
            db,
            flag_id,
            status=body.status,
            priority=body.priority,
            note=body.note,
        )
    except ValueError as exc:
        return _value_error_response(exc)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_flag", "id": flag_id},
        )
    request.app.state.project_state.graph_cache.invalidate()
    return updated


@router.delete("/api/flags/{flag_id}")
def delete_flag(
    request: Request,
    flag_id: int,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    if not flags_db.delete_flag(db, flag_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_flag", "id": flag_id},
        )
    request.app.state.project_state.graph_cache.invalidate()
    return {"ok": True}


@router.delete("/api/nodes/{node_id}/flags")
def delete_node_flags(
    request: Request,
    node_id: int,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    """Clear every flag for a node. Idempotent — returns ``cleared: 0``
    when there were no flags to delete, never 404. The right-click
    "Remove Flag" UI calls this without first checking; treating the
    no-op as success avoids a race when two surfaces toggle the same
    node concurrently.
    """
    deleted = flags_db.delete_flags_for_node(db, node_id)
    if deleted:
        request.app.state.project_state.graph_cache.invalidate()
    return {"ok": True, "cleared": deleted}


__all__ = ["router"]
