"""Crawl control + SSE.

Endpoints:

    POST   /api/crawl/stop          cooperative stop of the in-flight crawl
    GET    /api/crawl/status        in-flight snapshot + DB-active row
    GET    /api/crawl/history       most recent ``N`` crawls
    GET    /api/crawl/log           SSE stream of ``crawl.log`` events
    GET    /api/crawl/events        SSE multiplex of ``crawl.*`` channels
                                    (``kill_switch.*`` lives on its own
                                    control-plane route — see
                                    ``routes/sse.py``)

Crawl intake lives on ``POST /api/crawl/queue`` (see ``routes/crawl_queue.py``);
this module owns the runtime control surface only.

Only one crawl runs per process (PLAN.md:274). The 409 ``crawl_running``
response shape matches the existing project-switch contract in
``routes/projects.py:155``.

SSE handshakes inherit ``ApiAuthMiddleware`` from the FastAPI app — no
auth bypass possible (PLAN.md:207). Live channels emit JSON envelopes that
already include ``channel`` and ``ts`` (set by ``event_bus.publish``).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..crawler.runtime import CrawlRunnerRegistry
from ..db import crawl as crawl_db
from ..db.core import CrawlDB
from ..services.event_bus import EventBus
from ..services.sse import sse_stream
from .deps import get_active_db


router = APIRouter()


class StopCrawlBody(BaseModel):
    crawl_id: int | None = None


def _registry(request: Request) -> CrawlRunnerRegistry:
    return request.app.state.crawl_runners  # type: ignore[no-any-return]


def _event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus  # type: ignore[no-any-return]


# --- POST /api/crawl/stop ---------------------------------------------------


@router.post("/api/crawl/stop")
async def stop_crawl(
    request: Request,
    body: StopCrawlBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    registry = _registry(request)
    if registry.is_running():
        await registry.stop()
        return {"ok": True, "stopped": registry.crawl_id}

    # No in-process runner. If the DB still claims one is running (process
    # crash, half-state), close it out at the DB level so the next start
    # succeeds.
    active = crawl_db.find_active(db)
    if active is None:
        # Idempotent: nothing to stop is success, not an error. The crawl
        # may have ended (kill-switch teardown, natural completion)
        # between the UI rendering the Stop button and the click landing.
        return {"ok": True, "already_stopped": True}
    crawl_db.mark_stopped(
        db,
        int(active["id"]),
        _now_iso(),
        error="reaped_from_half_state",
    )
    return {"ok": True, "reaped": int(active["id"])}


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- GET /api/crawl/status --------------------------------------------------


@router.get("/api/crawl/status")
def crawl_status(
    request: Request, db: CrawlDB = Depends(get_active_db)
) -> dict[str, Any]:
    registry = _registry(request)
    active = crawl_db.find_active(db)
    return {
        "running": registry.is_running(),
        "crawl_id": registry.crawl_id,
        "active_row": active,
    }


# --- GET /api/crawl/history -------------------------------------------------


@router.get("/api/crawl/history")
def crawl_history(
    limit: int = 50, db: CrawlDB = Depends(get_active_db)
) -> dict[str, Any]:
    return {"crawls": crawl_db.list_crawls(db, limit=limit)}


# --- SSE --------------------------------------------------------------------


@router.get("/api/crawl/log")
async def crawl_log(request: Request) -> StreamingResponse:
    bus = _event_bus(request)
    return StreamingResponse(
        sse_stream(bus, ["crawl.log"], replay_log=True),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/crawl/events")
async def crawl_events(request: Request) -> StreamingResponse:
    bus = _event_bus(request)
    # Data-plane only. ``kill_switch.*`` events live on
    # ``GET /api/kill_switch/events`` so the recovery signal cannot be
    # silenced by ``sse.pauseAll()`` on the frontend when the switch
    # trips. See ``routes/sse.py``.
    channels = ["crawl.status", "crawl.page", "crawl.alert"]
    return StreamingResponse(
        sse_stream(bus, channels),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = ["router"]
