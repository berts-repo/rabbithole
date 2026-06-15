"""Project registry + switch routes.

Endpoints:

    GET    /api/projects             — registry list
    POST   /api/projects             — create + register a new project
    POST   /api/project/switch       — swap the active project (with crawl guard)
    DELETE /api/projects/{id}        — remove from registry; DB file stays on disk

All registry mutations take the project-state write lock so they can't race
``GET /api/stats`` (or any other ``get_active_db`` consumer). The create path
also opens a one-shot ``CrawlDB`` instance so the schema is initialized at
file mode 0o600 from the very first byte.
"""
from __future__ import annotations

import sqlite3
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import search_engines as search_engines_db
from ..db.core import CrawlDB
from ..security.paths import (
    PathError,
    validate_db_relpath,
    validate_project_name,
    write_sensitive_file,
)
from ..services import registry
from ..services.project_state import (
    CrawlRunningError,
    ProjectState,
    UnknownProjectError,
)

router = APIRouter()


def _existing_resource_count(db_path: Path) -> int:
    """Count resources in a DB that already exists on disk, read-only.

    A new project must be fresh work — it must never silently adopt the data
    of a DB left behind by a deleted project that reused this path (delete
    keeps the file on disk; the create form auto-derives the path from the
    name, so recreating a deleted project lands on the same file). We probe
    with a read-only sqlite connection so we never run migrations or otherwise
    mutate the user's existing file just to reject it. A non-rabbithole or
    schema-less file (no ``resources`` table) counts as 0 — empty is reusable.
    """
    if not db_path.exists() or db_path.stat().st_size == 0:
        return 0
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT count(*) FROM resources").fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


class CreateProjectBody(BaseModel):
    name: str
    path: str


class SwitchProjectBody(BaseModel):
    id: str


def _state(request: Request) -> ProjectState:
    return request.app.state.project_state  # type: ignore[no-any-return]


def _normalize_name_for_compare(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


# --- GET /api/projects -----------------------------------------------------


@router.get("/api/projects")
async def list_projects(request: Request) -> dict[str, Any]:
    state = _state(request)
    await state.rw_lock.acquire_read()
    try:
        data = registry.load(ProjectState._registry_path())
        return {
            "projects": data["projects"],
            "active_id": state.active_id,
        }
    finally:
        await state.rw_lock.release_read()


# --- POST /api/projects ----------------------------------------------------


@router.post("/api/projects")
async def create_project(request: Request, body: CreateProjectBody) -> Any:
    state = _state(request)
    await state.rw_lock.acquire_write()
    try:
        try:
            name = validate_project_name(body.name)
        except PathError as exc:
            return JSONResponse(
                {"error": "bad_name", "message": str(exc)},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        try:
            db_path = validate_db_relpath(body.path)
        except PathError as exc:
            return JSONResponse(
                {"error": "bad_path", "message": str(exc)},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        reg = registry.load(ProjectState._registry_path())
        compare_name = _normalize_name_for_compare(name)
        for entry in reg["projects"]:
            if _normalize_name_for_compare(entry["name"]) == compare_name:
                return JSONResponse(
                    {"error": "duplicate_name", "name": name},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            # Two registered projects must never share a DB file, or their
            # nodes bleed across what should be isolated work.
            if entry["path"] == body.path:
                return JSONResponse(
                    {"error": "duplicate_path", "path": body.path},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        # An orphaned DB with data at this path (a deleted project's file, left
        # on disk) must not be silently adopted as "new work". Refuse and let
        # the analyst pick a fresh path — or re-register the old one knowingly.
        existing = _existing_resource_count(db_path)
        if existing > 0:
            return JSONResponse(
                {
                    "error": "path_in_use",
                    "path": body.path,
                    "resources": existing,
                    "message": (
                        f"A database with {existing} resources already exists at "
                        f"{body.path}. Choose a different path for a new project."
                    ),
                },
                status_code=status.HTTP_409_CONFLICT,
            )

        # Parent dir 0o700, DB file 0o600 (touched empty so sqlite never
        # creates it under the process umask).
        db_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        import os
        try:
            os.chmod(db_path.parent, 0o700)
        except OSError:
            pass
        if not db_path.exists():
            write_sensitive_file(db_path, b"")
        # Open once so the schema initializes; close immediately. The file
        # mode survives the open since sqlite doesn't chmod existing files.
        seed = CrawlDB(db_path)
        try:
            # Preseed dark-web search engines so the Search tab works on
            # day one. Idempotent — safe to call on every create.
            search_engines_db.seed_defaults(seed)
        finally:
            seed.close()

        new_id = uuid.uuid4().hex
        reg["projects"].append({"id": new_id, "name": name, "path": body.path})
        try:
            registry.save(ProjectState._registry_path(), reg)
        except OSError as exc:
            return JSONResponse(
                {"error": "registry_write_failed", "message": str(exc)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return {"id": new_id, "name": name, "path": body.path}
    finally:
        await state.rw_lock.release_write()


# --- POST /api/project/switch ----------------------------------------------


@router.post("/api/project/switch")
async def switch_project(
    request: Request, body: SwitchProjectBody, force: bool = False
) -> Any:
    state = _state(request)
    try:
        await state.switch(body.id, force=force)
    except UnknownProjectError:
        return JSONResponse(
            {"error": "unknown_project", "id": body.id},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    except CrawlRunningError as exc:
        return JSONResponse(
            {
                "error": "crawl_running",
                "crawl_id": exc.crawl_id,
                "seed_url": exc.seed_url,
                "pages_crawled": exc.pages_crawled,
            },
            status_code=status.HTTP_409_CONFLICT,
        )
    except (PathError, OSError) as exc:
        return JSONResponse(
            {"error": "bad_path", "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return {"ok": True, "active_id": state.active_id}


# --- DELETE /api/projects/{id} ---------------------------------------------


@router.delete("/api/projects/{project_id}")
async def delete_project(request: Request, project_id: str) -> Any:
    state = _state(request)
    await state.rw_lock.acquire_write()
    try:
        reg = registry.load(ProjectState._registry_path())
        before = len(reg["projects"])
        reg["projects"] = [p for p in reg["projects"] if p["id"] != project_id]
        if len(reg["projects"]) == before:
            return JSONResponse(
                {"error": "unknown_project", "id": project_id},
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if reg.get("active_id") == project_id:
            reg["active_id"] = None
            if state.active_db is not None:
                state.active_db.close()
            state.active_db = None
            state.active_id = None
        registry.save(ProjectState._registry_path(), reg)
        return {"ok": True}
    finally:
        await state.rw_lock.release_write()


__all__ = ["router"]
