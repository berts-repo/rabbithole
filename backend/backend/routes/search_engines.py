"""Search-engine registry CRUD.

PLAN.md:346. Engines are project-scoped (each project has its own list,
preseeded on create). URL validation matches the v3 onion regex used by
the rest of the egress layer (``security/net.py::ONION_URL_RE``) — the
allowed shape is ``http(s)://<56-char-base32>.onion[/...]``. The optional
``{q}`` placeholder lives in the path/query and slips past the regex
because the path component allows arbitrary characters.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..db import search_engines as search_engines_db
from ..db.core import CrawlDB
from ..security.net import EgressError, validate_network_url
from .deps import get_active_db


router = APIRouter()


class CreateEngineBody(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    url: str = Field(min_length=1, max_length=512)


@router.get("/api/search-engines")
def list_engines(
    db: CrawlDB = Depends(get_active_db),
) -> dict[str, Any]:
    return {"engines": search_engines_db.list_engines(db)}


@router.post("/api/search-engines")
def create_engine(
    body: CreateEngineBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    label = body.label.strip()
    if not label:
        return JSONResponse(
            {"error": "bad_label"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        network, url = validate_network_url(body.url)
    except EgressError as exc:
        return JSONResponse(
            {"error": "bad_url", "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        engine_id = search_engines_db.create_engine(
            db, label=label, url=url, network=network
        )
    except Exception as exc:  # noqa: BLE001
        # UNIQUE(url) violation surfaces here.
        return JSONResponse(
            {"error": "duplicate_url", "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return {"id": engine_id, "label": label, "url": url, "network": network}


@router.patch("/api/search-engines/{engine_id}")
def update_engine(
    engine_id: int,
    body: CreateEngineBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    label = body.label.strip()
    if not label:
        return JSONResponse(
            {"error": "bad_label"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        network, url = validate_network_url(body.url)
    except EgressError as exc:
        return JSONResponse(
            {"error": "bad_url", "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        updated = search_engines_db.update_engine(
            db, engine_id, label=label, url=url, network=network
        )
    except Exception as exc:  # noqa: BLE001
        # UNIQUE(url) violation surfaces here.
        return JSONResponse(
            {"error": "duplicate_url", "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not updated:
        return JSONResponse(
            {"error": "unknown_engine", "id": engine_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return {"id": engine_id, "label": label, "url": url, "network": network}


@router.delete("/api/search-engines/{engine_id}")
def delete_engine(
    engine_id: int,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    deleted = search_engines_db.delete_engine(db, engine_id)
    if not deleted:
        return JSONResponse(
            {"error": "unknown_engine", "id": engine_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return {"ok": True}


__all__ = ["router"]
