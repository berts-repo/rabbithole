"""Auto-analysis rule routes (item 7, decision D4).

CRUD over the typed ``auto_analysis_rules`` table — the single home for
auto-analysis. Phase 1 stores both trigger kinds and wires the
``collection_add`` trigger; the ``crawl`` trigger migrates onto these rows in
Phase 3.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..db import auto_rules as rules_db
from ..db.core import CrawlDB
from ..prompts import PROMPTS
from .deps import get_active_db


router = APIRouter()

_TRIGGER_KINDS = {"crawl", "collection_add"}


class CreateRuleBody(BaseModel):
    trigger_kind: str = Field(min_length=1, max_length=32)
    analysis_type: str = Field(min_length=1, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    prompt_id: int | None = Field(default=None, gt=0)
    target_filter: dict[str, Any] | None = None
    enabled: bool = True


class UpdateRuleBody(BaseModel):
    analysis_type: str | None = Field(default=None, min_length=1, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    prompt_id: int | None = Field(default=None, gt=0)
    target_filter: dict[str, Any] | None = None
    enabled: bool | None = None


def _validate(trigger_kind: str, analysis_type: str) -> JSONResponse | None:
    if trigger_kind not in _TRIGGER_KINDS:
        return JSONResponse(
            {"error": "unknown_trigger", "trigger_kind": trigger_kind},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if analysis_type not in PROMPTS:
        return JSONResponse(
            {"error": "unknown_type", "analysis_type": analysis_type},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return None


@router.get("/api/auto-analysis-rules")
def list_rules(
    trigger_kind: str | None = None,
    db: CrawlDB = Depends(get_active_db),
) -> dict[str, Any]:
    return {"rules": rules_db.list_rules(db, trigger_kind=trigger_kind)}


@router.post("/api/auto-analysis-rules")
def create_rule(
    body: CreateRuleBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    err = _validate(body.trigger_kind, body.analysis_type)
    if err is not None:
        return err
    try:
        new_id = rules_db.create(
            db,
            trigger_kind=body.trigger_kind,
            analysis_type=body.analysis_type,
            model=body.model,
            prompt_id=body.prompt_id,
            target_filter=body.target_filter,
            enabled=body.enabled,
        )
    except ValueError as exc:
        return JSONResponse(
            {"error": "create_failed", "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return {"id": new_id}


@router.patch("/api/auto-analysis-rules/{rule_id}")
def update_rule(
    rule_id: int,
    body: UpdateRuleBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    if rules_db.get(db, rule_id) is None:
        return JSONResponse(
            {"error": "unknown_rule", "id": rule_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if body.analysis_type is not None and body.analysis_type not in PROMPTS:
        return JSONResponse(
            {"error": "unknown_type", "analysis_type": body.analysis_type},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    rules_db.update(
        db,
        rule_id,
        analysis_type=body.analysis_type,
        model=body.model,
        prompt_id=body.prompt_id,
        target_filter=body.target_filter,
        enabled=body.enabled,
    )
    return rules_db.get(db, rule_id)


@router.delete("/api/auto-analysis-rules/{rule_id}")
def delete_rule(
    rule_id: int,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    if not rules_db.delete(db, rule_id):
        return JSONResponse(
            {"error": "unknown_rule", "id": rule_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return {"deleted": rule_id}


__all__ = ["router"]
