"""Graph payload + exports.

Endpoints:

    GET /api/graph                    full graph JSON (PLAN.md:307)
    GET /api/export/gexf              GEXF 1.3 download (PLAN.md:309)
    GET /api/export/nodes-csv         nodes CSV download (PLAN.md:310)

All three read through ``ProjectState.graph_cache`` (15 s TTL with single-
flight, PLAN.md:311) so a frontend that polls ``/api/graph`` every 15 s and
then triggers an export immediately after only pays for one NX rebuild.

The payload build is sync + CPU-bound; we punt it to ``asyncio.to_thread``
so a 5 000-node Louvain compute doesn't stall SSE streams on the event
loop.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from ..db import collections as collections_db
from ..db.core import CrawlDB
from ..db.graph import build_payload
from ..export.csv import payload_to_nodes_csv
from ..export.gexf import payload_to_gexf
from .deps import get_active_db


router = APIRouter()


async def _payload(request: Request, db: CrawlDB) -> dict[str, Any]:
    """Cached graph payload for this request.

    Bind ``db`` into the builder so the worker thread doesn't need to
    re-resolve the active project — the read lock held by
    ``get_active_db`` is already in scope here.
    """
    cache = request.app.state.project_state.graph_cache

    async def _build() -> dict[str, Any]:
        return await asyncio.to_thread(build_payload, db)

    return await cache.get_or_build(_build)


@router.get("/api/graph")
async def get_graph(
    request: Request,
    collection_id: int | None = None,
    db: CrawlDB = Depends(get_active_db),
) -> dict[str, Any]:
    payload = await _payload(request, db)
    if collection_id is None:
        return payload
    members = collections_db.member_ids(db, collection_id)
    if members is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "unknown_collection", "collection_id": collection_id},
        )
    return collections_db.filter_payload_to_members(payload, members)


@router.get("/api/export/gexf")
async def export_gexf(
    request: Request, db: CrawlDB = Depends(get_active_db)
) -> Response:
    payload = await _payload(request, db)
    body = payload_to_gexf(payload)
    return Response(
        content=body,
        media_type="application/gexf+xml",
        headers={"Content-Disposition": 'attachment; filename="graph.gexf"'},
    )


@router.get("/api/export/nodes-csv")
async def export_nodes_csv(
    request: Request, db: CrawlDB = Depends(get_active_db)
) -> Response:
    payload = await _payload(request, db)
    body = payload_to_nodes_csv(payload).encode("utf-8")
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="nodes.csv"'},
    )


__all__ = ["router"]
