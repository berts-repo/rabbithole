"""Unified work-tracking helpers — the single ``jobs`` table.

Every piece of background work across the app — crawls, scheduled-crawl
firings, analyses, monitor probes, live-crawl progress, batch intake — writes
one ``jobs`` row with one status vocabulary
(``pending`` / ``running`` / ``done`` / ``failed`` / ``cancelled`` / ``paused``).
Source-specific config and back-references to typed detail tables live in
``payload`` (JSON); completion data in ``result`` (JSON).

This replaces the old ``crawl_queue`` table and the per-source status columns
on ``crawls`` / ``analyses`` / ``collection_analyses`` / ``monitors``. Those
typed tables keep their durable detail and read their work-status from the
linked ``jobs`` row (``payload`` carries e.g. ``crawl_id`` / ``analysis_id``),
so the two can never drift.

The Activity bottom-pane tab and ``routes/jobs.py`` consume these helpers; the
crawl queue runner uses :func:`claim_next_crawl` to atomically pull the next
pending crawl.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from .core import CrawlDB


KINDS = ("crawl", "schedule", "analysis", "probe", "live-crawl", "batch")
TARGET_TYPES = ("url", "domain", "collection", "cluster")
STATUSES = ("pending", "running", "done", "failed", "cancelled", "paused")

# Work that has not reached a terminal state. Used by recipe-delete cascades
# (cancel in-flight firings) and by retention purges (terminal rows only).
ACTIVE_STATUSES = ("pending", "running", "paused")
TERMINAL_STATUSES = ("done", "failed", "cancelled")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dumps(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"))


def _loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


def _row_to_dict(row: Any) -> dict[str, Any]:
    data = {k: row[k] for k in row.keys()}
    data["payload"] = _loads(data.get("payload"))
    data["result"] = _loads(data.get("result"))
    return data


# --- writes ----------------------------------------------------------------


def create_job(
    db: "CrawlDB",
    *,
    kind: str,
    target_type: str,
    target_id: int,
    status: str = "pending",
    payload: Any = None,
    result: Any = None,
    error: str | None = None,
) -> int:
    """Insert a job row and return its id.

    ``kind`` / ``target_type`` / ``status`` are CHECK-constrained at the DB
    layer; passing an out-of-vocabulary value raises rather than silently
    storing it. ``payload`` / ``result`` accept any JSON-serializable value
    (dict/list/str) and are stored as JSON text.
    """
    now = _now()
    started = now if status == "running" else None
    finished = now if status in TERMINAL_STATUSES else None
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            """INSERT INTO jobs(
                kind, target_type, target_id, status, payload, result, error,
                created_at, started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                kind, target_type, int(target_id), status,
                _dumps(payload), _dumps(result), error,
                now, started, finished,
            ),
        )
        return int(cur.lastrowid)


def set_status(
    db: "CrawlDB",
    job_id: int,
    status: str,
    *,
    result: Any = None,
    error: str | None = None,
) -> bool:
    """Transition a job to ``status``, stamping started/finished timestamps.

    Setting ``running`` stamps ``started_at`` if not already set; setting any
    terminal status stamps ``finished_at``. ``result`` / ``error`` are written
    only when provided (``None`` leaves the existing column untouched).
    """
    now = _now()
    sets = ["status=?"]
    params: list[Any] = [status]
    if status == "running":
        sets.append("started_at=COALESCE(started_at, ?)")
        params.append(now)
    if status in TERMINAL_STATUSES:
        sets.append("finished_at=?")
        params.append(now)
    if result is not None:
        sets.append("result=?")
        params.append(_dumps(result))
    if error is not None:
        sets.append("error=?")
        params.append(error)
    params.append(int(job_id))
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            f"UPDATE jobs SET {', '.join(sets)} WHERE id=?", params
        )
        return cur.rowcount > 0


def update_payload(db: "CrawlDB", job_id: int, payload: Any) -> bool:
    """Overwrite a job's ``payload`` JSON (e.g. live-crawl progress)."""
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "UPDATE jobs SET payload=? WHERE id=?",
            (_dumps(payload), int(job_id)),
        )
        return cur.rowcount > 0


def claim_next_crawl(db: "CrawlDB") -> dict[str, Any] | None:
    """Atomically claim the next pending crawl job, marking it ``running``.

    Mirrors the old ``crawl_queue.claim_next`` SELECT-then-UPDATE under a
    single ``BEGIN IMMEDIATE`` so two dispatch passes can't claim the same
    row. Returns the claimed job dict (status already ``running``) or ``None``
    when no pending crawl work exists. Honours nothing about the queue-paused
    gate — the caller checks ``crawl.queue_paused`` before claiming.
    """
    now = _now()
    with db.transaction(immediate=True) as c:
        row = c.execute(
            "SELECT * FROM jobs WHERE kind='crawl' AND status='pending' "
            "ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        job_id = int(row["id"])
        c.execute(
            "UPDATE jobs SET status='running', started_at=COALESCE(started_at, ?) "
            "WHERE id=?",
            (now, job_id),
        )
        claimed = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return _row_to_dict(claimed)


def delete_job(db: "CrawlDB", job_id: int) -> bool:
    """Remove a single job row (terminal-row cleanup / "Clear")."""
    with db.transaction(immediate=True) as c:
        cur = c.execute("DELETE FROM jobs WHERE id = ?", (int(job_id),))
        return cur.rowcount > 0


def _retention_cutoff_iso(older_than_days: int) -> str:
    """ISO cutoff: jobs finished before this are eligible for retention purge."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    return cutoff.isoformat(timespec="seconds")


def count_prunable_terminal_jobs(db: "CrawlDB", *, older_than_days: int) -> int:
    """Count terminal jobs a retention run would delete right now.

    Mirrors :func:`prune_terminal_jobs`'s predicate without deleting, so the
    Settings → Retention tab can show how many records are eligible before the
    analyst commits. A non-positive ``older_than_days`` means retention is off
    (keep history forever) and returns 0.
    """
    if older_than_days <= 0:
        return 0
    cutoff = _retention_cutoff_iso(older_than_days)
    placeholders = ",".join("?" * len(TERMINAL_STATUSES))
    with db.read() as c:
        row = c.execute(
            f"SELECT COUNT(*) AS n FROM jobs WHERE status IN ({placeholders}) "
            "AND finished_at IS NOT NULL AND finished_at < ?",
            (*TERMINAL_STATUSES, cutoff),
        ).fetchone()
    return int(row["n"]) if row is not None else 0


def prune_terminal_jobs(db: "CrawlDB", *, older_than_days: int) -> int:
    """Delete terminal (``done``/``failed``/``cancelled``) jobs finished more
    than ``older_than_days`` ago. Returns the number of rows removed.

    A non-positive ``older_than_days`` is a no-op (retention off — keep job
    history forever) and returns 0. Terminal job rows carry no foreign-key
    dependents — other tables link to a job through its JSON ``payload``, not a
    FK — so this is just the batch form of the per-row :func:`delete_job` the
    Activity "Clear" already uses. Investigation data (page snapshots, analyses)
    is never touched: this prunes only the work-tracking bookkeeping.
    """
    if older_than_days <= 0:
        return 0
    cutoff = _retention_cutoff_iso(older_than_days)
    placeholders = ",".join("?" * len(TERMINAL_STATUSES))
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            f"DELETE FROM jobs WHERE status IN ({placeholders}) "
            "AND finished_at IS NOT NULL AND finished_at < ?",
            (*TERMINAL_STATUSES, cutoff),
        )
        return cur.rowcount


def cancel_active_for(db: "CrawlDB", *, payload_key: str, value: int) -> int:
    """Cancel in-flight jobs whose ``payload[payload_key]`` equals ``value``.

    Used when a recipe is deleted: its in-flight firings (``pending`` /
    ``running`` / ``paused``) are cancelled, while terminal firings survive as
    history. Matches on the JSON payload via SQLite ``json_extract``.
    """
    now = _now()
    placeholders = ",".join("?" * len(ACTIVE_STATUSES))
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            f"""UPDATE jobs
                   SET status='cancelled', finished_at=?
                 WHERE status IN ({placeholders})
                   AND json_extract(payload, ?) = ?""",
            (now, *ACTIVE_STATUSES, f"$.{payload_key}", int(value)),
        )
        return cur.rowcount


# --- reads ------------------------------------------------------------------


def get_job(db: "CrawlDB", job_id: int) -> dict[str, Any] | None:
    with db.read() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (int(job_id),)).fetchone()
    return _row_to_dict(row) if row is not None else None


def list_jobs(
    db: "CrawlDB",
    *,
    kind: str | None = None,
    status: str | None = None,
    target_type: str | None = None,
    since: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List jobs newest-first, with optional filters.

    ``since`` filters on ``created_at >= since`` (ISO timestamp). ``limit`` is
    clamped to a sane ceiling so the Activity tab can't pull an unbounded set.
    """
    where: list[str] = []
    params: list[Any] = []
    if kind:
        where.append("kind=?")
        params.append(kind)
    if status:
        where.append("status=?")
        params.append(status)
    if target_type:
        where.append("target_type=?")
        params.append(target_type)
    if since:
        where.append("created_at >= ?")
        params.append(since)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    params.append(max(1, min(int(limit), 1000)))
    with db.read() as c:
        rows = c.execute(
            f"SELECT * FROM jobs{clause} ORDER BY id DESC LIMIT ?", params
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def counts_by_status(db: "CrawlDB") -> dict[str, int]:
    """Aggregate job counts per status (Activity summary / Inventory)."""
    with db.read() as c:
        rows = c.execute(
            "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status"
        ).fetchall()
    return {r["status"]: int(r["n"]) for r in rows}


def active_crawl_urls(db: "CrawlDB") -> set[str]:
    """URLs that already have a non-terminal (``pending``/``running``/
    ``paused``) crawl job, read from each job's ``payload.url``.

    The batch-intake "Run" and the crawl-queue enqueue both dedupe against
    in-flight crawl work; pulling the set once is cheaper than an
    ``_active_crawl_job_for_url`` scan per URL when spawning a whole batch.
    """
    urls: set[str] = set()
    for job in list_jobs(db, kind="crawl", limit=1000):
        if job["status"] in ACTIVE_STATUSES:
            payload = job.get("payload") or {}
            url = payload.get("url")
            if isinstance(url, str):
                urls.add(url)
    return urls


__all__ = [
    "ACTIVE_STATUSES",
    "KINDS",
    "STATUSES",
    "TARGET_TYPES",
    "TERMINAL_STATUSES",
    "active_crawl_urls",
    "cancel_active_for",
    "claim_next_crawl",
    "count_prunable_terminal_jobs",
    "counts_by_status",
    "create_job",
    "delete_job",
    "prune_terminal_jobs",
    "get_job",
    "list_jobs",
    "set_status",
    "update_payload",
]
