"""SSE framing helpers shared by control-plane and data-plane routes.

``routes/crawl.py`` carries the data-plane multiplex (``crawl.*``) and
``routes/sse.py`` carries the kill-switch control-plane channel. Both
need the same ``data: <json>\\n\\n`` framing and the same channel
fan-in loop, so the plumbing lives here rather than being duplicated.
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from .event_bus import EventBus


def sse_format(envelope: dict) -> bytes:
    return f"data: {json.dumps(envelope, default=str)}\n\n".encode("utf-8")


async def sse_stream(
    bus: EventBus, channels: list[str], *, replay_log: bool = False
) -> AsyncIterator[bytes]:
    """Yield SSE-formatted events for one or more channels.

    For ``crawl.log`` we replay the bus's ring buffer (PLAN.md:300 — 200
    lines) so a late subscriber sees the recent past. Other channels are
    live-only.
    """
    if replay_log:
        for envelope in bus.log_buffer_snapshot():
            yield sse_format(envelope)

    queues: list[asyncio.Task] = []
    out: asyncio.Queue[dict] = asyncio.Queue(maxsize=512)

    async def _pump(channel: str) -> None:
        async for envelope in bus.subscribe(channel):
            try:
                out.put_nowait(envelope)
            except asyncio.QueueFull:
                # Drop oldest on the combined fan-in queue too.
                try:
                    out.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                out.put_nowait(envelope)

    try:
        for ch in channels:
            queues.append(asyncio.create_task(_pump(ch), name=f"sse_{ch}"))
        while True:
            envelope = await out.get()
            yield sse_format(envelope)
    finally:
        for t in queues:
            t.cancel()
        for t in queues:
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
