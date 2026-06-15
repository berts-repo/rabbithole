"""sqlite-vec embedding store + ANN query layer.

PLAN.md:344. The embed worker drives this: per tick, :func:`pending` returns
the next batch of pages to embed, :func:`upsert_embedding` writes results, and
:func:`current_models` plus :func:`delete_all_embeddings` together implement
"model swap = full reindex".

The schema reset re-keys the vec0 table on ``page_id`` (was ``node_id``):
embeddings are 1:1 with a ``pages`` row, and the embedded text is the current
``page_versions`` clean body. Identity for the rest of the app is still the
``resources.id`` — :func:`semantic_search` joins ``pages`` → ``resources`` and
returns ``node_id`` = the resource id so search results line up with
``pages.keyword_search`` and the graph.

Vector serialization goes through ``sqlite_vec.serialize_float32`` — passing
a Python list directly raises a binding error inside the vec0 module.

The vec0 table layout (see ``db/core.py``):

    CREATE VIRTUAL TABLE embeddings USING vec0(
        page_id    INTEGER PRIMARY KEY,
        vector     FLOAT[384],
        +model     TEXT,
        +created_at TEXT
    )

The two ``+``-prefixed columns are *auxiliary*: stored but not indexed by
the ANN structure. They read fine in projections; we filter on them in
:func:`pending` via a small subquery, which is acceptable because the
subquery's row count is bounded by the number of already-embedded pages.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

import sqlite_vec

if TYPE_CHECKING:
    from .core import CrawlDB


SEMANTIC_RESULT_CAP = 50  # PLAN.md key constants: "Semantic results cap: 50"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def serialize_vector(values: list[float]) -> bytes:
    """Pack a Python ``list[float]`` into the bytes vec0 expects."""
    return sqlite_vec.serialize_float32(values)


# --- writes -----------------------------------------------------------------


def upsert_embedding(
    db: "CrawlDB",
    *,
    page_id: int,
    vector: bytes,
    model: str,
    when: str | None = None,
) -> None:
    """Insert (or replace) the embedding row for ``page_id``.

    vec0 lacks ``ON CONFLICT`` — we delete-then-insert under one transaction.
    """
    when = when or _now_iso()
    with db.transaction(immediate=True) as c:
        c.execute("DELETE FROM embeddings WHERE page_id = ?", (page_id,))
        c.execute(
            "INSERT INTO embeddings(page_id, vector, model, created_at) "
            "VALUES (?, ?, ?, ?)",
            (page_id, vector, model, when),
        )


def delete_embedding(db: "CrawlDB", page_id: int) -> bool:
    with db.transaction(immediate=True) as c:
        cur = c.execute("DELETE FROM embeddings WHERE page_id = ?", (page_id,))
        return cur.rowcount > 0


def delete_all_embeddings(db: "CrawlDB") -> int:
    """Wipe every row. Returns the deleted count. Used on model swap."""
    with db.transaction(immediate=True) as c:
        cur = c.execute("DELETE FROM embeddings")
        return cur.rowcount


# --- reads ------------------------------------------------------------------


def count_embeddings(db: "CrawlDB", *, model: str | None = None) -> int:
    """Total embedding rows. With ``model`` set, restrict to that model."""
    with db.read() as c:
        if model is None:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM embeddings"
            ).fetchone()
        else:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM embeddings WHERE model = ?",
                (model,),
            ).fetchone()
    return int(row["n"]) if row is not None else 0


def count_eligible_pages(db: "CrawlDB") -> int:
    """How many pages the embed worker would consider in total.

    A page is eligible when it has a current version with non-empty clean text
    and is not ``embed_excluded``.
    """
    with db.read() as c:
        row = c.execute(
            "SELECT COUNT(*) AS n FROM pages p "
            "JOIN page_versions pv ON pv.id = p.current_version_id "
            "WHERE p.embed_excluded = 0 "
            "  AND pv.body_text_clean IS NOT NULL "
            "  AND length(pv.body_text_clean) > 0"
        ).fetchone()
    return int(row["n"]) if row is not None else 0


def current_models(db: "CrawlDB") -> list[str]:
    """Distinct models present in the embeddings table.

    Empty list when the table is empty. >1 entry signals a stale state
    (mid-swap or a previous worker crash) — the worker treats anything
    other than ``[active_model]`` as "needs reindex".
    """
    with db.read() as c:
        rows = c.execute(
            "SELECT DISTINCT model FROM embeddings"
        ).fetchall()
    return [str(r["model"]) for r in rows if r["model"] is not None]


def pending(
    db: "CrawlDB", *, model: str, limit: int = 50
) -> list[dict[str, Any]]:
    """Pages that need embedding under the active ``model``.

    Returns ``[{page_id, resource_id}, ...]``. Excludes:
      * pages with no current version / empty clean text (uncrawled, or a
        Content-Type-discarded fetch)
      * ``embed_excluded`` pages (poison-pill flag)
      * pages already embedded under the current ``model``

    Ordered by the resource's ``last_seen DESC`` so the most-recent crawl bias
    gives the analyst something to query immediately after the worker starts.
    The worker keys the vec0 row by ``page_id`` and resolves the poison-pill
    exclusion by ``resource_id`` (the flag lives on ``pages``).
    """
    with db.read() as c:
        rows = c.execute(
            """SELECT p.id AS page_id, p.resource_id AS resource_id
                 FROM pages p
                 JOIN page_versions pv ON pv.id = p.current_version_id
                 JOIN resources r ON r.id = p.resource_id
                WHERE p.embed_excluded = 0
                  AND pv.body_text_clean IS NOT NULL
                  AND length(pv.body_text_clean) > 0
                  AND p.id NOT IN (
                      SELECT page_id FROM embeddings WHERE model = ?
                  )
                ORDER BY r.last_seen DESC, p.id DESC
                LIMIT ?""",
            (model, limit),
        ).fetchall()
    return [
        {"page_id": int(r["page_id"]), "resource_id": int(r["resource_id"])}
        for r in rows
    ]


def semantic_search(
    db: "CrawlDB",
    *,
    query_vec: bytes,
    limit: int = SEMANTIC_RESULT_CAP,
) -> list[dict[str, Any]]:
    """ANN search against the embeddings table, joined back to resources.

    Returns ``[{node_id, url, title, distance}, ...]`` sorted by distance
    ascending — ``node_id`` is the ``resources.id`` (the app identity), ``url``
    from the resource and ``title`` from its current page version. ``limit`` is
    hard-clamped to ``SEMANTIC_RESULT_CAP`` per PLAN.md.

    vec0's ANN syntax requires both ``vector MATCH ?`` and ``k = ?`` in the
    WHERE clause and ``ORDER BY distance``. ``k`` must be bound separately
    (some driver paths reject it as a literal placeholder otherwise).
    """
    k = max(1, min(int(limit), SEMANTIC_RESULT_CAP))
    with db.read() as c:
        try:
            rows = c.execute(
                """SELECT e.distance, r.id AS resource_id, r.url, pv.title
                   FROM embeddings e
                   JOIN pages p ON p.id = e.page_id
                   JOIN resources r ON r.id = p.resource_id
                   LEFT JOIN page_versions pv ON pv.id = p.current_version_id
                   WHERE e.vector MATCH ? AND k = ?
                   ORDER BY e.distance""",
                (query_vec, k),
            ).fetchall()
        except sqlite3.OperationalError:
            # Empty embeddings table → vec0 raises. Treat as empty result.
            return []
    return [
        {
            "node_id": int(r["resource_id"]),
            "url": r["url"],
            "title": r["title"],
            "distance": float(r["distance"]),
        }
        for r in rows
    ]


__all__ = [
    "SEMANTIC_RESULT_CAP",
    "count_eligible_pages",
    "count_embeddings",
    "current_models",
    "delete_all_embeddings",
    "delete_embedding",
    "pending",
    "semantic_search",
    "serialize_vector",
    "upsert_embedding",
]
