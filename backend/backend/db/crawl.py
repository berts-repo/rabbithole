"""Crawl-run / seed / schedule helpers.

The ``crawls`` table is per-run **execution detail** — counters, mode,
seed, timing — and ``crawl_nodes`` links each run to the resource ids it
touched. After the schema reset ``crawls`` no longer carries a ``status``
column: work-tracking status lives on the linked ``jobs`` row
(``kind='crawl'``, ``payload.crawl_id = crawls.id``), so the two never drift.
The :class:`CrawlRunner` owns that job's status transitions; this module owns
the durable per-run detail.

``set_started`` / ``finalize`` stamp the crawl's own timing; ``find_active``
and ``list_crawls`` read the live status by joining the linked job. ``seeds``
and ``crawl_schedules`` are small CRUD tables driven by their routes.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from . import jobs as jobs_db

if TYPE_CHECKING:
    from .core import CrawlDB


# --- crawls -----------------------------------------------------------------


Counter = Literal["pages_crawled", "pages_failed", "pages_queued", "pages_skipped"]

_VALID_COUNTERS: frozenset[str] = frozenset(
    ("pages_crawled", "pages_failed", "pages_queued", "pages_skipped")
)

VALID_MODES: tuple[str, ...] = ("Cross-site", "BFS", "DFS", "Diverse", "Focused")


def create_crawl(
    db: "CrawlDB",
    *,
    seed_url: str,
    mode: str,
    collection_id: int | None,
    max_depth: int | None,
) -> int:
    """Insert a per-run ``crawls`` detail row. Returns the new id.

    No status column any more — the linked ``jobs`` row (created by the queue
    runner alongside this) owns work-tracking status. Mode validation is the
    route handler's job (the CHECK constraint in ``db/core.py`` is the second
    line of defence).
    """
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            """INSERT INTO crawls(
                seed_url, mode, collection_id, max_depth
            ) VALUES (?, ?, ?, ?)""",
            (seed_url, mode, collection_id, max_depth),
        )
        return int(cur.lastrowid)


def set_started(db: "CrawlDB", crawl_id: int, when: str) -> None:
    """Stamp the run's ``started_at`` (the job's status flips separately)."""
    with db.transaction(immediate=True) as c:
        c.execute(
            "UPDATE crawls SET started_at=? WHERE id=?", (when, crawl_id)
        )


def finalize(
    db: "CrawlDB",
    crawl_id: int,
    when: str,
    *,
    error: str | None = None,
) -> None:
    """Stamp the run's ``completed_at`` (+ optional error) on any terminal exit.

    The terminal *status* (done / cancelled / failed) is written to the linked
    ``jobs`` row by the runner; this records the per-run timing/error detail.
    """
    with db.transaction(immediate=True) as c:
        c.execute(
            "UPDATE crawls SET completed_at=?, error=? WHERE id=?",
            (when, error, crawl_id),
        )


def mark_stopped(
    db: "CrawlDB",
    crawl_id: int,
    when: str,
    *,
    error: str | None = None,
) -> None:
    """Reap a half-state crawl: finalize the run and cancel its linked job.

    Used by ``POST /api/crawl/stop`` when no in-process runner exists but the
    linked ``jobs`` row still reads ``running``/``paused`` (e.g. a process
    crash left the work-status hanging). Stamps the ``crawls`` detail terminal
    via :func:`finalize` and cancels the ``kind='crawl'`` job
    (``payload.crawl_id = crawl_id``) so :func:`find_active` no longer surfaces
    it and the next crawl can start.
    """
    finalize(db, crawl_id, when, error=error)
    jobs_db.cancel_active_for(db, payload_key="crawl_id", value=crawl_id)


def bump_counter(db: "CrawlDB", crawl_id: int, field: Counter) -> None:
    if field not in _VALID_COUNTERS:
        raise ValueError(f"unknown counter: {field!r}")
    with db.transaction(immediate=True) as c:
        c.execute(
            f"UPDATE crawls SET {field} = {field} + 1 WHERE id = ?",  # noqa: S608
            (crawl_id,),
        )


def link_crawl_node(
    db: "CrawlDB", crawl_id: int, node_id: int, depth: int | None
) -> None:
    """Best-effort link. PK collision (re-visiting the same node) is silent."""
    with db.transaction(immediate=True) as c:
        c.execute(
            "INSERT OR IGNORE INTO crawl_nodes(crawl_id, node_id, depth) "
            "VALUES (?, ?, ?)",
            (crawl_id, node_id, depth),
        )


def find_active(db: "CrawlDB") -> dict[str, object] | None:
    """Return the run whose linked job is ``running``/``paused``, if any.

    Status comes from the ``jobs`` row (``kind='crawl'`` joined via
    ``payload.crawl_id``); counters/timing from the ``crawls`` detail row.
    The poller calls ``GET /api/crawl/status`` while a crawl runs.
    """
    with db.read() as c:
        row = c.execute(
            "SELECT c.id, c.seed_url, c.mode, j.status AS status, "
            "c.pages_crawled, c.pages_failed, c.pages_queued, "
            "c.started_at, c.collection_id "
            "FROM crawls c "
            "JOIN jobs j ON j.kind='crawl' "
            "  AND json_extract(j.payload, '$.crawl_id') = c.id "
            "WHERE j.status IN ('running','paused') "
            "ORDER BY c.id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def list_crawls(db: "CrawlDB", limit: int = 50) -> list[dict[str, object]]:
    """Most recent first. Used by the Crawl sub-tab history list.

    Joins each run to its ``jobs`` row so the history list carries the live
    status without a ``crawls.status`` column.
    """
    limit = max(1, min(limit, 500))
    with db.read() as c:
        rows = c.execute(
            "SELECT c.*, j.status AS status "
            "FROM crawls c "
            "LEFT JOIN jobs j ON j.kind='crawl' "
            "  AND json_extract(j.payload, '$.crawl_id') = c.id "
            "ORDER BY c.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{k: r[k] for k in r.keys()} for r in rows]


def get_crawl(db: "CrawlDB", crawl_id: int) -> dict[str, object] | None:
    with db.read() as c:
        row = c.execute(
            "SELECT * FROM crawls WHERE id = ?", (crawl_id,)
        ).fetchone()
    return None if row is None else {k: row[k] for k in row.keys()}


# ``last_started_at`` was retired with the v2 schema bump (audit-trail
# item 3 — the durable crawl queue is canonical for schedule retiming).
# The replacement lives at ``CrawlQueueRunner._last_schedule_fire`` and
# reads schedule-sourced crawl ``jobs`` (``payload.source='schedule'``,
# by ``created_at`` — when we intended to run) rather than ``crawls`` rows
# (when a run actually started), which is what prevents a double-fire when
# the queue is paused or the kill switch holds dispatch longer than the
# schedule interval.


# --- seeds ------------------------------------------------------------------


def list_seeds(db: "CrawlDB") -> list[dict[str, object]]:
    with db.read() as c:
        rows = c.execute(
            "SELECT url, label, added_at FROM seeds ORDER BY added_at DESC, url ASC"
        ).fetchall()
    return [{k: r[k] for k in r.keys()} for r in rows]


def add_seed(db: "CrawlDB", *, url: str, label: str | None, when: str) -> bool:
    """Insert a seed. Returns ``False`` if the URL already existed."""
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO seeds(url, label, added_at) VALUES (?, ?, ?)",
            (url, label, when),
        )
        return cur.rowcount > 0


def remove_seed(db: "CrawlDB", url: str) -> bool:
    with db.transaction(immediate=True) as c:
        cur = c.execute("DELETE FROM seeds WHERE url = ?", (url,))
        return cur.rowcount > 0


def update_seed_label(db: "CrawlDB", *, url: str, label: str | None) -> bool:
    """Rename a seed's label in place. Returns ``False`` if no row matched.

    URL is the seeds PK so the (url, added_at) shape stays stable across
    rename — the bookmark keeps its position in the date-sorted list.
    """
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "UPDATE seeds SET label = ? WHERE url = ?", (label, url)
        )
        return cur.rowcount > 0


# --- schedules --------------------------------------------------------------


def list_schedules(db: "CrawlDB") -> list[dict[str, object]]:
    with db.read() as c:
        rows = c.execute(
            "SELECT url, label, interval_hours, mode, active, collection_id "
            "FROM crawl_schedules ORDER BY url ASC"
        ).fetchall()
    return [
        {
            "url": r["url"],
            "label": r["label"],
            "interval_hours": r["interval_hours"],
            "mode": r["mode"],
            "active": bool(r["active"]),
            "collection_id": r["collection_id"],
        }
        for r in rows
    ]


def list_active_schedules(db: "CrawlDB") -> list[dict[str, object]]:
    """Schedules with ``active=1``. Used by ``crawl_queue_runner``."""
    with db.read() as c:
        rows = c.execute(
            "SELECT url, label, interval_hours, mode, collection_id "
            "FROM crawl_schedules WHERE active = 1"
        ).fetchall()
    return [
        {
            "url": r["url"],
            "label": r["label"],
            "interval_hours": r["interval_hours"],
            "mode": r["mode"],
            "collection_id": r["collection_id"],
        }
        for r in rows
    ]


def upsert_schedule(
    db: "CrawlDB",
    *,
    url: str,
    label: str | None,
    interval_hours: float,
    mode: str,
    collection_id: int | None,
    active: bool = True,
) -> None:
    with db.transaction(immediate=True) as c:
        c.execute(
            """INSERT INTO crawl_schedules(
                url, label, interval_hours, mode, active, collection_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                label = excluded.label,
                interval_hours = excluded.interval_hours,
                mode = excluded.mode,
                active = excluded.active,
                collection_id = excluded.collection_id""",
            (url, label, interval_hours, mode, 1 if active else 0, collection_id),
        )


def patch_schedule(
    db: "CrawlDB",
    url: str,
    *,
    label: str | None = None,
    interval_hours: float | None = None,
    mode: str | None = None,
    active: bool | None = None,
    collection_id: int | None = None,
) -> bool:
    """Apply only the provided fields. Returns ``True`` if the row exists."""
    sets: list[str] = []
    args: list[object] = []
    if label is not None:
        sets.append("label = ?")
        args.append(label)
    if interval_hours is not None:
        sets.append("interval_hours = ?")
        args.append(interval_hours)
    if mode is not None:
        sets.append("mode = ?")
        args.append(mode)
    if active is not None:
        sets.append("active = ?")
        args.append(1 if active else 0)
    if collection_id is not None:
        sets.append("collection_id = ?")
        args.append(collection_id)
    if not sets:
        # No-op PATCH; just verify existence.
        with db.read() as c:
            row = c.execute(
                "SELECT 1 FROM crawl_schedules WHERE url = ?", (url,)
            ).fetchone()
        return row is not None
    args.append(url)
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            f"UPDATE crawl_schedules SET {', '.join(sets)} WHERE url = ?",
            args,
        )
        return cur.rowcount > 0


def remove_schedule(db: "CrawlDB", url: str) -> bool:
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "DELETE FROM crawl_schedules WHERE url = ?", (url,)
        )
        return cur.rowcount > 0


__all__ = [
    "VALID_MODES",
    "add_seed",
    "bump_counter",
    "create_crawl",
    "finalize",
    "find_active",
    "get_crawl",
    "link_crawl_node",
    "mark_stopped",
    "list_active_schedules",
    "list_crawls",
    "list_schedules",
    "list_seeds",
    "patch_schedule",
    "set_started",
    "remove_schedule",
    "remove_seed",
    "upsert_schedule",
]
