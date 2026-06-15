"""``/api/settings/{key}`` — read/write project-scoped settings.

All writes pass through ``db.settings.put_setting`` which dispatches via
``validators_for_key``. The route catches the two well-defined exceptions:

  * ``KeyError`` — unknown setting key (or templated key referencing a
    nonexistent search engine). Maps to 400 ``unknown_setting``.
  * ``ValueError`` — validator rejected the value. Maps to 400 ``bad_value``.

Reads return the raw stored string (validators normalize on the write path,
so there's no second normalization at read time).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db.core import CrawlDB
from ..db.settings import UnknownSettingError, get_setting, put_setting
from .deps import get_active_db

router = APIRouter()


class PutSettingBody(BaseModel):
    value: Any = None


@router.get("/api/settings/{key}")
def get_setting_route(key: str, db: CrawlDB = Depends(get_active_db)) -> dict[str, Any]:
    return {"key": key, "value": get_setting(db, key)}


@router.put("/api/settings/{key}")
def put_setting_route(
    key: str, body: PutSettingBody, db: CrawlDB = Depends(get_active_db)
) -> Any:
    try:
        stored = put_setting(db, key, body.value)
    except UnknownSettingError as exc:
        return JSONResponse(
            {"error": "unknown_setting", "key": key, "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except ValueError as exc:
        return JSONResponse(
            {"error": "bad_value", "key": key, "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return {"key": key, "value": stored}


__all__ = ["router"]
