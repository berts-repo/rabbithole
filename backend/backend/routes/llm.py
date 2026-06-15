"""Analysis queue + collection synthesis routes.

PLAN.md:335. Mirrors the Intel sub-tab and right-panel Analysis tab UX:

  * Worker control            — start / stop / pause / resume / status
  * Analysis CRUD             — enqueue, list, get, set priority, delete, rerun
  * Collection synthesis      — enqueue + list per collection

Worker handles ``app.state.llm_worker``. Routes only flip the worker's
state; the loop itself owns Ollama I/O.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..db import collections as collections_db
from ..db import llm as llm_db
from ..db import resources as resources_db
from ..db.core import CrawlDB
from ..db.settings import get_setting
from ..prompts import PROMPTS
from .deps import get_active_db


router = APIRouter()


_DEFAULT_MODEL = "qwen2.5:3b"


# --- request bodies --------------------------------------------------------


class CreateAnalysisBody(BaseModel):
    node_id: int = Field(gt=0)
    analysis_type: str = Field(min_length=1, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    priority: int = Field(default=0, ge=0, le=10)
    question: str | None = Field(default=None, max_length=2048)


class CreateAnalysesBatchBody(BaseModel):
    node_ids: list[int] = Field(min_length=1, max_length=1000)
    analysis_type: str = Field(min_length=1, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    priority: int = Field(default=0, ge=0, le=10)
    question: str | None = Field(default=None, max_length=2048)
    skip_existing: bool = True


class PatchAnalysisBody(BaseModel):
    priority: int | None = Field(default=None, ge=0, le=10)


class CreateCollectionAnalysisBody(BaseModel):
    analysis_type: str = Field(min_length=1, max_length=64)
    model: str | None = Field(default=None, max_length=128)


class CreateClusterAnalysisBody(BaseModel):
    # The analyst composes against a live cluster (a set of nodes). The server
    # derives the stable fingerprint from the membership so clients never have
    # to (item 7, decision D1).
    resource_ids: list[int] = Field(min_length=1, max_length=2000)
    analysis_type: str = Field(min_length=1, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    question: str | None = Field(default=None, max_length=2048)
    label: str | None = Field(default=None, max_length=256)
    prompt_id: int | None = Field(default=None, gt=0)
    priority: int = Field(default=0, ge=0, le=10)


# --- analyses CRUD ---------------------------------------------------------


@router.get("/api/analyses")
def list_analyses(
    status_filter: str | None = None,
    node_id: int | None = None,
    limit: int = 200,
    db: CrawlDB = Depends(get_active_db),
) -> dict[str, Any]:
    capped = max(1, min(int(limit), 500))
    rows = llm_db.list_queue(
        db, status=status_filter, resource_id=node_id, limit=capped
    )
    return {"analyses": rows, "counts": llm_db.queue_counts(db)}


@router.get("/api/analyzed-nodes")
def list_analyzed_nodes(
    limit: int = 200,
    db: CrawlDB = Depends(get_active_db),
) -> dict[str, Any]:
    """Nodes that have ≥1 successful completed analysis — one row per node.

    Backs the bottom-pane "Analyzed" tab. A top-level path (not under
    ``/api/analyses/...``) so it can't collide with the ``int`` path param of
    ``get_analysis``. ``analysis_types`` is split from the DB's comma string
    into a list here so the client gets a clean shape.
    """
    capped = max(1, min(int(limit), 500))
    rows = llm_db.list_analyzed_nodes(db, limit=capped)
    for r in rows:
        r["analysis_types"] = (r["analysis_types"] or "").split(",")
    return {"nodes": rows}


@router.get("/api/analyses/{analysis_id}")
def get_analysis(
    analysis_id: int,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    row = llm_db.get(db, analysis_id)
    if row is None:
        return JSONResponse(
            {"error": "unknown_analysis", "id": analysis_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return row


@router.post("/api/analyses")
def create_analysis(
    body: CreateAnalysisBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    if body.analysis_type not in PROMPTS:
        return JSONResponse(
            {
                "error": "unknown_type",
                "analysis_type": body.analysis_type,
                "allowed": sorted(PROMPTS.keys()),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    spec = PROMPTS[body.analysis_type]
    if spec.multi_page:
        return JSONResponse(
            {"error": "collection_only", "analysis_type": body.analysis_type},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if resources_db.get_resource(db, body.node_id) is None:
        return JSONResponse(
            {"error": "unknown_node", "id": body.node_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if body.analysis_type == "Q&A" and not (body.question or "").strip():
        return JSONResponse(
            {"error": "question_required"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # No more stub-vs-crawled split: every analysis enqueues ``pending``. A
    # job against a not-yet-crawled resource is claimed and dropped
    # (``no_content``) rather than parked in a ``waiting`` state.
    model = (body.model or get_setting(db, "llm.model") or _DEFAULT_MODEL).strip()

    try:
        new_id = llm_db.enqueue(
            db,
            resource_id=body.node_id,
            analysis_type=body.analysis_type,
            model=model,
            priority=body.priority,
            question=body.question,
        )
    except ValueError as exc:
        return JSONResponse(
            {"error": "enqueue_failed", "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return {"id": new_id, "status": "pending"}


@router.post("/api/analyses/batch")
def create_analyses_batch(
    body: CreateAnalysesBatchBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    """Queue one analysis type across many resources in a single call.

    Every known resource gets a ``pending`` job (the stub/waiting split is
    gone — a job against a not-yet-crawled resource is claimed and dropped).
    With ``skip_existing`` (default on), a resource that already has a
    non-terminal job of this type is skipped. Unknown ids are counted under
    ``unknown`` rather than failing the whole batch.
    """
    if body.analysis_type not in PROMPTS:
        return JSONResponse(
            {
                "error": "unknown_type",
                "analysis_type": body.analysis_type,
                "allowed": sorted(PROMPTS.keys()),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if PROMPTS[body.analysis_type].multi_page:
        return JSONResponse(
            {"error": "collection_only", "analysis_type": body.analysis_type},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if body.analysis_type == "Q&A" and not (body.question or "").strip():
        return JSONResponse(
            {"error": "question_required"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    model = (body.model or get_setting(db, "llm.model") or _DEFAULT_MODEL).strip()
    ids = list(dict.fromkeys(int(n) for n in body.node_ids))
    states = resources_db.state_by_ids(db, ids)
    skip = (
        llm_db.resources_with_active_analysis(
            db, analysis_type=body.analysis_type, resource_ids=ids
        )
        if body.skip_existing
        else set()
    )

    queued = skipped = unknown = 0
    for nid in ids:
        if nid not in states:
            unknown += 1
            continue
        if nid in skip:
            skipped += 1
            continue
        try:
            llm_db.enqueue(
                db,
                resource_id=nid,
                analysis_type=body.analysis_type,
                model=model,
                priority=body.priority,
                question=body.question,
            )
        except ValueError:
            unknown += 1
            continue
        queued += 1
    return {
        "queued": queued,
        "skipped": skipped,
        "unknown": unknown,
    }


@router.patch("/api/analyses/{analysis_id}")
def patch_analysis(
    analysis_id: int,
    body: PatchAnalysisBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    if body.priority is None:
        return JSONResponse(
            {"error": "no_changes"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not llm_db.set_priority(db, analysis_id, body.priority):
        return JSONResponse(
            {"error": "unknown_analysis", "id": analysis_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return {"ok": True, "id": analysis_id, "priority": body.priority}


@router.delete("/api/analyses/{analysis_id}")
def delete_analysis(
    analysis_id: int,
    force: bool = False,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    if force:
        ok = llm_db.cancel_running(db, analysis_id)
    else:
        ok = llm_db.cancel(db, analysis_id)
    if not ok:
        return JSONResponse(
            {"error": "unknown_analysis_or_running", "id": analysis_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return {"ok": True, "id": analysis_id}


@router.post("/api/analyses/{analysis_id}/rerun")
def rerun_analysis(
    analysis_id: int,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    if not llm_db.rerun(db, analysis_id):
        return JSONResponse(
            {"error": "unknown_or_not_done", "id": analysis_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return {"ok": True, "id": analysis_id, "status": "pending"}


# --- worker control --------------------------------------------------------


def _llm_worker(request: Request) -> Any:
    return getattr(request.app.state, "llm_worker", None)


@router.get("/api/llm/status")
def llm_status(request: Request) -> Any:
    worker = _llm_worker(request)
    if worker is None:
        return JSONResponse(
            {"error": "worker_unavailable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return worker.snapshot()


@router.post("/api/llm/start")
async def llm_start(request: Request) -> Any:
    worker = _llm_worker(request)
    if worker is None:
        return JSONResponse(
            {"error": "worker_unavailable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    await worker.start()
    return worker.snapshot()


@router.post("/api/llm/stop")
async def llm_stop(request: Request) -> Any:
    worker = _llm_worker(request)
    if worker is None:
        return JSONResponse(
            {"error": "worker_unavailable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    await worker.stop()
    return worker.snapshot()


@router.post("/api/llm/pause")
def llm_pause(request: Request) -> Any:
    worker = _llm_worker(request)
    if worker is None:
        return JSONResponse(
            {"error": "worker_unavailable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    worker.pause()
    return worker.snapshot()


@router.post("/api/llm/resume")
def llm_resume(request: Request) -> Any:
    worker = _llm_worker(request)
    if worker is None:
        return JSONResponse(
            {"error": "worker_unavailable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    worker.resume()
    return worker.snapshot()


# --- collection synthesis --------------------------------------------------


@router.get("/api/collections/{collection_id}/analyses")
def list_collection_analyses(
    collection_id: int,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    if collections_db.get_collection(db, collection_id) is None:
        return JSONResponse(
            {"error": "unknown_collection", "id": collection_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return {
        "collection_id": collection_id,
        "analyses": llm_db.list_collection_analyses(db, collection_id),
    }


@router.post("/api/collections/{collection_id}/analyses")
def create_collection_analysis(
    collection_id: int,
    body: CreateCollectionAnalysisBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    if collections_db.get_collection(db, collection_id) is None:
        return JSONResponse(
            {"error": "unknown_collection", "id": collection_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if body.analysis_type not in PROMPTS:
        return JSONResponse(
            {
                "error": "unknown_type",
                "analysis_type": body.analysis_type,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    spec = PROMPTS[body.analysis_type]
    if not spec.multi_page:
        return JSONResponse(
            {
                "error": "node_only",
                "analysis_type": body.analysis_type,
                "hint": "use POST /api/analyses for per-node types",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    model = (body.model or get_setting(db, "llm.model") or _DEFAULT_MODEL).strip()
    try:
        new_id = llm_db.enqueue_collection(
            db,
            collection_id=collection_id,
            analysis_type=body.analysis_type,
            model=model,
        )
    except ValueError as exc:
        return JSONResponse(
            {"error": "enqueue_failed", "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return {"id": new_id, "status": "pending"}


# --- cluster analyses (item 7, decision D1) --------------------------------


@router.get("/api/clusters/{fingerprint}/analyses")
def list_cluster_analyses(
    fingerprint: str,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    return {
        "fingerprint": fingerprint,
        "analyses": llm_db.list_cluster_analyses(db, fingerprint),
    }


@router.post("/api/clusters/analyses")
def create_cluster_analysis(
    body: CreateClusterAnalysisBody,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    spec = PROMPTS.get(body.analysis_type)
    if spec is None:
        return JSONResponse(
            {"error": "unknown_type", "analysis_type": body.analysis_type},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    # A cluster analysis is one synthesis row over the whole membership, so the
    # type must be multi-page (Cluster Q&A, Cluster Summary, …). Accepting a
    # single-page type would enqueue a job the worker can only drop.
    if not spec.multi_page:
        return JSONResponse(
            {"error": "not_cluster_type", "analysis_type": body.analysis_type,
             "hint": "cluster analyses require a multi-page synthesis type"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    model = (body.model or get_setting(db, "llm.model") or _DEFAULT_MODEL).strip()
    fingerprint = llm_db.compute_fingerprint(body.resource_ids)
    new_id = llm_db.enqueue_cluster(
        db,
        fingerprint=fingerprint,
        resource_ids=body.resource_ids,
        analysis_type=body.analysis_type,
        model=model,
        label=body.label,
        question=body.question,
        prompt_id=body.prompt_id,
        priority=body.priority,
    )
    return {"id": new_id, "fingerprint": fingerprint, "status": "pending"}


@router.get("/api/cluster-analyses/{analysis_id}")
def get_cluster_analysis(
    analysis_id: int,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    row = llm_db.get_cluster_analysis(db, analysis_id)
    if row is None:
        return JSONResponse(
            {"error": "unknown_analysis", "id": analysis_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return row


@router.delete("/api/cluster-analyses/{analysis_id}")
def delete_cluster_analysis(
    analysis_id: int,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    if not llm_db.cancel_cluster(db, analysis_id):
        return JSONResponse(
            {"error": "not_deletable", "id": analysis_id,
             "hint": "running cluster analyses cannot be deleted"},
            status_code=status.HTTP_409_CONFLICT,
        )
    return {"deleted": analysis_id}


__all__ = ["router"]
