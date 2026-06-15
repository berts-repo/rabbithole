"""Resources — URL identity and the canonical lifecycle state machine.

A ``resources`` row is the identity that the rest of the graph points at:
edges, crawl_nodes, collection_items, flags, findings, analyses, graph_nodes,
and embeddings all FK ``resources(id)``. It carries the URL, its host, and the
single canonical ``state`` (``unknown`` / ``known`` / ``crawled`` / ``dead``)
that replaced the old ``nodes.stub`` boolean and ``crawl_queue.lookup_state``.

Crawled content does **not** live here — it lives on ``pages`` /
``page_versions`` (see ``pages.py`` / ``page_versions.py``). This module owns
only identity + state.

``resources.host`` FKs ``domains(host)``, so :func:`upsert_resource` ensures
the domain row exists before inserting — callers no longer have to order a
``domains`` write ahead of a resource write.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ..security.net import network_of_host

if TYPE_CHECKING:
    from .core import CrawlDB


STATES = ("unknown", "known", "crawled", "dead")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_domain(c: Any, host: str, when: str | None) -> None:
    """Make sure a ``domains`` row exists for ``host`` (FK target)."""
    c.execute(
        "INSERT INTO domains(host, last_seen) VALUES (?, ?) "
        "ON CONFLICT(host) DO NOTHING",
        (host, when),
    )


def upsert_resource(
    db: "CrawlDB",
    url: str,
    host: str,
    *,
    state: str = "known",
    when: str | None = None,
) -> int:
    """Return the resource id for ``url``, inserting it if missing.

    A freshly-discovered URL is recorded at ``state='known'`` (was a stub).
    If the resource already exists its state is left untouched — only the
    crawl-write path (:func:`set_state`) promotes it to ``crawled``. The
    domain row is ensured first so the host FK holds.
    """
    if state not in STATES:
        raise ValueError(f"bad_state:{state}")
    # first_seen is NOT NULL — always stamp it, even if a caller omits `when`.
    when = when or _now()
    with db.transaction(immediate=True) as c:
        row = c.execute("SELECT id FROM resources WHERE url = ?", (url,)).fetchone()
        if row is not None:
            return int(row["id"])
        _ensure_domain(c, host, when)
        # Network is derived once from the host suffix; search and graph read
        # the stored value rather than re-inferring per query.
        network = network_of_host(host)
        cur = c.execute(
            "INSERT INTO resources(url, host, network, state, first_seen, "
            "last_seen, last_state_change) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (url, host, network, state, when, when, when),
        )
        return int(cur.lastrowid)


def set_state(
    db: "CrawlDB", resource_id: int, state: str, *, when: str | None = None
) -> bool:
    """Move a resource to ``state``, stamping ``last_state_change``."""
    if state not in STATES:
        raise ValueError(f"bad_state:{state}")
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "UPDATE resources SET state = ?, last_state_change = ? WHERE id = ?",
            (state, when, resource_id),
        )
        return cur.rowcount > 0


def mark_dead(db: "CrawlDB", resource_id: int, *, when: str | None = None) -> bool:
    """Terminal state after repeated failures (auto) or analyst override."""
    return set_state(db, resource_id, "dead", when=when)


def get_resource(db: "CrawlDB", resource_id: int) -> dict[str, Any] | None:
    with db.read() as c:
        row = c.execute(
            "SELECT * FROM resources WHERE id = ?", (resource_id,)
        ).fetchone()
    return {k: row[k] for k in row.keys()} if row is not None else None


def lookup_by_urls(db: "CrawlDB", urls: list[str]) -> dict[str, dict[str, Any]]:
    """Return ``{url: {id, state, last_seen}}`` for known URLs.

    Unknown URLs are absent from the map — the caller fills in ``unknown``.
    Replaces the old ``stub``-keyed lookup used to badge bulk-import rows.
    """
    if not urls:
        return {}
    placeholders = ",".join("?" * len(urls))
    with db.read() as c:
        rows = c.execute(
            f"SELECT id, url, state, last_seen FROM resources "
            f"WHERE url IN ({placeholders})",
            urls,
        ).fetchall()
    return {
        r["url"]: {
            "id": int(r["id"]),
            "state": r["state"],
            "last_seen": r["last_seen"],
        }
        for r in rows
    }


def state_by_ids(db: "CrawlDB", resource_ids: list[int]) -> dict[int, str]:
    """Return ``{resource_id: state}`` for ids that reference an existing row."""
    ids = [int(n) for n in resource_ids]
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    with db.read() as c:
        rows = c.execute(
            f"SELECT id, state FROM resources WHERE id IN ({placeholders})", ids
        ).fetchall()
    return {int(r["id"]): r["state"] for r in rows}


def crawled_url_set(db: "CrawlDB") -> set[str]:
    """Snapshot of crawled URLs — badges engine results as already-known."""
    with db.read() as c:
        rows = c.execute(
            "SELECT url FROM resources WHERE state = 'crawled'"
        ).fetchall()
    return {str(r["url"]) for r in rows}


def crawled_meta_by_url(db: "CrawlDB") -> dict[str, dict[str, Any]]:
    """``{url: {id, title, category, last_seen}}`` for every crawled resource.

    The richer sibling of :func:`crawled_url_set`: the Search tab needs more
    than a membership test for already-crawled engine hits — it shows the
    node id (so "→ Graph" can highlight) plus the title/category/last-seen the
    spec lists on a crawled result row. Title/category are sourced exactly as
    the graph builder does (``db/graph.py``): title from the current page
    version, category from the page row; both NULL until the resource has a
    crawled page.
    """
    with db.read() as c:
        rows = c.execute(
            """SELECT r.id AS id, r.url AS url, r.last_seen AS last_seen,
                      pv.title AS title, p.category AS category
                 FROM resources r
                 LEFT JOIN pages p ON p.resource_id = r.id
                 LEFT JOIN page_versions pv ON pv.id = p.current_version_id
                WHERE r.state = 'crawled'"""
        ).fetchall()
    return {
        str(r["url"]): {
            "id": int(r["id"]),
            "title": r["title"],
            "category": r["category"],
            "last_seen": r["last_seen"],
        }
        for r in rows
    }


def recent_failure_count(db: "CrawlDB", resource_id: int, *, since: str) -> int:
    """Count failed (4xx/5xx/0) current-page fetches since ``since``.

    Backs the dead-state auto-transition (default 5 failures / 7 days): a
    resource's page versions whose ``http_status`` is missing or >= 400 since
    the cutoff. Computed from ``page_versions`` rather than a counter column.
    """
    with db.read() as c:
        row = c.execute(
            """SELECT COUNT(*) AS n
                 FROM page_versions pv
                 JOIN pages p ON p.id = pv.page_id
                WHERE p.resource_id = ?
                  AND pv.fetched_at >= ?
                  AND (pv.http_status IS NULL OR pv.http_status >= 400)""",
            (resource_id, since),
        ).fetchone()
    return int(row["n"]) if row is not None else 0


__all__ = [
    "STATES",
    "crawled_meta_by_url",
    "crawled_url_set",
    "get_resource",
    "lookup_by_urls",
    "mark_dead",
    "recent_failure_count",
    "set_state",
    "state_by_ids",
    "upsert_resource",
]
