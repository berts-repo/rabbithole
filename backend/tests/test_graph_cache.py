"""GraphCache — TTL, explicit invalidation, and the mid-build race.

The race regression: an ``invalidate()`` that lands while a rebuild is in
flight (an alias rename committing during a graph poll) must not be lost
when the in-flight build writes its result back.
"""
from __future__ import annotations

import asyncio

from backend.services.graph_cache import GraphCache


async def test_fresh_value_is_served_without_rebuilding() -> None:
    cache = GraphCache(ttl_seconds=60.0)
    calls = {"n": 0}

    async def build() -> str:
        calls["n"] += 1
        return "payload"

    assert await cache.get_or_build(build) == "payload"
    assert await cache.get_or_build(build) == "payload"
    assert calls["n"] == 1  # second read came from the cache


async def test_invalidate_forces_the_next_read_to_rebuild() -> None:
    cache = GraphCache(ttl_seconds=60.0)
    calls = {"n": 0}

    async def build() -> str:
        calls["n"] += 1
        return f"payload-{calls['n']}"

    await cache.get_or_build(build)
    cache.invalidate()
    assert await cache.get_or_build(build) == "payload-2"
    assert calls["n"] == 2


async def test_invalidate_during_build_is_not_swallowed() -> None:
    """An invalidate mid-rebuild must leave the cache stale.

    Without the generation guard the in-flight build would write its
    (now-stale) result back as fresh, and the rename would not surface
    until the TTL expired.
    """
    cache = GraphCache(ttl_seconds=60.0)
    calls = {"n": 0}
    build_started = asyncio.Event()
    release_build = asyncio.Event()

    async def slow_build() -> str:
        calls["n"] += 1
        build_started.set()
        await release_build.wait()
        return f"payload-{calls['n']}"

    task = asyncio.create_task(cache.get_or_build(slow_build))
    await build_started.wait()
    # Rename commits + invalidates while the poll's rebuild is in flight.
    cache.invalidate()
    release_build.set()
    assert await task == "payload-1"

    # The mid-build invalidate must still count — the next read rebuilds
    # rather than serving the stale single-flight result.
    async def quick_build() -> str:
        calls["n"] += 1
        return f"payload-{calls['n']}"

    assert await cache.get_or_build(quick_build) == "payload-2"
    assert calls["n"] == 2
