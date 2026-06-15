"""Phase B4 — RW lock semantics around the project-state.

These tests exercise the lock directly rather than through HTTP so we can
deterministically interleave operations. The HTTP tests in
``test_b4_projects.py`` already prove the dependency chain works end-to-end.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend.db.core import CrawlDB
from backend.services import registry
from backend.services.project_state import AsyncRWLock, ProjectState


# ---------------------------------------------------------------------------
# AsyncRWLock primitive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_readers_can_hold_concurrently():
    lock = AsyncRWLock()
    await lock.acquire_read()
    await lock.acquire_read()
    # Two readers held simultaneously — no deadlock, no blocking.
    await lock.release_read()
    await lock.release_read()


@pytest.mark.asyncio
async def test_writer_waits_for_readers():
    lock = AsyncRWLock()
    await lock.acquire_read()
    writer_done = asyncio.Event()

    async def writer():
        await lock.acquire_write()
        writer_done.set()
        await lock.release_write()

    task = asyncio.create_task(writer())
    await asyncio.sleep(0.05)
    assert not writer_done.is_set(), "writer must wait while a reader holds the lock"

    await lock.release_read()
    await asyncio.wait_for(writer_done.wait(), timeout=1.0)
    await task


@pytest.mark.asyncio
async def test_reader_waits_for_writer_priority():
    """Once a writer is pending, new readers queue behind it (writer-priority)."""
    lock = AsyncRWLock()
    await lock.acquire_read()  # current reader

    writer_started = asyncio.Event()
    reader_started = asyncio.Event()

    async def writer():
        await lock.acquire_write()
        writer_started.set()
        # Give the second reader a chance to race past us.
        await asyncio.sleep(0.05)
        await lock.release_write()

    async def second_reader():
        await lock.acquire_read()
        reader_started.set()
        await lock.release_read()

    w_task = asyncio.create_task(writer())
    await asyncio.sleep(0.02)  # let writer enter the waiting state
    r_task = asyncio.create_task(second_reader())
    await asyncio.sleep(0.02)

    assert not writer_started.is_set()
    assert not reader_started.is_set()

    # Drop the current reader → writer wakes first.
    await lock.release_read()
    await asyncio.wait_for(writer_started.wait(), timeout=1.0)
    # Reader must STILL be blocked until the writer releases.
    assert not reader_started.is_set()
    await asyncio.wait_for(r_task, timeout=1.0)
    await w_task


# ---------------------------------------------------------------------------
# ProjectState switch + write-lock guard
# ---------------------------------------------------------------------------


def _seed_two_projects(projects_dir: Path) -> tuple[str, str]:
    projects_dir.mkdir(parents=True, exist_ok=True)
    a_path = projects_dir / "a" / "case.db"
    b_path = projects_dir / "b" / "case.db"
    for p in (a_path, b_path):
        p.parent.mkdir(parents=True, exist_ok=True)
        CrawlDB(p).close()
    state = {
        "projects": [
            {"id": "a" * 32, "name": "Project-A", "path": "a/case.db"},
            {"id": "b" * 32, "name": "Project-B", "path": "b/case.db"},
        ],
        "active_id": None,
    }
    registry.save(projects_dir / "projects.json", state)
    return "a" * 32, "b" * 32


@pytest.mark.asyncio
async def test_switch_swaps_active_db(projects_dir):
    a_id, b_id = _seed_two_projects(projects_dir)
    ps = ProjectState.new()
    await ps.switch(a_id, force=False)
    assert ps.active_id == a_id
    first_handle = ps.active_db

    await ps.switch(b_id, force=False)
    assert ps.active_id == b_id
    assert ps.active_db is not first_handle


@pytest.mark.asyncio
async def test_in_flight_reader_blocks_switch(projects_dir):
    """A long-lived read lock holder blocks the switch's write lock acquisition."""
    a_id, b_id = _seed_two_projects(projects_dir)
    ps = ProjectState.new()
    await ps.switch(a_id, force=False)

    await ps.rw_lock.acquire_read()
    switched = asyncio.Event()

    async def do_switch():
        await ps.switch(b_id, force=False)
        switched.set()

    task = asyncio.create_task(do_switch())
    await asyncio.sleep(0.05)
    assert not switched.is_set(), "switch must wait for the in-flight reader"

    await ps.rw_lock.release_read()
    await asyncio.wait_for(switched.wait(), timeout=1.0)
    await task
    assert ps.active_id == b_id


@pytest.mark.asyncio
async def test_reader_after_switch_sees_new_db(projects_dir):
    a_id, b_id = _seed_two_projects(projects_dir)
    ps = ProjectState.new()
    await ps.switch(a_id, force=False)
    a_path = ps.active_db.path

    await ps.switch(b_id, force=False)
    await ps.rw_lock.acquire_read()
    try:
        assert ps.active_db.path != a_path
        assert ps.active_db.path.name == "case.db"
        assert ps.active_db.path.parent.name == "b"
    finally:
        await ps.rw_lock.release_read()


@pytest.mark.asyncio
async def test_load_from_registry_attaches_active(projects_dir):
    a_id, _ = _seed_two_projects(projects_dir)
    # Mark project A active on disk.
    reg = registry.load(projects_dir / "projects.json")
    reg["active_id"] = a_id
    registry.save(projects_dir / "projects.json", reg)

    ps = ProjectState.new()
    await ps.load_from_registry()
    assert ps.active_id == a_id
    assert ps.active_db is not None
    await ps.close()


@pytest.mark.asyncio
async def test_detach_clears_active(projects_dir):
    a_id, _ = _seed_two_projects(projects_dir)
    ps = ProjectState.new()
    await ps.switch(a_id, force=False)
    await ps.detach()
    assert ps.active_db is None
    assert ps.active_id is None
