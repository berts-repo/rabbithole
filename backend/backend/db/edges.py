"""Edge helpers (crawl-edge insert + analyst create / source-lookup / delete).

Edges have a ``source`` column (``'crawl'`` or ``'analyst'``) and point at
``resources(id)``. Crawl edges are derived data written by the runtime via
:func:`insert_crawl_edge`; the analyst helpers below only ever touch
``source='analyst'`` edges.
"""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import CrawlDB


class EdgeConflictError(Exception):
    """``edges`` PK/uniqueness violation on analyst insert."""


def insert_crawl_edge(
    db: "CrawlDB",
    *,
    from_id: int,
    to_id: int,
    anchor_text: str | None,
) -> None:
    """Insert a ``source='crawl'`` edge between two resources. PK collisions
    are silent (re-crawling a link never duplicates the edge). Self-loops are
    skipped. Moved here from the old ``db.nodes`` module in the schema reset.
    """
    if from_id == to_id:
        return
    with db.transaction(immediate=True) as c:
        c.execute(
            "INSERT OR IGNORE INTO edges(from_id, to_id, anchor_text, source) "
            "VALUES (?, ?, ?, 'crawl')",
            (from_id, to_id, anchor_text),
        )


def create_analyst_edge(
    db: "CrawlDB",
    *,
    from_id: int,
    to_id: int,
    anchor_text: str | None,
    label: str | None,
) -> None:
    """Insert one ``source='analyst'`` edge.

    Raises ``EdgeConflictError`` if the row already exists (PK collision).
    Self-loops are rejected by the caller before this point.
    """
    try:
        with db.transaction(immediate=True) as c:
            c.execute(
                "INSERT INTO edges(from_id, to_id, anchor_text, source, label) "
                "VALUES (?, ?, ?, 'analyst', ?)",
                (from_id, to_id, anchor_text, label),
            )
    except sqlite3.IntegrityError as exc:
        raise EdgeConflictError(str(exc)) from exc


def get_edge_source(
    db: "CrawlDB", *, from_id: int, to_id: int
) -> str | None:
    """Return the ``source`` column for one edge, or ``None`` if missing."""
    with db.read() as c:
        row = c.execute(
            "SELECT source FROM edges WHERE from_id = ? AND to_id = ?",
            (from_id, to_id),
        ).fetchone()
    return None if row is None else str(row["source"])


def delete_analyst_edge(
    db: "CrawlDB", *, from_id: int, to_id: int
) -> int:
    """Delete one analyst edge. Returns affected row count (0 or 1)."""
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "DELETE FROM edges WHERE from_id = ? AND to_id = ? "
            "AND source = 'analyst'",
            (from_id, to_id),
        )
        return cur.rowcount


__all__ = [
    "EdgeConflictError",
    "create_analyst_edge",
    "delete_analyst_edge",
    "get_edge_source",
    "insert_crawl_edge",
]
