"""15-second cache for the graph payload.

``GET /api/graph`` is the most expensive read in the app — it triggers a
NetworkX rebuild (PageRank, betweenness with k-sampling, Louvain, articulation
points, infra-cluster IDF). PLAN.md:311 lists every event that should
invalidate the cache; this class is the in-process holder those events drop
to ``0`` via :meth:`invalidate`.

One instance lives on ``ProjectState`` and is replaced whenever the active
project switches, so cached data for project A can never bleed into a read
on project B (PLAN.md:273).

Single-flight: concurrent callers awaiting a rebuild share one compute. The
slot is filled before the lock is released so the second caller sees the
cached value without re-running the builder.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable


DEFAULT_TTL_SECONDS = 15.0


class GraphCache:
    """TTL cache with explicit invalidation and single-flight rebuild."""

    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._value: Any = None
        self._expires_at: float = 0.0
        # Bumped on every invalidate(). get_or_build snapshots it before a
        # rebuild and refuses to mark the result fresh if it changed during
        # the build — see the race note there.
        self._generation: int = 0
        self._lock = asyncio.Lock()

    def invalidate(self) -> None:
        """Mark the cached value stale. Cheap; safe to call from any task."""
        self._expires_at = 0.0
        self._generation += 1

    async def get_or_build(
        self, build: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Return the cached value, rebuilding via ``build`` if stale.

        The lock serializes concurrent rebuilds so a thundering herd against
        a cold cache collapses to a single compute. After the first caller
        finishes, the others see the freshly cached value without re-running.

        Race guard: an ``invalidate()`` that lands *while* a rebuild is in
        flight (e.g. an alias rename committing mid-poll) must not be lost.
        We snapshot the generation before building; if it changed by the
        time the build finishes, the result reflects a DB state that's
        already stale, so we hand it to this caller but leave the slot
        expired — the next reader rebuilds instead of getting stale data.
        """
        if self._is_fresh():
            return self._value
        async with self._lock:
            if self._is_fresh():
                return self._value
            generation = self._generation
            value = await build()
            self._value = value
            if generation == self._generation:
                self._expires_at = time.monotonic() + self._ttl
            else:
                self._expires_at = 0.0
            return value

    def _is_fresh(self) -> bool:
        return self._value is not None and time.monotonic() < self._expires_at


__all__ = ["GraphCache", "DEFAULT_TTL_SECONDS"]
