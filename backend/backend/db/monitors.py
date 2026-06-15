"""Uptime monitors + probe history.

PLAN.md:319. Monitors track ``.onion`` URLs the analyst wants to keep an
eye on. The daemon (B7g) writes ``probes`` rows on interval — each paired
with a unified ``kind='probe'`` job for the Activity view; the routes here
are the analyst-facing CRUD path. The schema reset dropped
``monitors.last_status``: the latest status reads from the most recent
``probes`` row / linked job.

URL validation runs through :func:`security.net.validate_onion_url` so
clearnet targets are refused at create time.
"""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from . import jobs as jobs_db
from . import settings as settings_db
from ..security.net import EgressError

if TYPE_CHECKING:
    from .core import CrawlDB


LABEL_MAX = 256
MIN_INTERVAL_HOURS = 0.25
MIN_DOWNTIME_THRESHOLD_HOURS = 0.25

_MUTABLE_FIELDS: frozenset[str] = frozenset({
    "enabled",
    "label",
    "interval_hours",
    "alert_on_change",
    "alert_on_restore",
    "downtime_threshold_hours",
})


# Each monitor row carries its latest probe's outcome so the right-pane
# Monitors list can render status + content-change without a second query.
# (``monitors.last_status`` was dropped in the reset; it now reads from the
# most recent ``probes`` row.)
_MONITOR_SELECT = """
    SELECT m.*,
           lp.status_code     AS last_status,
           lp.content_changed AS last_content_changed,
           lp.checked_at      AS last_checked_at
      FROM monitors m
      LEFT JOIN probes lp
        ON lp.monitor_id = m.id
       AND lp.checked_at = (
           SELECT MAX(p2.checked_at) FROM probes p2 WHERE p2.monitor_id = m.id
       )
"""


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out: dict[str, Any] = {k: row[k] for k in row.keys()}
    for boolean_col in (
        "enabled",
        "alert_on_change",
        "alert_on_restore",
        "last_content_changed",
    ):
        if boolean_col in out and out[boolean_col] is not None:
            out[boolean_col] = bool(out[boolean_col])
    return out


def list_monitors(
    db: "CrawlDB", *, host: str | None = None
) -> list[dict[str, Any]]:
    if host is None:
        sql = f"{_MONITOR_SELECT} ORDER BY m.id DESC"
        params: tuple[Any, ...] = ()
    else:
        sql = (
            f"{_MONITOR_SELECT} "
            "WHERE lower(m.url) LIKE ? || '%' "
            "   OR lower(m.url) LIKE 'http://' || ? || '%' "
            "   OR lower(m.url) LIKE 'https://' || ? || '%' "
            "ORDER BY m.id DESC"
        )
        h = host.lower()
        params = (h, h, h)
    with db.read() as c:
        rows = c.execute(sql, params).fetchall()
    # Apply explicit host match on parsed URL (LIKE is just a prefilter).
    result: list[dict[str, Any]] = []
    for r in rows:
        data = _row_to_dict(r)
        if host is not None:
            parsed = urlparse(data["url"] or "")
            if parsed.hostname != host.lower():
                continue
        result.append(data)
    return result


def get_monitor(db: "CrawlDB", mid: int) -> dict[str, Any] | None:
    with db.read() as c:
        row = c.execute(
            f"{_MONITOR_SELECT} WHERE m.id = ?", (mid,)
        ).fetchone()
    return _row_to_dict(row)


def create_monitor(
    db: "CrawlDB",
    *,
    url: str,
    label: str | None,
    interval_hours: float,
    alert_on_change: bool = True,
    alert_on_restore: bool = True,
    downtime_threshold_hours: float = 48.0,
) -> int:
    try:
        canonical = settings_db.validate_intake_url(db, url)
    except EgressError as exc:
        raise ValueError("bad_url") from exc
    if interval_hours < MIN_INTERVAL_HOURS:
        raise ValueError("interval_too_short")
    if downtime_threshold_hours < MIN_DOWNTIME_THRESHOLD_HOURS:
        raise ValueError("downtime_threshold_too_short")
    cleaned_label = label.strip() if label is not None else None
    if cleaned_label is not None and len(cleaned_label) > LABEL_MAX:
        raise ValueError("label_too_long")
    try:
        with db.transaction(immediate=True) as c:
            cur = c.execute(
                """INSERT INTO monitors(
                       url, label, interval_hours,
                       enabled, alert_on_change, alert_on_restore,
                       downtime_threshold_hours
                   ) VALUES (?, ?, ?, 1, ?, ?, ?)""",
                (
                    canonical,
                    cleaned_label,
                    interval_hours,
                    1 if alert_on_change else 0,
                    1 if alert_on_restore else 0,
                    downtime_threshold_hours,
                ),
            )
            return int(cur.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise ValueError("duplicate_url") from exc


def update_monitor(
    db: "CrawlDB", mid: int, **fields: Any
) -> dict[str, Any] | None:
    unknown = set(fields) - _MUTABLE_FIELDS
    if unknown:
        raise ValueError("unknown_field")

    sets: list[str] = []
    params: list[Any] = []
    if "enabled" in fields:
        sets.append("enabled = ?")
        params.append(1 if fields["enabled"] else 0)
    if "label" in fields:
        label_val = fields["label"]
        if label_val is None:
            sets.append("label = NULL")
        else:
            cleaned = str(label_val).strip()
            if len(cleaned) > LABEL_MAX:
                raise ValueError("label_too_long")
            sets.append("label = ?")
            params.append(cleaned)
    if "interval_hours" in fields:
        interval = float(fields["interval_hours"])
        if interval < MIN_INTERVAL_HOURS:
            raise ValueError("interval_too_short")
        sets.append("interval_hours = ?")
        params.append(interval)
    if "alert_on_change" in fields:
        sets.append("alert_on_change = ?")
        params.append(1 if fields["alert_on_change"] else 0)
    if "alert_on_restore" in fields:
        sets.append("alert_on_restore = ?")
        params.append(1 if fields["alert_on_restore"] else 0)
    if "downtime_threshold_hours" in fields:
        threshold = float(fields["downtime_threshold_hours"])
        if threshold < MIN_DOWNTIME_THRESHOLD_HOURS:
            raise ValueError("downtime_threshold_too_short")
        sets.append("downtime_threshold_hours = ?")
        params.append(threshold)

    if not sets:
        return get_monitor(db, mid)
    params.append(mid)
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            f"UPDATE monitors SET {', '.join(sets)} WHERE id = ?", params
        )
        if cur.rowcount == 0:
            return None
        row = c.execute(
            "SELECT * FROM monitors WHERE id = ?", (mid,)
        ).fetchone()
    return _row_to_dict(row)


def delete_monitor(db: "CrawlDB", mid: int) -> bool:
    with db.transaction(immediate=True) as c:
        cur = c.execute("DELETE FROM monitors WHERE id = ?", (mid,))
        return cur.rowcount > 0


def record_probe(
    db: "CrawlDB",
    mid: int,
    *,
    url: str,
    checked_at: str,
    status_code: int | None,
    body_hash: str | None = None,
    content_changed: int | None = None,
) -> int:
    """Atomic insert of the probe row + its unified ``kind='probe'`` job.

    The schema reset dropped ``monitors.last_status`` — the latest status now
    reads from the most recent ``probes`` row (or the linked job). Each probe
    is also a unit of work in the Activity view, so we write one ``kind='probe'``
    job alongside the history row, both in one transaction so the two never
    drift. The probe completes synchronously, so the job is created already
    ``done``; ``status_code=None`` (target unreachable) is a normal *result*,
    not a job failure. ``payload`` carries the monitor id, url, and outcome
    (incl. ``content_changed``) so the Activity row can label and render it
    without a join.

    ``body_hash`` is the clean-text hash of the fetched body (when the monitor
    tracks content); ``content_changed`` is ``1``/``0`` vs the prior probe, or
    ``None`` when content wasn't tracked or there was no prior hash.

    Returns the new ``jobs.id``. ``checked_at`` should be ISO-8601 UTC.
    """
    with db.transaction(immediate=True) as c:
        c.execute(
            "INSERT INTO probes(monitor_id, checked_at, status_code, "
            "body_hash, content_changed) VALUES (?, ?, ?, ?, ?)",
            (mid, checked_at, status_code, body_hash, content_changed),
        )
        return jobs_db.create_job(
            db,
            kind="probe",
            target_type="url",
            target_id=mid,
            status="done",
            payload={
                "monitor_id": mid,
                "url": url,
                "status_code": status_code,
                "content_changed": (
                    bool(content_changed) if content_changed is not None else None
                ),
            },
        )


def latest_probe(db: "CrawlDB", mid: int) -> dict[str, Any] | None:
    """Most recent probe for a monitor — the daemon reads ``body_hash`` from
    here to compute the next probe's ``content_changed``."""
    with db.read() as c:
        row = c.execute(
            "SELECT checked_at, status_code, body_hash, content_changed "
            "FROM probes WHERE monitor_id = ? "
            "ORDER BY checked_at DESC LIMIT 1",
            (mid,),
        ).fetchone()
    if row is None:
        return None
    out: dict[str, Any] = {k: row[k] for k in row.keys()}
    if out.get("content_changed") is not None:
        out["content_changed"] = bool(out["content_changed"])
    return out


__all__ = [
    "LABEL_MAX",
    "MIN_DOWNTIME_THRESHOLD_HOURS",
    "MIN_INTERVAL_HOURS",
    "create_monitor",
    "delete_monitor",
    "get_monitor",
    "latest_probe",
    "list_monitors",
    "record_probe",
    "update_monitor",
]
