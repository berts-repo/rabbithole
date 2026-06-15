"""FastAPI dependency that yields the active project's ``CrawlDB``.

The dependency acquires the read lock on ``app.state.project_state.rw_lock``
for the lifetime of the request and releases it on exit (success or error).
Routes that need the active DB declare:

    db: CrawlDB = Depends(get_active_db)

If no project is active, the dependency raises 409 ``no_active_project``
before the handler runs. The frontend treats that response as "open the
project picker modal."
"""
from __future__ import annotations

from typing import AsyncIterator

from fastapi import HTTPException, Request, status

from ..db.core import CrawlDB
from ..services.project_state import ProjectState


async def get_active_db(request: Request) -> AsyncIterator[CrawlDB]:
    state: ProjectState = request.app.state.project_state
    await state.rw_lock.acquire_read()
    try:
        if state.active_db is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "no_active_project"},
            )
        yield state.active_db
    finally:
        await state.rw_lock.release_read()


__all__ = ["get_active_db"]
