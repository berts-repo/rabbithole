"""Collection CRUD, item membership, and exports.

PLAN.md:317. Full surface lands in B7c — F3's minimal GET/POST is folded
in below. Collection mutations do *not* invalidate the graph cache:
membership isn't part of the graph payload.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from ..db import collections as collections_db
from ..db.core import CrawlDB
from ..export.csv import payload_to_nodes_csv
from ..export.gexf import payload_to_gexf
from ..services.llm_worker import auto_enqueue_for_collection_add
from .deps import get_active_db


router = APIRouter()


class CreateCollectionBody(BaseModel):
    name: str
    description: str | None = None


class UpdateCollectionBody(BaseModel):
    name: str | None = None
    description: str | None = None


class AddItemsBody(BaseModel):
    # Batch membership add. The frontend's "Add to Collection" modal and the
    # graph "Expand to collection" popover both send a node-id array; a
    # single-node add is just a one-element list.
    node_ids: list[int] = Field(min_length=1, max_length=1000)


def _value_error_response(exc: ValueError) -> JSONResponse:
    code = str(exc)
    if code == "duplicate_name":
        return JSONResponse(
            {"error": code}, status_code=status.HTTP_409_CONFLICT
        )
    if code in {"unknown_collection", "unknown_node"}:
        return JSONResponse(
            {"error": code}, status_code=status.HTTP_404_NOT_FOUND
        )
    return JSONResponse(
        {"error": code}, status_code=status.HTTP_400_BAD_REQUEST
    )


@router.get("/api/collections")
def list_collections(
    db: CrawlDB = Depends(get_active_db),
) -> dict[str, Any]:
    return {"collections": collections_db.list_collections(db)}


@router.post("/api/collections")
def create_collection(
    body: CreateCollectionBody, db: CrawlDB = Depends(get_active_db)
) -> Any:
    try:
        collection_id = collections_db.create_collection(
            db, body.name, description=body.description
        )
    except ValueError as exc:
        return _value_error_response(exc)
    return {
        "id": collection_id,
        "name": body.name.strip(),
        "description": body.description,
    }


@router.get("/api/collections/{cid}")
def get_collection(
    cid: int, db: CrawlDB = Depends(get_active_db)
) -> Any:
    meta = collections_db.get_collection(db, cid)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_collection", "id": cid},
        )
    return {**meta, "items": collections_db.list_items(db, cid)}


@router.patch("/api/collections/{cid}")
def patch_collection(
    cid: int,
    body: UpdateCollectionBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    try:
        updated = collections_db.update_collection(
            db, cid, name=body.name, description=body.description
        )
    except ValueError as exc:
        return _value_error_response(exc)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_collection", "id": cid},
        )
    return updated


@router.delete("/api/collections/{cid}")
def delete_collection(
    cid: int, db: CrawlDB = Depends(get_active_db)
) -> Any:
    if not collections_db.delete_collection(db, cid):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_collection", "id": cid},
        )
    return {"ok": True}


@router.post("/api/collections/{cid}/items")
def add_items(
    cid: int, body: AddItemsBody, db: CrawlDB = Depends(get_active_db)
) -> Any:
    try:
        result = collections_db.add_items(db, cid, body.node_ids)
    except ValueError as exc:
        return _value_error_response(exc)
    # Collection-add auto-analysis trigger (item 7, decision D4): fire enabled
    # ``collection_add`` rules for genuinely new members only. ``added_ids``
    # carries exactly those, so re-adding an existing member never re-queues.
    added_ids = result.get("added_ids") or []
    if added_ids:
        auto_enqueue_for_collection_add(db, cid, added_ids)
    return result


@router.delete("/api/collections/{cid}/items/{node_id}")
def remove_item(
    cid: int, node_id: int, db: CrawlDB = Depends(get_active_db)
) -> Any:
    if not collections_db.remove_item(db, cid, node_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_item", "collection_id": cid, "node_id": node_id},
        )
    return {"ok": True}


@router.get("/api/nodes/{node_id}/collections")
def list_for_node(
    node_id: int, db: CrawlDB = Depends(get_active_db)
) -> dict[str, Any]:
    return {"collections": collections_db.list_for_node(db, node_id)}


@router.get("/api/collections/{cid}/export")
def export_collection(
    cid: int,
    format: str = "json",
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    if format not in {"json", "csv", "gexf"}:
        return JSONResponse(
            {"error": "bad_format", "format": format},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        payload = collections_db.build_export_payload(db, cid)
    except ValueError as exc:
        return _value_error_response(exc)

    name = payload["collection"]["name"]
    safe_stub = "".join(
        ch if ch.isalnum() or ch in "-_." else "_" for ch in name
    ) or f"collection-{cid}"

    if format == "json":
        return Response(
            json.dumps(payload),
            media_type="application/json",
            headers={
                "Content-Disposition":
                    f'attachment; filename="{safe_stub}.json"',
            },
        )
    if format == "csv":
        return Response(
            payload_to_nodes_csv(payload),
            media_type="text/csv",
            headers={
                "Content-Disposition":
                    f'attachment; filename="{safe_stub}.csv"',
            },
        )
    return Response(
        payload_to_gexf(payload),
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_stub}.gexf"',
        },
    )


__all__ = ["router"]
