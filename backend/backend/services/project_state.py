"""Active-project state: RW lock + ``ProjectState`` singleton.

The backend tracks one active project at a time. Every DB-touching route in
B5–B8 reaches the active ``CrawlDB`` through the ``get_active_db`` dependency
in ``routes/deps.py``, which holds a read lock for the lifetime of the request.
``POST /api/project/switch`` and ``POST /api/projects`` take the write lock so
they can swap the DB / mutate the registry without a request racing them.

The lock is writer-priority: once ``acquire_write`` is awaiting, new readers
queue behind it. This matters because the analyst may be poll-spamming the
header stats every few seconds while clicking "switch project" — without
writer-priority, the swap could starve for ages.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..db import crawl as crawl_db
from ..db import jobs as jobs_db
from ..db.core import CrawlDB
from ..security.paths import projects_base, validate_db_relpath
from . import registry
from .graph_cache import GraphCache


class CrawlRunningError(RuntimeError):
    """Raised by ``ProjectState.switch`` when an in-flight crawl blocks a swap.

    The route handler unpacks the attached fields into the 409 response body.
    """

    def __init__(self, crawl_id: int, seed_url: str, pages_crawled: int) -> None:
        super().__init__(f"crawl {crawl_id} is running on {seed_url}")
        self.crawl_id = crawl_id
        self.seed_url = seed_url
        self.pages_crawled = pages_crawled


class UnknownProjectError(LookupError):
    """Raised by ``ProjectState.switch`` for an id not in the registry."""


class AsyncRWLock:
    """Writer-priority readers/writers lock.

    Implemented on top of a single ``asyncio.Condition``. Readers wait if a
    writer holds the lock OR if a writer is pending — that latter clause is
    what gives writers priority and prevents starvation under a steady read
    load.
    """

    def __init__(self) -> None:
        self._cond = asyncio.Condition()
        self._readers = 0
        self._writing = False
        self._writers_waiting = 0

    async def acquire_read(self) -> None:
        async with self._cond:
            while self._writing or self._writers_waiting > 0:
                await self._cond.wait()
            self._readers += 1

    async def release_read(self) -> None:
        async with self._cond:
            self._readers -= 1
            if self._readers == 0:
                self._cond.notify_all()

    async def acquire_write(self) -> None:
        async with self._cond:
            self._writers_waiting += 1
            try:
                while self._writing or self._readers > 0:
                    await self._cond.wait()
                self._writing = True
            finally:
                self._writers_waiting -= 1

    async def release_write(self) -> None:
        async with self._cond:
            self._writing = False
            self._cond.notify_all()


@dataclass
class ProjectState:
    """Holds the active DB handle, active project id, and the RW lock.

    A single instance lives on ``app.state.project_state`` for the lifetime of
    the FastAPI process. Initial load is deferred to ``load_from_registry`` so
    tests can build a fresh ``ProjectState`` without touching disk.
    """

    rw_lock: AsyncRWLock
    graph_cache: GraphCache
    active_db: CrawlDB | None = None
    active_id: str | None = None

    @classmethod
    def new(cls) -> "ProjectState":
        return cls(rw_lock=AsyncRWLock(), graph_cache=GraphCache())

    # -- registry / disk plumbing ------------------------------------------

    @staticmethod
    def _registry_path() -> Path:
        return projects_base() / "projects.json"

    def _resolve_db_path(self, entry: dict[str, Any]) -> Path:
        """Re-canonicalize the stored path through ``validate_db_relpath``.

        Registry entries store the *user-supplied* path string; the resolved
        on-disk location is recomputed on every open so a moved ``$HOME`` or
        symlink swap is caught.
        """
        return validate_db_relpath(entry["path"])

    async def load_from_registry(self) -> None:
        """Re-attach to ``active_id`` from a previous run, if present.

        Called once at app startup. If the registry's ``active_id`` no longer
        resolves to a usable DB (path moved, mode swapped, etc.) we log and
        start with no active project; the frontend's project picker takes over.
        """
        state = registry.load(self._registry_path())
        active_id = state.get("active_id")
        if not active_id:
            return
        entry = next((p for p in state["projects"] if p["id"] == active_id), None)
        if entry is None:
            return
        try:
            db_path = self._resolve_db_path(entry)
            self.active_db = CrawlDB(db_path)
            self.active_id = active_id
        except Exception:
            # Path invalid, file missing, schema mismatch — fall through to
            # "no active project" and let the frontend re-pick.
            self.active_db = None
            self.active_id = None

    # -- mutation surface --------------------------------------------------

    async def switch(self, project_id: str, *, force: bool) -> None:
        """Swap the active DB to ``project_id``.

        Raises ``UnknownProjectError`` if the id isn't in the registry,
        ``CrawlRunningError`` if a crawl is in flight on the current project
        and ``force`` is False. With ``force=True`` any in-flight crawl's
        linked ``kind='crawl'`` job is cancelled (the kill-signal broadcast is
        B5's responsibility; the DB-level transition is correct as-is). After
        the schema reset crawl work-status lives on the ``jobs`` row, so the
        in-flight check reads ``crawl.find_active`` rather than a dropped
        ``crawls.status`` column.
        """
        await self.rw_lock.acquire_write()
        try:
            state = registry.load(self._registry_path())
            entry = next(
                (p for p in state["projects"] if p["id"] == project_id), None
            )
            if entry is None:
                raise UnknownProjectError(project_id)

            if self.active_db is not None:
                active = crawl_db.find_active(self.active_db)
                if active is not None:
                    if not force:
                        raise CrawlRunningError(
                            crawl_id=int(active["id"]),
                            seed_url=str(active["seed_url"]),
                            pages_crawled=int(active["pages_crawled"]),
                        )
                    jobs_db.cancel_active_for(
                        self.active_db,
                        payload_key="crawl_id",
                        value=int(active["id"]),
                    )

            new_path = validate_db_relpath(entry["path"])
            new_db = CrawlDB(new_path)
            old_db = self.active_db
            self.active_db = new_db
            self.active_id = project_id
            # Fresh project = fresh cache. The previous project's payload
            # would be stale on the next read anyway (PLAN.md:311).
            self.graph_cache.invalidate()
            state["active_id"] = project_id
            registry.save(self._registry_path(), state)
            if old_db is not None:
                old_db.close()
        finally:
            await self.rw_lock.release_write()

    async def detach(self) -> None:
        """Close + clear the active DB (used by DELETE on the active project)."""
        await self.rw_lock.acquire_write()
        try:
            if self.active_db is not None:
                self.active_db.close()
            self.active_db = None
            self.active_id = None
            self.graph_cache.invalidate()
        finally:
            await self.rw_lock.release_write()

    async def close(self) -> None:
        """Process-exit hook. Drops the lock entirely."""
        if self.active_db is not None:
            self.active_db.close()
            self.active_db = None
            self.active_id = None


__all__ = [
    "AsyncRWLock",
    "ProjectState",
    "CrawlRunningError",
    "UnknownProjectError",
]
