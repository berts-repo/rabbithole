"""Crawl-intake HTTP surface, backed by the unified ``jobs`` table.

    POST   /api/crawl/queue               enqueue one or many URLs

This is the crawl-intake endpoint only. Listing crawl jobs, editing/cancelling/
retrying them, and the live SSE stream are owned by the unified ``GET /api/jobs``
surface (``routes/jobs.py``) and surfaced in the bottom-pane Activity tab — the
old per-queue ``GET/PATCH/DELETE/retry/events`` handlers here were retired in the
schema-reset Phase 6 dead-code sweep.

An enqueued "queue row" is a ``jobs`` row with ``kind='crawl'``; its crawl config
lives in ``payload`` (url, mode, source, stay_on_domain, collection_id,
max_depth, priority). Collection *names* are resolved to ids at intake.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..db import collections as collections_db
from ..db import crawl as crawl_db
from ..db import jobs as jobs_db
from ..db import resources as resources_db
from ..db import settings as settings_db
from ..db.core import CrawlDB
from ..security.net import EgressError
from ..services.crawl_queue_runner import CrawlQueueRunner
from ..services.event_bus import EventBus
from .deps import get_active_db


router = APIRouter()


# Intake provenance values (payload metadata only — no DB CHECK any more).
VALID_SOURCES: tuple[str, ...] = (
    "manual", "bulk", "bookmark", "collection", "bottom_pane",
    "search", "graph_menu", "right_pane", "schedule",
)
DEFAULT_MAX_DEPTH = 3


# --- bodies -----------------------------------------------------------------


class EnqueueBody(BaseModel):
    """Either ``url`` (singular) or ``urls`` (list). Other fields apply to
    every URL in the batch."""

    url: str | None = None
    urls: list[str] | None = None
    mode: str
    source: str
    stay_on_domain: bool = False
    max_depth: int | None = Field(default=None, ge=0, le=20)
    collection_id: int | None = None
    collection_name_pending: str | None = None
    priority: int = 0
    use_default_max_depth: bool = False


# --- helpers ----------------------------------------------------------------


def _event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus  # type: ignore[no-any-return]


def _queue_runner(request: Request) -> CrawlQueueRunner:
    return request.app.state.crawl_queue_runner  # type: ignore[no-any-return]


def _publish_change(bus: EventBus, job_id: int, status_value: str) -> None:
    bus.publish(
        "jobs.changed",
        {"job_id": job_id, "kind": "crawl", "status": status_value},
    )


def _bad_field(message: str) -> JSONResponse:
    return JSONResponse(
        {"error": "bad_field", "message": message},
        status_code=status.HTTP_400_BAD_REQUEST,
    )


def _active_crawl_job_for_url(db: CrawlDB, url: str) -> dict[str, Any] | None:
    """The non-terminal crawl job for ``url``, if any (dedupe guard)."""
    for job in jobs_db.list_jobs(db, kind="crawl", limit=1000):
        if job["status"] in jobs_db.ACTIVE_STATUSES:
            payload = job.get("payload") or {}
            if payload.get("url") == url:
                return job
    return None


def _resolve_collection(
    db: CrawlDB, collection_id: int | None, name_pending: str | None
) -> int | None:
    if collection_id is not None:
        return collection_id
    if name_pending:
        return collections_db.find_or_create_by_name(db, name_pending)
    return None


# --- POST /api/crawl/queue --------------------------------------------------


@router.post("/api/crawl/queue")
async def post_queue(
    request: Request,
    body: EnqueueBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    """Enqueue one URL (``url``) or many (``urls``) as pending crawl jobs.

    Per-row result: ``inserted`` (bool), ``job_id`` (int or null), ``state``
    (the resource's current lifecycle state, or ``unknown``), and ``reason``
    (``ok`` / ``duplicate_active`` / ``duplicate_in_batch`` / ``bad_url``).
    Duplicates within a single paste are deduped silently.
    """
    if body.url is None and not body.urls:
        return _bad_field("must provide 'url' or 'urls'")
    if body.url is not None and body.urls:
        return _bad_field("provide 'url' OR 'urls', not both")
    if body.mode not in crawl_db.VALID_MODES:
        return _bad_field(f"mode must be one of {list(crawl_db.VALID_MODES)}")
    if body.source not in VALID_SOURCES:
        return _bad_field(f"source must be one of {list(VALID_SOURCES)}")

    raw_urls: list[str] = (
        [body.url] if body.url is not None else list(body.urls or [])
    )
    max_depth = DEFAULT_MAX_DEPTH if body.use_default_max_depth else body.max_depth
    collection_id = _resolve_collection(
        db, body.collection_id, body.collection_name_pending
    )

    bus = _event_bus(request)
    response_rows: list[dict[str, Any]] = []
    seen_in_batch: set[str] = set()

    for raw in raw_urls:
        try:
            url = settings_db.validate_intake_url(db, raw)
        except EgressError as exc:
            response_rows.append(
                {"url": raw, "inserted": False, "reason": "bad_url",
                 "message": str(exc), "state": "unknown"}
            )
            continue

        known = resources_db.lookup_by_urls(db, [url]).get(url)
        state = known["state"] if known else "unknown"

        if url in seen_in_batch:
            response_rows.append(
                {"url": url, "inserted": False, "reason": "duplicate_in_batch",
                 "state": state}
            )
            continue
        seen_in_batch.add(url)

        if _active_crawl_job_for_url(db, url) is not None:
            response_rows.append(
                {"url": url, "inserted": False, "reason": "duplicate_active",
                 "state": state}
            )
            continue

        job_id = jobs_db.create_job(
            db,
            kind="crawl",
            target_type="url",
            target_id=known["id"] if known else 0,
            status="pending",
            payload={
                "url": url,
                "mode": body.mode,
                "source": body.source,
                "stay_on_domain": body.stay_on_domain,
                "collection_id": collection_id,
                "max_depth": max_depth,
                "priority": body.priority,
            },
        )
        _publish_change(bus, job_id, "pending")
        response_rows.append(
            {"url": url, "inserted": True, "job_id": job_id, "reason": "ok",
             "state": state}
        )

    # Nudge the runner — a fresh job may unblock dispatch before the tick.
    _queue_runner(request).try_advance()
    return {"results": response_rows}


__all__ = ["router"]
