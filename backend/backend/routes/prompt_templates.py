"""Prompt-template routes (item 7, decision D3).

CRUD over project-local analyzer prompts. Built-in presets are seeded at DB
init (``builtin=1``); they can be hidden/un-hidden but not edited or deleted.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..db import prompt_templates as prompts_db
from ..db.core import CrawlDB
from .deps import get_active_db


router = APIRouter()


class CreatePromptBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    analysis_type: str = Field(min_length=1, max_length=64)
    body: str = Field(min_length=1, max_length=8192)


class UpdatePromptBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    analysis_type: str | None = Field(default=None, min_length=1, max_length=64)
    body: str | None = Field(default=None, min_length=1, max_length=8192)
    hidden: bool | None = None


@router.get("/api/prompts")
def list_prompts(
    include_hidden: bool = False,
    db: CrawlDB = Depends(get_active_db),
) -> dict[str, Any]:
    return {"prompts": prompts_db.list_templates(db, include_hidden=include_hidden)}


@router.get("/api/prompts/{template_id}")
def get_prompt(
    template_id: int,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    row = prompts_db.get(db, template_id)
    if row is None:
        return JSONResponse(
            {"error": "unknown_prompt", "id": template_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return row


@router.post("/api/prompts")
def create_prompt(
    body: CreatePromptBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    new_id = prompts_db.create(
        db, name=body.name, analysis_type=body.analysis_type, body=body.body
    )
    return {"id": new_id}


@router.post("/api/prompts/{template_id}/clone")
def clone_prompt(
    template_id: int,
    body: CreatePromptBody | None = None,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    src = prompts_db.get(db, template_id)
    if src is None:
        return JSONResponse(
            {"error": "unknown_prompt", "id": template_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    name = body.name if body is not None else f"{src['name']} (copy)"
    new_id = prompts_db.clone(db, template_id, name=name)
    return {"id": new_id}


@router.patch("/api/prompts/{template_id}")
def update_prompt(
    template_id: int,
    body: UpdatePromptBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    existing = prompts_db.get(db, template_id)
    if existing is None:
        return JSONResponse(
            {"error": "unknown_prompt", "id": template_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    # Visibility is the only mutation allowed on builtins.
    if body.hidden is not None:
        prompts_db.set_hidden(db, template_id, body.hidden)
    text_change = any(
        v is not None for v in (body.name, body.analysis_type, body.body)
    )
    if text_change:
        if existing["builtin"]:
            return JSONResponse(
                {"error": "builtin_readonly", "id": template_id,
                 "hint": "built-in presets can be hidden but not edited"},
                status_code=status.HTTP_409_CONFLICT,
            )
        prompts_db.update(
            db,
            template_id,
            name=body.name,
            analysis_type=body.analysis_type,
            body=body.body,
        )
    return prompts_db.get(db, template_id)


@router.delete("/api/prompts/{template_id}")
def delete_prompt(
    template_id: int,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    existing = prompts_db.get(db, template_id)
    if existing is None:
        return JSONResponse(
            {"error": "unknown_prompt", "id": template_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if existing["builtin"]:
        return JSONResponse(
            {"error": "builtin_undeletable", "id": template_id,
             "hint": "hide built-in presets instead of deleting"},
            status_code=status.HTTP_409_CONFLICT,
        )
    prompts_db.delete(db, template_id)
    return {"deleted": template_id}


__all__ = ["router"]
