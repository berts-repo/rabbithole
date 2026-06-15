"""Watchlist CRUD.

Posts/deletes publish ``watchlist.changed`` on the event bus so any
in-flight Focused crawl can rebuild its Aho-Corasick automaton without
waiting for the next start.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import watchlist as watchlist_db
from ..db.core import CrawlDB
from ..services.event_bus import EventBus
from .deps import get_active_db


router = APIRouter()


class AddTermBody(BaseModel):
    term: str


def _event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus  # type: ignore[no-any-return]


@router.get("/api/watchlist")
async def list_watchlist(
    db: CrawlDB = Depends(get_active_db),
) -> dict[str, Any]:
    return {"terms": watchlist_db.list_terms(db)}


@router.post("/api/watchlist")
async def add_watchlist(
    request: Request,
    body: AddTermBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    try:
        term_id = watchlist_db.add_term(db, body.term)
    except watchlist_db.WatchlistError as exc:
        return JSONResponse(
            {"error": "bad_term", "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    _event_bus(request).publish("watchlist.changed", {"action": "add", "id": term_id})
    return {"id": term_id, "term": body.term.strip()}


@router.patch("/api/watchlist/{term_id}")
async def update_watchlist(
    term_id: int,
    request: Request,
    body: AddTermBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    try:
        updated = watchlist_db.update_term(db, term_id, body.term)
    except watchlist_db.WatchlistError as exc:
        return JSONResponse(
            {"error": "bad_term", "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_term", "id": term_id},
        )
    _event_bus(request).publish(
        "watchlist.changed", {"action": "update", "id": term_id}
    )
    return {"id": term_id, "term": body.term.strip()}


@router.delete("/api/watchlist/{term_id}")
async def delete_watchlist(
    term_id: int, request: Request, db: CrawlDB = Depends(get_active_db)
) -> dict[str, Any]:
    if not watchlist_db.remove_term(db, term_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_term", "id": term_id},
        )
    _event_bus(request).publish(
        "watchlist.changed", {"action": "remove", "id": term_id}
    )
    return {"ok": True}


__all__ = ["router"]
