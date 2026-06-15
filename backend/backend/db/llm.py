"""Analysis detail layer over the unified ``jobs`` table.

The schema reset dropped the per-row ``status`` column from ``analyses`` and
``collection_analyses``: work-status now lives on a linked ``jobs`` row
(``kind='analysis'``), exactly as it does for crawls. Each typed row is durable
detail (``analysis_type`` / ``model`` / ``result`` / ``question`` /
``priority``); its 1:1 job row carries the unified status vocabulary
(``pending`` / ``running`` / ``done`` / ``failed`` / ``cancelled`` /
``paused``) and back-references the typed row through ``payload`` — so the two
can never drift:

* per-resource analyses → ``target_type='url'``, ``target_id`` = the
  ``resources.id``, ``payload.analysis_id`` = the ``analyses.id``;
* collection synthesis  → ``target_type='collection'``, ``target_id`` = the
  ``collections.id``, ``payload.collection_analysis_id`` = the
  ``collection_analyses.id``.

The LLM worker drives this: ``claim_next_batch`` per tick (5 jobs, priority
order) and ``claim_next_collection`` (one synthesis job), then ``mark_done`` /
``mark_failed_back_to_pending`` per job. The analyst-facing routes layer on
top: enqueue, list, set priority, cancel, re-run, delete.

There is no ``waiting`` state any more — the old stub-promotion split is gone.
Auto-enqueue fires only after a page is crawled, and a manual analysis against
a not-yet-crawled resource is simply claimed and dropped (``no_content``).
Crash recovery is the single boot sweep in ``core.py`` (running → failed); this
module no longer reconciles mid-flight rows itself.

Every mutation runs inside ``db.transaction(immediate=True)``; the typed-table
write and the linked-job transition compose in one (reentrant) transaction so
they commit together. Status validation is the schema's CHECK constraint on
``jobs.status``; the FK on ``analyses.resource_id`` surfaces as ``ValueError``
so callers don't have to know about ``sqlite3``.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from . import jobs as jobs_db

if TYPE_CHECKING:
    from .core import CrawlDB


# Lower-bound limit on claimed batches. PLAN.md key constants: "LLM worker
# batch size: 5 jobs". Keeping the default here lets tests override.
DEFAULT_BATCH_SIZE = 5

# Job statuses that mean "this analysis is still in the queue / not finished".
_ACTIVE_STATUSES = jobs_db.ACTIVE_STATUSES  # pending, running, paused


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _job_for_analysis(c: sqlite3.Cursor, analysis_id: int) -> sqlite3.Row | None:
    """The per-resource analysis job linked to ``analysis_id`` (1:1)."""
    return c.execute(
        "SELECT id, status FROM jobs "
        "WHERE kind='analysis' AND target_type='url' "
        "  AND json_extract(payload, '$.analysis_id') = ? "
        "ORDER BY id DESC LIMIT 1",
        (analysis_id,),
    ).fetchone()


def _collection_job_for_analysis(
    c: sqlite3.Cursor, analysis_id: int
) -> sqlite3.Row | None:
    """The collection-synthesis job linked to ``analysis_id`` (1:1)."""
    return c.execute(
        "SELECT id, status FROM jobs "
        "WHERE kind='analysis' AND target_type='collection' "
        "  AND json_extract(payload, '$.collection_analysis_id') = ? "
        "ORDER BY id DESC LIMIT 1",
        (analysis_id,),
    ).fetchone()


# --- analyses (per-resource) -----------------------------------------------


def enqueue(
    db: "CrawlDB",
    *,
    resource_id: int,
    analysis_type: str,
    model: str,
    priority: int = 0,
    question: str | None = None,
) -> int:
    """Insert an ``analyses`` detail row + its pending job. Returns the analysis id.

    The two writes share one transaction so a job never exists without its
    detail row (or vice versa). A bad ``resource_id`` (no such resource) trips
    the FK and surfaces as ``ValueError``.
    """
    when = _now_iso()
    with db.transaction(immediate=True) as c:
        try:
            cur = c.execute(
                """INSERT INTO analyses(
                    resource_id, analysis_type, model, question, priority,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (resource_id, analysis_type, model, question, priority, when, when),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(str(exc)) from exc
        analysis_id = int(cur.lastrowid)
        jobs_db.create_job(
            db,
            kind="analysis",
            target_type="url",
            target_id=resource_id,
            status="pending",
            payload={"analysis_id": analysis_id, "analysis_type": analysis_type},
        )
    return analysis_id


def get(db: "CrawlDB", analysis_id: int) -> dict[str, Any] | None:
    """Analysis detail merged with its linked job ``status`` + ``job_id``."""
    with db.read() as c:
        row = c.execute(
            "SELECT * FROM analyses WHERE id = ?", (analysis_id,)
        ).fetchone()
        if row is None:
            return None
        job = _job_for_analysis(c, analysis_id)
    data = {k: row[k] for k in row.keys()}
    data["status"] = job["status"] if job is not None else None
    data["job_id"] = int(job["id"]) if job is not None else None
    return data


def list_queue(
    db: "CrawlDB",
    *,
    status: str | tuple[str, ...] | None = None,
    resource_id: int | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Analyses joined to their jobs. Filter on job status and/or resource id.

    Ordered by priority desc, created asc. Each row carries the typed detail
    plus ``status`` (the job's) and ``job_id``.
    """
    clauses = ["j.kind = 'analysis'", "j.target_type = 'url'"]
    args: list[Any] = []
    if status is not None:
        if isinstance(status, str):
            clauses.append("j.status = ?")
            args.append(status)
        else:
            placeholders = ",".join("?" for _ in status)
            clauses.append(f"j.status IN ({placeholders})")
            args.extend(status)
    if resource_id is not None:
        clauses.append("a.resource_id = ?")
        args.append(resource_id)
    where = " AND ".join(clauses)
    sql = (
        f"SELECT a.*, j.status AS status, j.id AS job_id "
        f"  FROM jobs j "
        f"  JOIN analyses a ON a.id = json_extract(j.payload, '$.analysis_id') "
        f" WHERE {where} "
        f" ORDER BY a.priority DESC, a.created_at ASC, a.id ASC "
        f" LIMIT ?"
    )
    args.append(limit)
    with db.read() as c:
        rows = c.execute(sql, args).fetchall()
    return [{k: r[k] for k in r.keys()} for r in rows]


def resources_with_active_analysis(
    db: "CrawlDB", *, analysis_type: str, resource_ids: list[int]
) -> set[int]:
    """Subset of ``resource_ids`` with a non-terminal analysis job of ``analysis_type``.

    "Non-terminal" = the linked job is ``pending`` / ``running`` / ``paused``.
    Used by the batch-analysis route's ``skip_existing`` so a resource already
    queued for this type isn't enqueued twice.
    """
    ids = [int(n) for n in resource_ids]
    if not ids:
        return set()
    id_ph = ",".join("?" for _ in ids)
    active_ph = ",".join("?" for _ in _ACTIVE_STATUSES)
    with db.read() as c:
        rows = c.execute(
            f"""SELECT DISTINCT a.resource_id
                  FROM jobs j
                  JOIN analyses a ON a.id = json_extract(j.payload, '$.analysis_id')
                 WHERE j.kind = 'analysis' AND j.target_type = 'url'
                   AND j.status IN ({active_ph})
                   AND a.analysis_type = ?
                   AND a.resource_id IN ({id_ph})""",
            [*_ACTIVE_STATUSES, analysis_type, *ids],
        ).fetchall()
    return {int(r["resource_id"]) for r in rows}


def claim_next_batch(
    db: "CrawlDB",
    *,
    model: str,
    limit: int = DEFAULT_BATCH_SIZE,
) -> list[dict[str, Any]]:
    """Atomically transition up to ``limit`` pending analysis jobs to ``running``.

    Ordered by ``(analyses.priority DESC, analyses.created_at ASC, jobs.id ASC)``.
    Returns the claimed work — ``job_id`` / ``analysis_id`` / ``resource_id`` /
    ``analysis_type`` / ``model`` / ``question`` — in execution order. Empty
    list when there is nothing pending.
    """
    with db.transaction(immediate=True) as c:
        rows = c.execute(
            """SELECT j.id AS job_id, a.id AS analysis_id, a.resource_id,
                      a.analysis_type, a.model, a.question
                 FROM jobs j
                 JOIN analyses a ON a.id = json_extract(j.payload, '$.analysis_id')
                WHERE j.kind = 'analysis' AND j.target_type = 'url'
                  AND j.status = 'pending'
                ORDER BY a.priority DESC, a.created_at ASC, j.id ASC
                LIMIT ?""",
            (limit,),
        ).fetchall()
        if not rows:
            return []
        when = _now_iso()
        claimed: list[dict[str, Any]] = []
        for r in rows:
            c.execute(
                "UPDATE jobs SET status='running', "
                "started_at=COALESCE(started_at, ?) WHERE id = ?",
                (when, int(r["job_id"])),
            )
            c.execute(
                "UPDATE analyses SET updated_at=? WHERE id = ?",
                (when, int(r["analysis_id"])),
            )
            claimed.append(
                {
                    "job_id": int(r["job_id"]),
                    "analysis_id": int(r["analysis_id"]),
                    "resource_id": int(r["resource_id"]),
                    "analysis_type": r["analysis_type"],
                    "model": r["model"],
                    "question": r["question"],
                }
            )
    return claimed


def mark_done(
    db: "CrawlDB", *, job_id: int, analysis_id: int, result_text: str | None
) -> bool:
    """Write the result to ``analyses`` and flip the job to ``done`` (atomic)."""
    when = _now_iso()
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "UPDATE analyses SET result=?, updated_at=? WHERE id = ?",
            (result_text, when, analysis_id),
        )
        jobs_db.set_status(db, job_id, "done")
        return cur.rowcount > 0


def mark_failed_back_to_pending(db: "CrawlDB", job_id: int) -> bool:
    """Send a transient-failed running job back to ``pending`` for a retry tick."""
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "UPDATE jobs SET status='pending' WHERE id = ? AND status = 'running'",
            (job_id,),
        )
        return cur.rowcount > 0


def set_priority(db: "CrawlDB", analysis_id: int, priority: int) -> bool:
    when = _now_iso()
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "UPDATE analyses SET priority=?, updated_at=? WHERE id = ?",
            (priority, when, analysis_id),
        )
        return cur.rowcount > 0


def cancel(db: "CrawlDB", analysis_id: int) -> bool:
    """Delete a non-running analysis and its job. Running jobs are left alone."""
    with db.transaction(immediate=True) as c:
        job = _job_for_analysis(c, analysis_id)
        if job is not None and job["status"] == "running":
            return False
        if job is not None:
            c.execute("DELETE FROM jobs WHERE id = ?", (int(job["id"]),))
        cur = c.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
        return cur.rowcount > 0


def cancel_running(db: "CrawlDB", analysis_id: int) -> bool:
    """Force-delete an analysis and its job even when running (analyst's ✕)."""
    with db.transaction(immediate=True) as c:
        job = _job_for_analysis(c, analysis_id)
        if job is not None:
            c.execute("DELETE FROM jobs WHERE id = ?", (int(job["id"]),))
        cur = c.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
        return cur.rowcount > 0


def rerun(db: "CrawlDB", analysis_id: int) -> bool:
    """Reset a terminal analysis to re-run: clear the result, re-pend the job."""
    when = _now_iso()
    with db.transaction(immediate=True) as c:
        job = _job_for_analysis(c, analysis_id)
        if job is None or job["status"] not in jobs_db.TERMINAL_STATUSES:
            return False
        c.execute(
            "UPDATE jobs SET status='pending', result=NULL, error=NULL, "
            "started_at=NULL, finished_at=NULL WHERE id = ?",
            (int(job["id"]),),
        )
        cur = c.execute(
            "UPDATE analyses SET result=NULL, updated_at=? WHERE id = ?",
            (when, analysis_id),
        )
        return cur.rowcount > 0


def queue_counts(db: "CrawlDB") -> dict[str, int]:
    """``{job-status: count}`` over per-resource analysis jobs (zeros included)."""
    counts = {s: 0 for s in jobs_db.STATUSES}
    with db.read() as c:
        rows = c.execute(
            "SELECT status, COUNT(*) AS n FROM jobs "
            "WHERE kind='analysis' AND target_type='url' GROUP BY status"
        ).fetchall()
    for r in rows:
        counts[str(r["status"])] = int(r["n"])
    return counts


def list_analyzed_nodes(
    db: "CrawlDB",
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Nodes with at least one *successful* completed per-resource analysis.

    One row per resource (``node_id``), newest-analyzed first, carrying the
    node's ``url``/``title``/``state`` plus the distinct ``analysis_types`` that
    landed and the most recent ``last_analyzed`` (``jobs.finished_at``). Mirrors
    the ``list_queue`` join (``json_extract(payload, '$.analysis_id')``), then
    joins ``resources`` for identity and ``pages``→``page_versions`` for the
    current title (same chain as ``pages.get_page_detail``).

    Dropped jobs are excluded: the worker still marks a job ``done`` when output
    is unusable, writing a ``<dropped:...>`` sentinel into ``analyses.result``
    (no_content / ollama_unreachable / invalid_output). A node whose every
    analysis was dropped isn't usefully "analyzed", so those rows don't count.

    ``analysis_types`` comes back as a comma-joined string — the route splits it
    into a list. ``GROUP_CONCAT(DISTINCT …)`` must be the single-argument form
    (a custom separator is a SQLite error with ``DISTINCT``); the default comma
    is safe because analysis-type names contain no commas.
    """
    sql = """
        SELECT a.resource_id            AS node_id,
               r.url                    AS url,
               pv.title                 AS title,
               r.state                  AS state,
               GROUP_CONCAT(DISTINCT a.analysis_type) AS analysis_types,
               MAX(j.finished_at)       AS last_analyzed
          FROM jobs j
          JOIN analyses a       ON a.id = json_extract(j.payload, '$.analysis_id')
          JOIN resources r      ON r.id = a.resource_id
          LEFT JOIN pages p     ON p.resource_id = r.id
          LEFT JOIN page_versions pv ON pv.id = p.current_version_id
         WHERE j.kind = 'analysis' AND j.target_type = 'url'
           AND j.status = 'done'
           AND a.result IS NOT NULL AND a.result NOT LIKE '<dropped:%'
         GROUP BY a.resource_id
         ORDER BY MAX(j.finished_at) DESC
         LIMIT ?
    """
    with db.read() as c:
        rows = c.execute(sql, (limit,)).fetchall()
    return [{k: r[k] for k in r.keys()} for r in rows]


# --- collection_analyses (synthesis) ---------------------------------------


def enqueue_collection(
    db: "CrawlDB",
    *,
    collection_id: int,
    analysis_type: str,
    model: str,
) -> int:
    """Insert a ``collection_analyses`` detail row + its pending job. Returns id."""
    when = _now_iso()
    with db.transaction(immediate=True) as c:
        try:
            cur = c.execute(
                """INSERT INTO collection_analyses(
                    collection_id, analysis_type, model, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)""",
                (collection_id, analysis_type, model, when, when),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(str(exc)) from exc
        analysis_id = int(cur.lastrowid)
        jobs_db.create_job(
            db,
            kind="analysis",
            target_type="collection",
            target_id=collection_id,
            status="pending",
            payload={
                "collection_analysis_id": analysis_id,
                "analysis_type": analysis_type,
            },
        )
    return analysis_id


def get_collection_analysis(
    db: "CrawlDB", analysis_id: int
) -> dict[str, Any] | None:
    with db.read() as c:
        row = c.execute(
            "SELECT * FROM collection_analyses WHERE id = ?", (analysis_id,)
        ).fetchone()
        if row is None:
            return None
        job = _collection_job_for_analysis(c, analysis_id)
    data = {k: row[k] for k in row.keys()}
    data["status"] = job["status"] if job is not None else None
    data["job_id"] = int(job["id"]) if job is not None else None
    return data


def list_collection_analyses(
    db: "CrawlDB", collection_id: int
) -> list[dict[str, Any]]:
    """Synthesis rows for a collection, newest first, with linked job status."""
    with db.read() as c:
        rows = c.execute(
            """SELECT ca.*, j.status AS status, j.id AS job_id
                 FROM collection_analyses ca
                 LEFT JOIN jobs j
                   ON j.kind = 'analysis' AND j.target_type = 'collection'
                  AND json_extract(j.payload, '$.collection_analysis_id') = ca.id
                WHERE ca.collection_id = ?
                ORDER BY ca.created_at DESC, ca.id DESC""",
            (collection_id,),
        ).fetchall()
    return [{k: r[k] for k in r.keys()} for r in rows]


def claim_next_collection(
    db: "CrawlDB", *, model: str
) -> dict[str, Any] | None:
    """Atomically claim one pending collection-synthesis job → ``running``."""
    with db.transaction(immediate=True) as c:
        row = c.execute(
            """SELECT j.id AS job_id, ca.id AS analysis_id, ca.collection_id,
                      ca.analysis_type, ca.model
                 FROM jobs j
                 JOIN collection_analyses ca
                   ON ca.id = json_extract(j.payload, '$.collection_analysis_id')
                WHERE j.kind = 'analysis' AND j.target_type = 'collection'
                  AND j.status = 'pending'
                ORDER BY ca.created_at ASC, j.id ASC
                LIMIT 1"""
        ).fetchone()
        if row is None:
            return None
        when = _now_iso()
        c.execute(
            "UPDATE jobs SET status='running', "
            "started_at=COALESCE(started_at, ?) WHERE id = ?",
            (when, int(row["job_id"])),
        )
        c.execute(
            "UPDATE collection_analyses SET updated_at=? WHERE id = ?",
            (when, int(row["analysis_id"])),
        )
        return {
            "job_id": int(row["job_id"]),
            "analysis_id": int(row["analysis_id"]),
            "collection_id": int(row["collection_id"]),
            "analysis_type": row["analysis_type"],
            "model": row["model"],
        }


def mark_collection_done(
    db: "CrawlDB", *, job_id: int, analysis_id: int, result_text: str | None
) -> bool:
    when = _now_iso()
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "UPDATE collection_analyses SET result=?, updated_at=? WHERE id = ?",
            (result_text, when, analysis_id),
        )
        jobs_db.set_status(db, job_id, "done")
        return cur.rowcount > 0


def mark_collection_failed_back_to_pending(db: "CrawlDB", job_id: int) -> bool:
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "UPDATE jobs SET status='pending' WHERE id = ? AND status = 'running'",
            (job_id,),
        )
        return cur.rowcount > 0


# --- cluster_analyses (item 7, decision D1) --------------------------------
#
# Clusters drift across layout/algorithm runs, so the durable key is a cluster
# *fingerprint* — the sorted set of member resource_ids hashed — not a numeric
# cluster id. A re-clustered group with the same membership re-attaches its
# analyses automatically; a changed membership orphans the old rows as
# queryable history (still fetchable by id, no longer surfaced on a live
# cluster). Storage mirrors `analyses`; the linked job uses target_type
# 'cluster' with target_id = the cluster_analyses.id (a cluster has no single
# resource FK, so the row's own id is the stable job target).


def compute_fingerprint(resource_ids: list[int]) -> str:
    """Stable hex key for a cluster's membership (sorted ids → SHA-256, 16 hex)."""
    import hashlib

    uniq = sorted({int(r) for r in resource_ids})
    joined = ",".join(str(r) for r in uniq)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def _cluster_job_for_analysis(
    c: sqlite3.Cursor, analysis_id: int
) -> sqlite3.Row | None:
    return c.execute(
        "SELECT id, status FROM jobs "
        "WHERE kind='analysis' AND target_type='cluster' "
        "  AND json_extract(payload, '$.cluster_analysis_id') = ? "
        "ORDER BY id DESC LIMIT 1",
        (analysis_id,),
    ).fetchone()


def enqueue_cluster(
    db: "CrawlDB",
    *,
    fingerprint: str,
    resource_ids: list[int],
    analysis_type: str,
    model: str,
    label: str | None = None,
    question: str | None = None,
    prompt_id: int | None = None,
    priority: int = 0,
) -> int:
    """Insert a ``cluster_analyses`` detail row + its pending job. Returns the id.

    ``resource_ids`` is the compose-time membership snapshot stored as a JSON
    array — the fingerprint is one-way, so the worker reads this list back to
    fetch each member's page body.
    """
    when = _now_iso()
    members = json.dumps(sorted({int(r) for r in resource_ids}))
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            """INSERT INTO cluster_analyses(
                fingerprint, resource_ids, label, analysis_type, model,
                question, prompt_id, priority, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (fingerprint, members, label, analysis_type, model, question,
             prompt_id, priority, when, when),
        )
        analysis_id = int(cur.lastrowid)
        jobs_db.create_job(
            db,
            kind="analysis",
            target_type="cluster",
            target_id=analysis_id,
            status="pending",
            payload={
                "cluster_analysis_id": analysis_id,
                "analysis_type": analysis_type,
            },
        )
    return analysis_id


def get_cluster_analysis(
    db: "CrawlDB", analysis_id: int
) -> dict[str, Any] | None:
    with db.read() as c:
        row = c.execute(
            "SELECT * FROM cluster_analyses WHERE id = ?", (analysis_id,)
        ).fetchone()
        if row is None:
            return None
        job = _cluster_job_for_analysis(c, analysis_id)
    data = {k: row[k] for k in row.keys()}
    data["status"] = job["status"] if job is not None else None
    data["job_id"] = int(job["id"]) if job is not None else None
    return data


def list_cluster_analyses(
    db: "CrawlDB", fingerprint: str
) -> list[dict[str, Any]]:
    """Cluster analyses for a fingerprint, newest first, with linked job status."""
    with db.read() as c:
        rows = c.execute(
            """SELECT ca.*, j.status AS status, j.id AS job_id
                 FROM cluster_analyses ca
                 LEFT JOIN jobs j
                   ON j.kind = 'analysis' AND j.target_type = 'cluster'
                  AND json_extract(j.payload, '$.cluster_analysis_id') = ca.id
                WHERE ca.fingerprint = ?
                ORDER BY ca.created_at DESC, ca.id DESC""",
            (fingerprint,),
        ).fetchall()
    return [{k: r[k] for k in r.keys()} for r in rows]


def claim_next_cluster(
    db: "CrawlDB", *, model: str
) -> dict[str, Any] | None:
    """Atomically claim one pending cluster-analysis job → ``running``."""
    with db.transaction(immediate=True) as c:
        row = c.execute(
            """SELECT j.id AS job_id, ca.id AS analysis_id, ca.fingerprint,
                      ca.resource_ids, ca.analysis_type, ca.model, ca.question
                 FROM jobs j
                 JOIN cluster_analyses ca
                   ON ca.id = json_extract(j.payload, '$.cluster_analysis_id')
                WHERE j.kind = 'analysis' AND j.target_type = 'cluster'
                  AND j.status = 'pending'
                ORDER BY ca.priority DESC, ca.created_at ASC, j.id ASC
                LIMIT 1"""
        ).fetchone()
        if row is None:
            return None
        when = _now_iso()
        c.execute(
            "UPDATE jobs SET status='running', "
            "started_at=COALESCE(started_at, ?) WHERE id = ?",
            (when, int(row["job_id"])),
        )
        c.execute(
            "UPDATE cluster_analyses SET updated_at=? WHERE id = ?",
            (when, int(row["analysis_id"])),
        )
        return {
            "job_id": int(row["job_id"]),
            "analysis_id": int(row["analysis_id"]),
            "fingerprint": row["fingerprint"],
            "resource_ids": [int(r) for r in json.loads(row["resource_ids"] or "[]")],
            "analysis_type": row["analysis_type"],
            "model": row["model"],
            "question": row["question"],
        }


def mark_cluster_done(
    db: "CrawlDB", *, job_id: int, analysis_id: int, result_text: str | None
) -> bool:
    when = _now_iso()
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "UPDATE cluster_analyses SET result=?, updated_at=? WHERE id = ?",
            (result_text, when, analysis_id),
        )
        jobs_db.set_status(db, job_id, "done")
        return cur.rowcount > 0


def mark_cluster_failed_back_to_pending(db: "CrawlDB", job_id: int) -> bool:
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "UPDATE jobs SET status='pending' WHERE id = ? AND status = 'running'",
            (job_id,),
        )
        return cur.rowcount > 0


def cancel_cluster(db: "CrawlDB", analysis_id: int) -> bool:
    """Delete a non-running cluster analysis and its job."""
    with db.transaction(immediate=True) as c:
        job = _cluster_job_for_analysis(c, analysis_id)
        if job is not None and job["status"] == "running":
            return False
        if job is not None:
            c.execute("DELETE FROM jobs WHERE id = ?", (int(job["id"]),))
        cur = c.execute(
            "DELETE FROM cluster_analyses WHERE id = ?", (analysis_id,)
        )
        return cur.rowcount > 0


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "cancel",
    "cancel_cluster",
    "claim_next_cluster",
    "compute_fingerprint",
    "enqueue_cluster",
    "get_cluster_analysis",
    "list_cluster_analyses",
    "mark_cluster_done",
    "mark_cluster_failed_back_to_pending",
    "cancel_running",
    "claim_next_batch",
    "claim_next_collection",
    "enqueue",
    "enqueue_collection",
    "get",
    "get_collection_analysis",
    "list_collection_analyses",
    "list_queue",
    "mark_collection_done",
    "mark_collection_failed_back_to_pending",
    "mark_done",
    "mark_failed_back_to_pending",
    "queue_counts",
    "resources_with_active_analysis",
    "rerun",
    "set_priority",
]
