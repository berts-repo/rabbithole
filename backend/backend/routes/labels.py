"""Label taxonomy CRUD + attach/detach + reorder (item 11, Phase 1).

HTTP shell over ``db/labels.py``. Two concepts share the label UI panel but
stay separate routes: labels here, page rename on
``PATCH /api/pages/{id}/alias`` (``routes/pages.py``), domain rename on
``PATCH /api/domains/{host}`` (``routes/domains.py``).

Error vocabulary (raised as ``ValueError`` in the db layer, mapped here):
``duplicate_name`` / ``builtin_rename`` / ``builtin_undeletable`` → 409;
``empty_name`` / ``name_too_long`` → 400; ``unknown_label`` /
``unknown_resource`` / ``unknown_domain`` → 404.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..db import labels as labels_db
from ..db.core import CrawlDB
from .deps import get_active_db


router = APIRouter()


# ValueError code → HTTP status. Anything unlisted is a 400.
_CONFLICT_CODES = {"duplicate_name", "builtin_rename", "builtin_undeletable"}
_NOT_FOUND_CODES = {"unknown_label", "unknown_resource", "unknown_domain"}


def _invalidate_graph(request: Request) -> None:
    """Bust the cached graph payload — it carries label ids per node, so an
    attach/detach changes what the next poll returns."""
    request.app.state.project_state.graph_cache.invalidate()


def _error_response(code: str) -> JSONResponse:
    if code in _CONFLICT_CODES:
        http_status = status.HTTP_409_CONFLICT
    elif code in _NOT_FOUND_CODES:
        http_status = status.HTTP_404_NOT_FOUND
    else:
        http_status = status.HTTP_400_BAD_REQUEST
    return JSONResponse({"error": code}, status_code=http_status)


class CreateLabelBody(BaseModel):
    name: str = Field(min_length=1, max_length=labels_db.LABEL_NAME_MAX)
    color: str | None = Field(default=None, max_length=labels_db.COLOR_MAX)
    description: str | None = Field(
        default=None, max_length=labels_db.DESCRIPTION_MAX
    )


class UpdateLabelBody(CreateLabelBody):
    hidden: bool = False


class ReorderBody(BaseModel):
    ids: list[int]


@router.get("/api/labels")
def list_labels(
    include_hidden: bool = True,
    db: CrawlDB = Depends(get_active_db),
) -> dict[str, Any]:
    return {
        "labels": labels_db.list_labels(db, include_hidden=include_hidden)
    }


@router.post("/api/labels")
def create_label(
    body: CreateLabelBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    try:
        return labels_db.create_label(
            db,
            name=body.name,
            color=body.color,
            description=body.description,
        )
    except ValueError as exc:
        return _error_response(str(exc))


# Declared before ``/api/labels/{label_id}`` so "order" is not captured as an
# int path param (it would 422).
@router.patch("/api/labels/order")
def reorder_labels(
    request: Request,
    body: ReorderBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    labels_db.reorder(db, body.ids)
    # Per-node label_ids ride in rank order; a re-rank changes the dominant
    # label color mode reads, so bust the cached payload.
    _invalidate_graph(request)
    return {"labels": labels_db.list_labels(db)}


@router.get("/api/labels/{label_id}/members")
def label_members(
    label_id: int,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    if labels_db.get_label(db, label_id) is None:
        return _error_response("unknown_label")
    return labels_db.label_members(db, label_id)


@router.patch("/api/labels/{label_id}")
def update_label(
    label_id: int,
    body: UpdateLabelBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    try:
        updated = labels_db.update_label(
            db,
            label_id,
            name=body.name,
            color=body.color,
            description=body.description,
            hidden=body.hidden,
        )
    except ValueError as exc:
        return _error_response(str(exc))
    if updated is None:
        return _error_response("unknown_label")
    return updated


@router.delete("/api/labels/{label_id}")
def delete_label(
    request: Request,
    label_id: int,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    try:
        deleted = labels_db.delete_label(db, label_id)
    except ValueError as exc:
        return _error_response(str(exc))
    if not deleted:
        return _error_response("unknown_label")
    # Cascade wiped this label's attachments from every node — bust the cache.
    _invalidate_graph(request)
    return {"ok": True}


# --- attachment ------------------------------------------------------------


@router.post("/api/labels/{label_id}/resources/{resource_id}")
def attach_resource(
    request: Request,
    label_id: int,
    resource_id: int,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    try:
        attached = labels_db.attach_resource(db, label_id, resource_id)
    except ValueError as exc:
        return _error_response(str(exc))
    if attached:
        _invalidate_graph(request)
    return {"ok": True, "attached": attached}


@router.delete("/api/labels/{label_id}/resources/{resource_id}")
def detach_resource(
    request: Request,
    label_id: int,
    resource_id: int,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    detached = labels_db.detach_resource(db, label_id, resource_id)
    if detached:
        _invalidate_graph(request)
    return {"ok": True, "detached": detached}


@router.post("/api/labels/{label_id}/domains/{host}")
def attach_domain(
    request: Request,
    label_id: int,
    host: str,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    try:
        attached = labels_db.attach_domain(db, label_id, host)
    except ValueError as exc:
        return _error_response(str(exc))
    if attached:
        _invalidate_graph(request)
    return {"ok": True, "attached": attached}


@router.delete("/api/labels/{label_id}/domains/{host}")
def detach_domain(
    request: Request,
    label_id: int,
    host: str,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    detached = labels_db.detach_domain(db, label_id, host)
    if detached:
        _invalidate_graph(request)
    return {"ok": True, "detached": detached}


__all__ = ["router"]
