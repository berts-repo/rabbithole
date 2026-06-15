"""Page-version reads — single-snapshot fetch + on-demand two-version diff.

The schema reset made each crawl append a ``page_versions`` row rather than
overwriting the previous one (see
``docs/work/archive/2026-06-04-schema-reset/source-spec.md`` → *Page
Versioning*). ``GET /api/nodes/:id`` still returns the **current** snapshot plus
a lightweight ``history`` timeline; the endpoints here back the Phase-5
versioning UI that lets an analyst pull up an *older* snapshot and diff two
versions.

- ``GET /api/pages/versions/{version_id}`` — one full version, body included.
- ``GET /api/pages/versions/{a_id}/diff/{b_id}`` — line diff of two versions'
  normalized text (``body_text_clean`` — the same text used for FTS / embedding
  per the DDL). Computed on demand with stdlib ``difflib``; no diff is cached.

Both versions in a diff must belong to the same page — diffing across pages is
meaningless and rejected with 400.
"""
from __future__ import annotations

import difflib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import page_versions as versions_db
from ..db import pages as pages_db
from ..db.core import CrawlDB
from .deps import get_active_db


router = APIRouter()

# Hard cap on emitted diff lines so a pathologically large page can't produce an
# unbounded response. The body is text-only and crawler-capped, so this is a
# safety net, not an expected path.
MAX_DIFF_LINES = 4000


class RenameAliasBody(BaseModel):
    alias: str | None = None


@router.patch("/api/pages/{resource_id}/alias")
def patch_page_alias(
    request: Request,
    resource_id: int,
    body: RenameAliasBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    """Set or clear a page's display alias (item 11, decision D1).

    The page half of rename, on the same target-agnostic seam the frontend
    ``renameTarget()`` already routes through. Keyed by ``resource_id``.
    Invalidates the graph cache like the domain rename does, since a node may
    label as its page alias.
    """
    try:
        result = pages_db.rename_alias(db, resource_id, body.alias)
    except ValueError as exc:
        return JSONResponse(
            {"error": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST
        )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_resource", "id": resource_id},
        )
    request.app.state.project_state.graph_cache.invalidate()
    return result


def _version_summary(v: dict[str, Any]) -> dict[str, Any]:
    """The header fields a diff/picker shows, without the body text."""
    return {
        "id": v["id"],
        "page_id": v["page_id"],
        "fetched_at": v["fetched_at"],
        "http_status": v["http_status"],
        "title": v["title"],
        "content_changed": (
            bool(v["content_changed"]) if v["content_changed"] is not None else None
        ),
    }


def build_diff_lines(
    a_lines: list[str], b_lines: list[str], *, context: int = 3
) -> tuple[list[dict[str, str]], bool]:
    """Unified-style line diff of two text blocks (a = older, b = newer).

    Returns ``(lines, truncated)``. Each line is ``{op, text}`` with ``op`` one
    of ``hunk`` / ``context`` / ``add`` / ``remove``. ``add`` is present in
    ``b`` only, ``remove`` in ``a`` only. Built on ``difflib.unified_diff`` so
    context windows and hunk grouping come for free; the file-header lines are
    dropped. Truncates at :data:`MAX_DIFF_LINES`.
    """
    out: list[dict[str, str]] = []
    truncated = False
    for line in difflib.unified_diff(a_lines, b_lines, n=context, lineterm=""):
        if line.startswith("+++") or line.startswith("---"):
            continue
        if len(out) >= MAX_DIFF_LINES:
            truncated = True
            break
        if line.startswith("@@"):
            out.append({"op": "hunk", "text": line})
        elif line.startswith("+"):
            out.append({"op": "add", "text": line[1:]})
        elif line.startswith("-"):
            out.append({"op": "remove", "text": line[1:]})
        else:
            # Unified-diff context lines carry a leading space.
            out.append({"op": "context", "text": line[1:] if line[:1] == " " else line})
    return out, truncated


@router.get("/api/pages/versions/{version_id}")
def get_page_version(
    version_id: int, db: CrawlDB = Depends(get_active_db)
) -> dict[str, Any]:
    """One full page version, body text included (the snapshot picker view)."""
    version = versions_db.get_version(db, version_id)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_version", "id": version_id},
        )
    return {
        "id": version["id"],
        "page_id": version["page_id"],
        "fetched_at": version["fetched_at"],
        "http_status": version["http_status"],
        "title": version["title"],
        "content_changed": (
            bool(version["content_changed"])
            if version["content_changed"] is not None
            else None
        ),
        "body_text": version["body_text"],
        "body_text_clean": version["body_text_clean"],
    }


@router.get("/api/pages/versions/{a_id}/diff/{b_id}")
def diff_page_versions(
    a_id: int, b_id: int, db: CrawlDB = Depends(get_active_db)
) -> dict[str, Any]:
    """On-demand text diff of two versions of the same page.

    Orders the pair old→new by ``fetched_at`` (id tie-break) regardless of arg
    order, so the diff always reads forward in time. 404 if either version is
    unknown; 400 if they belong to different pages.
    """
    a = versions_db.get_version(db, a_id)
    b = versions_db.get_version(db, b_id)
    missing = a_id if a is None else b_id if b is None else None
    if missing is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_version", "id": missing},
        )
    assert a is not None and b is not None
    if a["page_id"] != b["page_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "cross_page_diff", "a_page": a["page_id"], "b_page": b["page_id"]},
        )

    # Old→new ordering so adds/removes read in chronological direction.
    older, newer = sorted((a, b), key=lambda v: (v["fetched_at"] or "", v["id"]))
    a_lines = (older["body_text_clean"] or "").splitlines()
    b_lines = (newer["body_text_clean"] or "").splitlines()
    lines, truncated = build_diff_lines(a_lines, b_lines)
    added = sum(1 for line in lines if line["op"] == "add")
    removed = sum(1 for line in lines if line["op"] == "remove")
    return {
        "a": _version_summary(older),
        "b": _version_summary(newer),
        "identical": added == 0 and removed == 0,
        "added": added,
        "removed": removed,
        "truncated": truncated,
        "lines": lines,
    }
