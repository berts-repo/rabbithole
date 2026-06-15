"""Tor status + kill-switch control-plane SSE.

Endpoints:

    GET    /api/tor/status              latest kill-switch snapshot
    POST   /api/tor/probe               force one synchronous probe
    GET    /api/kill_switch/events      SSE stream of FSM transitions

The kill-switch SSE stream is *dedicated* to ``kill_switch.*`` events. The
data-plane multiplex on ``/api/crawl/events`` (see ``routes/crawl.py``)
does not carry these channels — if it did, the frontend's
``sse.pauseAll()`` would close the only stream capable of delivering
``kill_switch.clear`` the moment the switch tripped, leaving the
operator unable to recover. Two streams, two purposes, no shared fate.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..services.event_bus import EventBus
from ..services.sse import sse_stream


router = APIRouter()


def _event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus  # type: ignore[no-any-return]


@router.get("/api/tor/status")
def tor_status(request: Request) -> dict[str, Any]:
    """Return the latest Tor reachability snapshot from the kill switch.

    The kill switch probes every 5 s in the background (PLAN.md:291); this
    route just hands back the cached result so we don't open extra Tor
    circuits on every UI poll.
    """
    return request.app.state.kill_switch.snapshot()


@router.post("/api/tor/probe")
async def tor_probe(request: Request) -> dict[str, Any]:
    """Force a Tor probe right now and return the resulting snapshot.

    Companion to ``GET /api/tor/status``: that route reads cached state,
    this route triggers a fresh probe. The Retry button in the kill-switch
    modal calls this so a recovered Tor connection clears the modal within
    one round trip instead of waiting up to one full probe interval for the
    background loop to publish ``kill_switch.clear``.
    """
    return await request.app.state.kill_switch.probe_now()


@router.get("/api/kill_switch/events")
async def kill_switch_events(request: Request) -> StreamingResponse:
    """SSE stream of kill-switch FSM transitions.

    Carries ``kill_switch.engaged``, ``kill_switch.banner``, and
    ``kill_switch.clear``. The frontend opens this with a plain
    EventSource (bypassing ``sse.svelte.ts``) so the stream survives a
    data-plane pause — without that, a tripped switch would silence its
    own recovery signal.
    """
    bus = _event_bus(request)
    return StreamingResponse(
        sse_stream(
            bus,
            ["kill_switch.engaged", "kill_switch.banner", "kill_switch.clear"],
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = ["router"]
