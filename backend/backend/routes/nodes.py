"""Per-node CRUD + analyst toggles.

PLAN.md:295 — resource detail, known-resource create, reviewed toggle,
analysis_excluded toggle, ``PATCH /api/nodes/:id/opened``. Identity/state
writes route through ``db/resources.py`` and page-level toggles through
``db/pages.py`` so the schema invariants live in one place. ``node_id`` in
these paths is a ``resources.id``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import pages as pages_db
from ..db import resources as resources_db
from ..db import settings as settings_db
from ..db.core import CrawlDB
from ..db.settings import get_setting
from ..security.net import EgressError
from ..security.paths import (
    PathError,
    discover_browser_path,
    launch_browser,
    validate_browser_path,
)
from .deps import get_active_db


router = APIRouter()


class CreateNodeBody(BaseModel):
    url: str


class CreateNodesBody(BaseModel):
    urls: list[str]


class LookupBody(BaseModel):
    urls: list[str]


class ReviewedBody(BaseModel):
    reviewed: bool


class AnalysisExcludedBody(BaseModel):
    excluded: bool


LOOKUP_MAX = 500


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_resource(db: CrawlDB, node_id: int) -> None:
    """404 if no ``resources`` row backs ``node_id`` (toggles ensure a page)."""
    if resources_db.get_resource(db, node_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_node", "id": node_id},
        )


@router.get("/api/nodes/{node_id}")
def get_node(
    node_id: int, db: CrawlDB = Depends(get_active_db)
) -> dict[str, Any]:
    node = pages_db.get_page_detail(db, node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_node", "id": node_id},
        )
    return node


@router.post("/api/nodes")
def create_node(
    request: Request,
    body: CreateNodeBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    try:
        url = settings_db.validate_intake_url(db, body.url)
    except EgressError as exc:
        return JSONResponse(
            {"error": "bad_url", "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    host = (urlsplit(url).hostname or "").lower()
    node_id = resources_db.upsert_resource(db, url, host, state="known")
    # A new resource is a new node in the /api/graph payload — bust the
    # cached build or the next poll keeps returning the stale graph and the
    # node never appears on the canvas (it's only counted via /api/stats,
    # which reads the DB directly). Mirrors the patch/delete node routes.
    request.app.state.project_state.graph_cache.invalidate()
    return {"id": node_id, "url": url}


@router.post("/api/nodes/batch")
def create_nodes(
    request: Request,
    body: CreateNodesBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    """Materialize many URLs as uncrawled (``known``) nodes in one call.

    Backs the Search tab's "Add all to Graph" — pinning a full result page
    one POST at a time would be 50–200 round-trips. Each URL is validated
    independently (a bad one doesn't sink the batch) and upserted; the graph
    cache is busted once at the end (mirrors ``create_node``). Returns the
    created/existing ``{id, url}`` per valid URL plus the rejects so the
    client can pin exactly the ids that landed.
    """
    if len(body.urls) > LOOKUP_MAX:
        return JSONResponse(
            {"error": "too_many_urls", "max": LOOKUP_MAX},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    nodes: list[dict[str, Any]] = []
    invalid: list[dict[str, str]] = []
    for raw in body.urls:
        try:
            url = settings_db.validate_intake_url(db, raw)
        except EgressError as exc:
            invalid.append({"url": raw, "message": str(exc)})
            continue
        host = (urlsplit(url).hostname or "").lower()
        node_id = resources_db.upsert_resource(db, url, host, state="known")
        nodes.append({"id": node_id, "url": url})
    if nodes:
        request.app.state.project_state.graph_cache.invalidate()
    return {"nodes": nodes, "invalid": invalid}


@router.post("/api/nodes/lookup")
def lookup_nodes(
    body: LookupBody, db: CrawlDB = Depends(get_active_db)
) -> Any:
    """Batch URL → state map for the bulk-import list (F3).

    Each input URL gets one entry in ``results`` keyed by the *original*
    input string (untrimmed) so the frontend can correlate without
    re-deriving the canonical form. State is the canonical resource state
    (``unknown`` / ``known`` / ``crawled`` / ``dead``) or ``invalid`` for a
    URL that fails egress validation.
    """
    if len(body.urls) > LOOKUP_MAX:
        return JSONResponse(
            {"error": "too_many_urls", "max": LOOKUP_MAX},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Two-pass: validate first so a single bad URL doesn't cost the batch.
    canonical: dict[str, str] = {}
    results: dict[str, dict[str, Any]] = {}
    for raw in body.urls:
        try:
            url = settings_db.validate_intake_url(db, raw)
        except EgressError as exc:
            results[raw] = {"state": "invalid", "reason": str(exc)}
            continue
        canonical[raw] = url

    found = resources_db.lookup_by_urls(db, list(set(canonical.values())))
    for raw, url in canonical.items():
        hit = found.get(url)
        if hit is None:
            results[raw] = {"state": "unknown"}
        else:
            results[raw] = {
                "state": hit["state"],
                "id": hit["id"],
                "last_seen": hit["last_seen"],
            }
    return {"results": results}


@router.patch("/api/nodes/{node_id}/opened")
def patch_opened(
    node_id: int, db: CrawlDB = Depends(get_active_db)
) -> dict[str, Any]:
    _require_resource(db, node_id)
    pages_db.set_opened(db, node_id, _now_iso())
    return {"ok": True}


@router.post("/api/nodes/{node_id}/open")
def open_node_in_browser(
    request: Request,
    node_id: int,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    """Launch the configured browser pointed at the node's URL.

    Privacy gate: refuses if the kill switch is engaged (Tor unreachable).
    The 5 s background probe in ``services/kill_switch.py`` is the source
    of truth here — we do *not* run an inline ``probe_now()`` per click
    because (a) Tor Browser self-isolates so the cache window is not a
    leak vector and (b) the 1-3 s latency would be felt on every click.
    When the change-browser feature lands (Mullvad / Brave / Firefox),
    revisit: non-Tor browsers don't self-isolate the same way.

    Browser path: prefers the explicit ``browser.path`` setting; falls
    back to ``discover_browser_path`` (walks the canonical Tor Browser
    install hints) so a default install works without configuration.
    The launcher re-validates the path + URL at exec time regardless
    (TOCTOU close).
    """
    node = pages_db.get_page_detail(db, node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_node", "id": node_id},
        )

    if request.app.state.kill_switch.engaged.is_set():
        return JSONResponse(
            {"error": "tor_unavailable", "reason": "tripped"},
            status_code=status.HTTP_409_CONFLICT,
        )

    raw_path = get_setting(db, "browser.path")
    try:
        if raw_path:
            resolved = validate_browser_path(raw_path)
        else:
            resolved = discover_browser_path()
            if resolved is None:
                return JSONResponse(
                    {"error": "browser_unconfigured"},
                    status_code=status.HTTP_412_PRECONDITION_FAILED,
                )
    except PathError as exc:
        return JSONResponse(
            {"error": "browser_invalid", "message": str(exc)},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    try:
        launch_browser(resolved, str(node["url"]))
    except (PathError, EgressError) as exc:
        return JSONResponse(
            {"error": "launch_failed", "message": str(exc)},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    when = _now_iso()
    pages_db.set_opened(db, node_id, when)
    return {"ok": True, "browser": resolved.name, "opened_at": when}


@router.patch("/api/nodes/{node_id}/reviewed")
def patch_reviewed(
    request: Request,
    node_id: int,
    body: ReviewedBody,
    db: CrawlDB = Depends(get_active_db),
) -> dict[str, Any]:
    _require_resource(db, node_id)
    pages_db.set_reviewed(db, node_id, body.reviewed)
    # `reviewed` is part of the /api/graph payload (see db/graph.py) so
    # the next poll needs a fresh build for the F4b "Mark Reviewed"
    # context-menu toggle to relabel.
    request.app.state.project_state.graph_cache.invalidate()
    return {"ok": True}


@router.patch("/api/nodes/{node_id}/analysis_excluded")
def patch_analysis_excluded(
    request: Request,
    node_id: int,
    body: AnalysisExcludedBody,
    db: CrawlDB = Depends(get_active_db),
) -> dict[str, Any]:
    _require_resource(db, node_id)
    pages_db.set_analysis_excluded(db, node_id, body.excluded)
    request.app.state.project_state.graph_cache.invalidate()
    return {"ok": True}


__all__ = ["router"]
