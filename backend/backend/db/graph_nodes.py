"""Graph node metadata — persisted render/layout/metric values per resource.

Split out of the old ``nodes`` god table: layout coordinates (``x`` / ``y``),
the cluster id, and the centrality metrics (``pagerank`` / ``betweenness``)
now live in their own 1:1 table keyed by ``resource_id``. This keeps the
``resources`` identity row lean and lets the graph payload builder persist
computed metrics without widening the lifecycle table.

A row is optional: a resource with no ``graph_nodes`` row simply has no cached
layout/metrics yet (the graph builder falls back to computing on demand).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .core import CrawlDB


def upsert_metrics(
    db: "CrawlDB",
    resource_id: int,
    *,
    x: float | None = None,
    y: float | None = None,
    cluster: int | None = None,
    pagerank: float | None = None,
    betweenness: float | None = None,
) -> None:
    """Insert or update the cached metrics for one resource."""
    with db.transaction(immediate=True) as c:
        c.execute(
            """INSERT INTO graph_nodes(resource_id, x, y, cluster, pagerank, betweenness)
                 VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(resource_id) DO UPDATE SET
                 x=excluded.x, y=excluded.y, cluster=excluded.cluster,
                 pagerank=excluded.pagerank, betweenness=excluded.betweenness""",
            (resource_id, x, y, cluster, pagerank, betweenness),
        )


def get_metrics(db: "CrawlDB", resource_id: int) -> dict[str, Any] | None:
    with db.read() as c:
        row = c.execute(
            "SELECT * FROM graph_nodes WHERE resource_id = ?", (resource_id,)
        ).fetchone()
    return {k: row[k] for k in row.keys()} if row is not None else None


def all_metrics(db: "CrawlDB") -> dict[int, dict[str, Any]]:
    """``{resource_id: {x, y, cluster, pagerank, betweenness}}`` for all rows."""
    with db.read() as c:
        rows = c.execute("SELECT * FROM graph_nodes").fetchall()
    return {int(r["resource_id"]): {k: r[k] for k in r.keys()} for r in rows}


def clear(db: "CrawlDB") -> int:
    """Drop all cached metrics (e.g. before a full recompute)."""
    with db.transaction(immediate=True) as c:
        cur = c.execute("DELETE FROM graph_nodes")
        return cur.rowcount


__all__ = ["all_metrics", "clear", "get_metrics", "upsert_metrics"]
