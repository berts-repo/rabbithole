"""In-DB search routes (keyword via FTS5 + semantic via sqlite-vec).

PLAN.md:345.

Keyword search: ``pages_fts`` is FTS5 over the current page version's
``body_text_clean``. Raw user input goes through ``_quote_fts`` which wraps
it as a single phrase to neutralize FTS5 operator chars (``"`` ``*`` ``:``
``(`` ``)`` ``^`` ``+`` ``-`` ``NEAR`` ``OR`` ``AND`` ``NOT``). The SQL lives
in ``db.pages.keyword_search``; because ``pages_fts`` is contentless, the
snippet is rebuilt in Python from the page's clean text — a 24-token window
with ``<mark>`` tags around hits which the frontend renders in a sandboxed
pre tag (CSP forbids inline scripts).

Semantic search: encodes the query with the embed worker's loaded
fastembed model and runs an ANN query against ``embeddings``. Returns
``503 embed_unavailable`` rather than synchronously loading the model
in the request path — the worker owns the model lifecycle.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from ..db import embed as embed_db
from ..db import findings as findings_db
from ..db import pages as pages_db
from ..db.core import CrawlDB
from ..services.embed_worker import EmbedNotReady, EmbedWorker
from .deps import get_active_db


router = APIRouter()


_KEYWORD_LIMIT_MAX = 200
_SEMANTIC_LIMIT_MAX = embed_db.SEMANTIC_RESULT_CAP
_SNIPPET_TOKENS = 24
# Findings (entity + note) get their own budget on top of the page `limit` so a
# flood of page FTS hits can't starve the structured matches the analyst came
# for. Pages lead by FTS rank; entity/note rows follow. See package decisions D2.
_FINDINGS_SUBLIMIT = 25


def _quote_fts(query: str) -> str:
    """Wrap ``query`` as one FTS5 phrase. ``"`` is escaped by doubling."""
    cleaned = "".join(
        ch for ch in query if ch == "\t" or ch >= " "
    ).strip()
    if not cleaned:
        return ""
    escaped = cleaned.replace('"', '""')
    return '"' + escaped + '"'


@router.get("/api/search/keyword")
def keyword_search(
    q: str = "",
    limit: int = 50,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    quoted = _quote_fts(q)
    if not quoted:
        return {"results": []}
    capped = max(1, min(int(limit), _KEYWORD_LIMIT_MAX))
    try:
        pages = pages_db.keyword_search(
            db,
            fts_query=quoted,
            query_text=q,
            limit=capped,
            snippet_tokens=_SNIPPET_TOKENS,
        )
    except pages_db.FtsQueryError as exc:
        return JSONResponse(
            {"error": "fts_query_failed", "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    # Page FTS hits lead (real relevance signal); entity + note substring
    # matches follow under their own sub-cap so they always surface.
    findings = findings_db.search_findings(
        db, query_text=q, limit=min(capped, _FINDINGS_SUBLIMIT)
    )
    return {"results": pages + findings}


@router.get("/api/search/semantic")
def semantic_search(
    request: Request,
    q: str = "",
    limit: int = 50,
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    text = q.strip()
    if not text:
        return {"results": []}
    worker: EmbedWorker | None = getattr(request.app.state, "embed_worker", None)
    if worker is None:
        return JSONResponse(
            {"error": "embed_unavailable", "message": "embed worker not configured"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    try:
        query_vec = worker.encode(text)
    except EmbedNotReady as exc:
        return JSONResponse(
            {"error": "embed_unavailable", "message": str(exc)},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    capped = max(1, min(int(limit), _SEMANTIC_LIMIT_MAX))
    rows = embed_db.semantic_search(db, query_vec=query_vec, limit=capped)
    return {"results": rows}


__all__ = ["router"]
