"""Embedding worker control + progress routes.

PLAN.md:343. Mirrors the Intel sub-tab Embedding Model section UX.
The worker handle lives at ``app.state.embed_worker``.

Lifecycle controls (start / stop) are exposed in Settings → Embedding;
pause / resume in Intel. Both go through the same worker — start clears
the circuit breaker per spec line 344.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from ..db import embed as embed_db
from ..db.core import CrawlDB
from .deps import get_active_db


router = APIRouter()


def _embed_worker(request: Request) -> Any:
    return getattr(request.app.state, "embed_worker", None)


def _worker_or_503(request: Request):
    worker = _embed_worker(request)
    if worker is None:
        return None, JSONResponse(
            {"error": "worker_unavailable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return worker, None


@router.get("/api/embed/status")
def embed_status(request: Request) -> Any:
    worker, err = _worker_or_503(request)
    if err is not None:
        return err
    return worker.snapshot()


@router.post("/api/embed/start")
async def embed_start(request: Request) -> Any:
    worker, err = _worker_or_503(request)
    if err is not None:
        return err
    await worker.start()
    return worker.snapshot()


@router.post("/api/embed/stop")
async def embed_stop(request: Request) -> Any:
    worker, err = _worker_or_503(request)
    if err is not None:
        return err
    await worker.stop()
    return worker.snapshot()


@router.post("/api/embed/pause")
def embed_pause(request: Request) -> Any:
    worker, err = _worker_or_503(request)
    if err is not None:
        return err
    worker.pause()
    return worker.snapshot()


@router.post("/api/embed/resume")
def embed_resume(request: Request) -> Any:
    worker, err = _worker_or_503(request)
    if err is not None:
        return err
    worker.resume()
    return worker.snapshot()


@router.get("/api/embed/progress")
def embed_progress(
    request: Request, db: CrawlDB = Depends(get_active_db)
) -> Any:
    embedded = embed_db.count_embeddings(db)
    eligible = embed_db.count_eligible_pages(db)
    pct = (embedded / eligible * 100.0) if eligible > 0 else 100.0
    return {
        "embedded": embedded,
        "eligible": eligible,
        "queue_size": max(eligible - embedded, 0),
        "percent": round(pct, 2),
    }


@router.get("/api/embed/models")
def embed_models() -> Any:
    """Return the fastembed registry filtered to 384-dim models.

    Anything other than 384 dims doesn't fit the schema's vec0 declaration.
    Lazy import keeps onnxruntime out of cold-start unless the analyst
    actually opens Settings → Embedding → Model picker.
    """
    try:
        from fastembed import TextEmbedding
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            {"error": "fastembed_unavailable", "message": str(exc)},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    out: list[dict[str, Any]] = []
    for model in TextEmbedding.list_supported_models():
        dim = model.get("dim")
        if dim != 384:
            continue
        out.append(
            {
                "model": model.get("model"),
                "dim": dim,
                "size_in_GB": model.get("size_in_GB"),
                "description": model.get("description"),
            }
        )
    return {"models": out}


__all__ = ["router"]
