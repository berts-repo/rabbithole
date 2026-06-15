"""Per-node analyst notes.

PLAN.md:318. Notes do not invalidate the graph cache — they are not part
of the graph payload.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import findings as findings_db
from ..db.core import CrawlDB
from .deps import get_active_db


router = APIRouter()


class CreateNoteBody(BaseModel):
    body: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@router.get("/api/nodes/{node_id}/notes")
def list_node_notes(
    node_id: int, db: CrawlDB = Depends(get_active_db)
) -> dict[str, Any]:
    return {"notes": findings_db.list_notes(db, node_id)}


@router.post("/api/nodes/{node_id}/notes")
def create_node_note(
    node_id: int,
    body: CreateNoteBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    try:
        return findings_db.create_note(db, node_id, body.body, now=_now_iso())
    except ValueError as exc:
        code = str(exc)
        http_status = (
            status.HTTP_404_NOT_FOUND
            if code == "unknown_resource"
            else status.HTTP_400_BAD_REQUEST
        )
        return JSONResponse({"error": code}, status_code=http_status)


@router.delete("/api/notes/{note_id}")
def delete_note(
    note_id: int, db: CrawlDB = Depends(get_active_db)
) -> Any:
    if not findings_db.delete_note(db, note_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_note", "id": note_id},
        )
    return {"ok": True}


__all__ = ["router"]
