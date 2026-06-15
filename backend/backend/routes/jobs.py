"""Unified work/activity HTTP surface — the ``jobs`` table.

Backs the bottom-pane Activity tab: one list of every kind of work (crawls,
scheduled fires, analyses, monitor probes, live-crawl, batch) under one status
vocabulary, plus per-job control actions and a live SSE stream.

    GET    /api/jobs                  list (filters: kind/status/target_type/since/limit)
    GET    /api/jobs/:id              single job
    POST   /api/jobs/:id/cancel       cancel a pending/running/paused job
    POST   /api/jobs/:id/retry        re-enqueue a terminal job as fresh pending
    POST   /api/jobs/:id/pause        pending → paused (won't be claimed)
    POST   /api/jobs/:id/resume       paused → pending
    SSE    /api/jobs/stream           live updates (channel ``jobs.changed``)

Crawl jobs that are actively running are cancelled through the crawl queue
runner (which stops the in-flight runner); the runner writes the terminal
status. Other kinds just transition the row.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
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
from ..services.sse import sse_stream
from .deps import get_active_db


router = APIRouter()

# Batch intake reuses the crawl-queue intake vocabulary (provenance + default
# depth) so a batch's spawned children are indistinguishable from a direct
# enqueue. Kept in sync with routes/crawl_queue.py.
DEFAULT_MAX_DEPTH = 3


# --- batch intake bodies ----------------------------------------------------


class StageBatchBody(BaseModel):
    """Stage a batch: a URL list plus the shared crawl config every child
    will inherit on Run. No crawl jobs are created until the batch runs."""

    urls: list[str]
    mode: str
    source: str = "bulk"
    stay_on_domain: bool = False
    max_depth: int | None = Field(default=None, ge=0, le=20)
    collection_id: int | None = None
    collection_name_pending: str | None = None
    priority: int = 0
    use_default_max_depth: bool = False


def _event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus  # type: ignore[no-any-return]


def _queue_runner(request: Request) -> CrawlQueueRunner:
    return request.app.state.crawl_queue_runner  # type: ignore[no-any-return]


def _publish(bus: EventBus, job: dict[str, Any]) -> None:
    bus.publish(
        "jobs.changed",
        {"job_id": job["id"], "kind": job["kind"], "status": job["status"]},
    )


def _not_found(job_id: int) -> JSONResponse:
    return JSONResponse(
        {"error": "not_found", "job_id": job_id},
        status_code=status.HTTP_404_NOT_FOUND,
    )


def _bad_field(message: str) -> JSONResponse:
    return JSONResponse(
        {"error": "bad_field", "message": message},
        status_code=status.HTTP_400_BAD_REQUEST,
    )


def _conflict(error: str, job_id: int, message: str) -> JSONResponse:
    return JSONResponse(
        {"error": error, "job_id": job_id, "message": message},
        status_code=status.HTTP_409_CONFLICT,
    )


@router.get("/api/jobs")
def list_jobs(
    kind: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    target_type: str | None = None,
    since: str | None = None,
    limit: int = 200,
    db: CrawlDB = Depends(get_active_db),
) -> dict[str, Any]:
    return {
        "jobs": jobs_db.list_jobs(
            db,
            kind=kind,
            status=status_filter,
            target_type=target_type,
            since=since,
            limit=limit,
        ),
        "counts": jobs_db.counts_by_status(db),
    }


@router.get("/api/jobs/stream")
async def jobs_stream(request: Request) -> StreamingResponse:
    """SSE stream for the ``jobs.changed`` channel (Activity tab live view).

    Declared before the ``{job_id}`` matcher so the literal ``stream`` path
    isn't first parsed as an int id.
    """
    bus = _event_bus(request)
    return StreamingResponse(
        sse_stream(bus, ["jobs.changed"]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/jobs/batch")
def stage_batch(
    request: Request, body: StageBatchBody, db: CrawlDB = Depends(get_active_db)
) -> Any:
    """Stage a batch intake as one ``pending`` ``kind='batch'`` job.

    Validates + de-dupes the pasted URL list now (so the stored batch only
    holds crawlable onion URLs) and stores the shared crawl config in
    ``payload``. **No crawl children are created** — that happens on
    ``POST /api/jobs/:id/run``; ``DELETE``/cancel discards the batch.

    Declared before the ``{job_id}`` matcher so the literal ``batch`` path
    isn't first parsed as an int id.
    """
    if body.mode not in crawl_db.VALID_MODES:
        return _bad_field(f"mode must be one of {list(crawl_db.VALID_MODES)}")

    clean: list[str] = []
    seen: set[str] = set()
    rejected: list[dict[str, Any]] = []
    for raw in body.urls:
        try:
            url = settings_db.validate_intake_url(db, raw)
        except EgressError as exc:
            rejected.append({"url": raw, "reason": "bad_url", "message": str(exc)})
            continue
        if url in seen:
            continue
        seen.add(url)
        clean.append(url)

    if not clean:
        return _bad_field("no valid onion URLs in batch")

    collection_id = body.collection_id
    if collection_id is None and body.collection_name_pending:
        collection_id = collections_db.find_or_create_by_name(
            db, body.collection_name_pending
        )
    max_depth = (
        DEFAULT_MAX_DEPTH if body.use_default_max_depth else body.max_depth
    )

    # A batch has no single resource target; anchor it on the collection when
    # one is chosen, else a placeholder url/0.
    target_type = "collection" if collection_id is not None else "url"
    target_id = collection_id if collection_id is not None else 0

    batch_id = jobs_db.create_job(
        db,
        kind="batch",
        target_type=target_type,
        target_id=target_id,
        status="pending",
        payload={
            "urls": clean,
            "count": len(clean),
            "mode": body.mode,
            "source": body.source,
            "stay_on_domain": body.stay_on_domain,
            "collection_id": collection_id,
            "max_depth": max_depth,
            "priority": body.priority,
        },
    )
    batch = jobs_db.get_job(db, batch_id)
    _publish(_event_bus(request), batch)
    return {"job": batch, "staged": len(clean), "rejected": rejected}


@router.get("/api/jobs/{job_id}")
def get_job(job_id: int, db: CrawlDB = Depends(get_active_db)) -> Any:
    job = jobs_db.get_job(db, job_id)
    if job is None:
        return _not_found(job_id)
    return {"job": job}


@router.post("/api/jobs/{job_id}/cancel")
def cancel_job(
    request: Request, job_id: int, db: CrawlDB = Depends(get_active_db)
) -> Any:
    job = jobs_db.get_job(db, job_id)
    if job is None:
        return _not_found(job_id)
    if job["status"] in jobs_db.TERMINAL_STATUSES:
        return JSONResponse(
            {"error": "not_cancellable", "job_id": job_id,
             "message": "job already terminal"},
            status_code=status.HTTP_409_CONFLICT,
        )
    # A running crawl is stopped through the runner, which writes the terminal
    # status itself; everything else transitions directly.
    if job["kind"] == "crawl" and job["status"] == "running":
        if _queue_runner(request).request_cancel(job_id):
            return {"ok": True, "job_id": job_id, "cancelling": True}
    jobs_db.set_status(db, job_id, "cancelled")
    updated = jobs_db.get_job(db, job_id)
    _publish(_event_bus(request), updated)
    return {"ok": True, "job_id": job_id, "status": "cancelled"}


@router.post("/api/jobs/{job_id}/retry")
def retry_job(
    request: Request, job_id: int, db: CrawlDB = Depends(get_active_db)
) -> Any:
    job = jobs_db.get_job(db, job_id)
    if job is None:
        return _not_found(job_id)
    if job["status"] not in jobs_db.TERMINAL_STATUSES:
        return JSONResponse(
            {"error": "not_retryable", "job_id": job_id,
             "message": "job is not in a terminal state"},
            status_code=status.HTTP_409_CONFLICT,
        )
    payload = dict(job.get("payload") or {})
    payload.pop("crawl_id", None)  # a fresh run gets its own detail row
    new_id = jobs_db.create_job(
        db,
        kind=job["kind"],
        target_type=job["target_type"],
        target_id=job["target_id"],
        status="pending",
        payload=payload,
    )
    new = jobs_db.get_job(db, new_id)
    _publish(_event_bus(request), new)
    if job["kind"] == "crawl":
        _queue_runner(request).try_advance()
    return {"job": new}


@router.post("/api/jobs/{job_id}/pause")
def pause_job(
    request: Request, job_id: int, db: CrawlDB = Depends(get_active_db)
) -> Any:
    job = jobs_db.get_job(db, job_id)
    if job is None:
        return _not_found(job_id)
    if job["status"] != "pending":
        return JSONResponse(
            {"error": "not_pausable", "job_id": job_id,
             "message": "only pending jobs can be paused"},
            status_code=status.HTTP_409_CONFLICT,
        )
    jobs_db.set_status(db, job_id, "paused")
    updated = jobs_db.get_job(db, job_id)
    _publish(_event_bus(request), updated)
    return {"job": updated}


@router.post("/api/jobs/{job_id}/resume")
def resume_job(
    request: Request, job_id: int, db: CrawlDB = Depends(get_active_db)
) -> Any:
    job = jobs_db.get_job(db, job_id)
    if job is None:
        return _not_found(job_id)
    if job["status"] != "paused":
        return JSONResponse(
            {"error": "not_resumable", "job_id": job_id,
             "message": "only paused jobs can be resumed"},
            status_code=status.HTTP_409_CONFLICT,
        )
    jobs_db.set_status(db, job_id, "pending")
    updated = jobs_db.get_job(db, job_id)
    _publish(_event_bus(request), updated)
    if job["kind"] == "crawl":
        _queue_runner(request).try_advance()
    return {"job": updated}


@router.post("/api/jobs/{job_id}/run")
def run_batch(
    request: Request, job_id: int, db: CrawlDB = Depends(get_active_db)
) -> Any:
    """Run a staged batch: spawn one ``kind='crawl'`` child per staged URL,
    then mark the batch ``done``.

    Batch-only; the batch must still be ``pending`` (Run is a one-shot — a
    re-run would double-spawn). URLs that already have an in-flight crawl job
    are skipped. The batch's ``result`` records the spawned child ids so the
    parent→children link is queryable. Each child inherits the batch's stored
    crawl config; the queue runner is nudged once at the end.
    """
    job = jobs_db.get_job(db, job_id)
    if job is None:
        return _not_found(job_id)
    if job["kind"] != "batch":
        return _conflict("not_runnable", job_id, "only batch jobs can be run")
    if job["status"] != "pending":
        return _conflict(
            "not_runnable", job_id, "only pending batches can be run"
        )

    payload = dict(job.get("payload") or {})
    urls: list[str] = [u for u in (payload.get("urls") or []) if isinstance(u, str)]
    config = {
        "mode": payload.get("mode"),
        "source": payload.get("source", "bulk"),
        "stay_on_domain": bool(payload.get("stay_on_domain")),
        "collection_id": payload.get("collection_id"),
        "max_depth": payload.get("max_depth"),
        "priority": payload.get("priority", 0),
    }

    active = jobs_db.active_crawl_urls(db)
    known = resources_db.lookup_by_urls(db, urls)
    bus = _event_bus(request)
    child_ids: list[int] = []
    skipped = 0
    for url in urls:
        if url in active:
            skipped += 1
            continue
        resource = known.get(url)
        child_id = jobs_db.create_job(
            db,
            kind="crawl",
            target_type="url",
            target_id=resource["id"] if resource else 0,
            status="pending",
            payload={"url": url, **config},
        )
        active.add(url)
        child_ids.append(child_id)
        _publish(bus, jobs_db.get_job(db, child_id))

    jobs_db.set_status(
        db,
        job_id,
        "done",
        result={
            "child_job_ids": child_ids,
            "spawned": len(child_ids),
            "skipped": skipped,
        },
    )
    updated = jobs_db.get_job(db, job_id)
    _publish(bus, updated)
    _queue_runner(request).try_advance()
    return {"job": updated, "spawned": len(child_ids), "skipped": skipped}


__all__ = ["router"]
