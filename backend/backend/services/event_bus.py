"""In-process publish/subscribe bus for SSE fan-out.

PLAN.md:299 — ``services/event_bus.py``: in-process pub/sub for SSE broadcast.

Channels are plain strings (``crawl.log``, ``crawl.status``, ``crawl.page``,
``crawl.alert``, ``kill_switch.engaged``, ``kill_switch.clear``,
``kill_switch.banner``, ``watchlist.changed``). Producers and consumers agree
on names — there's no enum to keep in lockstep across files.

Each subscriber owns a bounded ``asyncio.Queue(maxsize=256)``. Slow consumers
don't backpressure the producer; instead the oldest queued event is dropped
and a ``_dropped`` sentinel is delivered before the next real event so the
SSE client knows it lost messages. This is the right trade-off for a single-
analyst app: never block the crawler on a stalled HTTP client.

The bus also keeps a small (200-line) ring buffer for ``crawl.log`` so
late-subscribed SSE clients and ``GET /api/crawl/log`` see the same recent
history (PLAN.md:300). Other channels are not buffered — they're live-only.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


_QUEUE_MAX = 256
_LOG_BUFFER_MAX = 200
_LOG_CHANNEL = "crawl.log"


@dataclass
class _Subscription:
    channel: str
    queue: asyncio.Queue[dict[str, Any]]
    dropped: int = 0


@dataclass
class EventBus:
    """Per-process event bus. One instance lives on ``app.state.event_bus``."""

    _subs: dict[str, list[_Subscription]] = field(default_factory=dict)
    _log_buffer: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=_LOG_BUFFER_MAX)
    )

    def publish(self, channel: str, payload: dict[str, Any]) -> None:
        """Fan ``payload`` out to every subscriber on ``channel``.

        Mutates a copy: the payload is augmented with ``channel`` and ``ts``
        (UTC seconds, float) so the SSE serializer doesn't have to bolt them
        on later. We do this once at publish time rather than per-subscriber.
        """
        envelope: dict[str, Any] = {"channel": channel, "ts": time.time(), **payload}
        if channel == _LOG_CHANNEL:
            self._log_buffer.append(envelope)
        for sub in self._subs.get(channel, ()):
            self._deliver(sub, envelope)

    def _deliver(self, sub: _Subscription, envelope: dict[str, Any]) -> None:
        try:
            sub.queue.put_nowait(envelope)
            return
        except asyncio.QueueFull:
            pass
        # Drop oldest, account, then re-attempt. Re-attempt is best-effort —
        # if another producer races us we just lose this one and the counter
        # remains correct.
        try:
            sub.queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        sub.dropped += 1
        try:
            sub.queue.put_nowait(envelope)
        except asyncio.QueueFull:
            sub.dropped += 1

    async def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        """Yield events from ``channel`` until the consumer breaks out.

        On overflow, a ``{type: "_dropped", count: N}`` sentinel is delivered
        before the next real event. The counter resets after each emission.
        """
        sub = _Subscription(channel=channel, queue=asyncio.Queue(maxsize=_QUEUE_MAX))
        self._subs.setdefault(channel, []).append(sub)
        try:
            while True:
                event = await sub.queue.get()
                if sub.dropped > 0:
                    dropped = sub.dropped
                    sub.dropped = 0
                    yield {
                        "channel": channel,
                        "ts": time.time(),
                        "type": "_dropped",
                        "count": dropped,
                    }
                yield event
        finally:
            self._subs[channel].remove(sub)
            if not self._subs[channel]:
                del self._subs[channel]

    def log_buffer_snapshot(self, limit: int = _LOG_BUFFER_MAX) -> list[dict[str, Any]]:
        """Return the most recent ``limit`` entries from the ``crawl.log`` ring."""
        if limit <= 0:
            return []
        capped = min(limit, _LOG_BUFFER_MAX)
        return list(self._log_buffer)[-capped:]


__all__ = ["EventBus"]
