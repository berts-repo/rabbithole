"""Domain profile queries.

PLAN.md:324. ``touch_domain`` is the crawler's per-fetch upsert (shipped
in B5). B7 adds the read profile (page count, flag count, entities,
activity sparkline), pages list, and alias rename.

Counts are computed at query time via JOIN — the schema deliberately stores
neither ``page_count`` nor ``flag_count`` on the ``domains`` row.
"""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

from . import findings as findings_db
from . import graph_filters as graph_filters_db
from . import labels as labels_db
from .flags import ACTIVE_STATUSES

# Comma-separated ``?`` placeholders for the active-flag-status IN-list.
_ACTIVE_FLAG_PLACEHOLDERS = ",".join("?" * len(ACTIVE_STATUSES))

if TYPE_CHECKING:
    from .core import CrawlDB


ALIAS_MAX = 64
PAGE_LIST_DEFAULT_LIMIT = 200


def touch_domain(db: "CrawlDB", host: str, when: str) -> None:
    """Upsert ``(host, last_seen=when)``. Leaves ``alias`` untouched."""
    if not host:
        return
    with db.transaction(immediate=True) as c:
        c.execute(
            """INSERT INTO domains(host, last_seen) VALUES (?, ?)
               ON CONFLICT(host) DO UPDATE SET last_seen=excluded.last_seen""",
            (host, when),
        )


def list_domains(db: "CrawlDB") -> list[dict[str, Any]]:
    """``[{host, alias, page_count, fail_count, flag_count}, ...]`` by page count desc."""
    with db.read() as c:
        rows = c.execute(
            f"""SELECT d.host, d.alias, d.last_seen,
                      (SELECT COUNT(*) FROM resources r
                       WHERE r.host = d.host AND r.state = 'crawled') AS page_count,
                      (SELECT COUNT(*) FROM resources r
                       JOIN pages p ON p.resource_id = r.id
                       JOIN page_versions pv ON pv.id = p.current_version_id
                       WHERE r.host = d.host
                         AND r.state = 'crawled'
                         AND pv.http_status IS NOT NULL
                         AND pv.http_status >= 400) AS fail_count,
                      (SELECT COUNT(*) FROM flags f
                       JOIN resources r2 ON r2.id = f.node_id
                       WHERE r2.host = d.host
                         AND f.status IN ({_ACTIVE_FLAG_PLACEHOLDERS})) AS flag_count
               FROM domains d
               ORDER BY page_count DESC, d.host""",
            ACTIVE_STATUSES,
        ).fetchall()
    return [
        {
            "host": r["host"],
            "alias": r["alias"],
            "last_seen": r["last_seen"],
            "page_count": int(r["page_count"]),
            "fail_count": int(r["fail_count"]),
            "flag_count": int(r["flag_count"]),
        }
        for r in rows
    ]


def _domain_row(db: "CrawlDB", host: str) -> sqlite3.Row | None:
    with db.read() as c:
        return c.execute(
            "SELECT host, alias, last_seen FROM domains WHERE host = ?",
            (host,),
        ).fetchone()


def get_profile(db: "CrawlDB", host: str) -> dict[str, Any] | None:
    """Full Domain tab profile (right-pane.md:294)."""
    domain_row = _domain_row(db, host)
    if domain_row is None:
        return None
    with db.read() as c:
        page_count = int(
            c.execute(
                "SELECT COUNT(*) AS n FROM resources "
                "WHERE host = ? AND state = 'crawled'",
                (host,),
            ).fetchone()["n"]
        )
        flag_count = int(
            c.execute(
                f"""SELECT COUNT(*) AS n FROM flags f
                    JOIN resources r ON r.id = f.node_id
                    WHERE r.host = ?
                      AND f.status IN ({_ACTIVE_FLAG_PLACEHOLDERS})""",
                (host, *ACTIVE_STATUSES),
            ).fetchone()["n"]
        )
        # ``monitors.last_status`` is gone — read the latest probe status_code
        # for whichever monitor watches this host.
        last_status_row = c.execute(
            """SELECT p.status_code FROM probes p
               JOIN monitors m ON m.id = p.monitor_id
               WHERE lower(m.url) LIKE 'http://' || ? || '%'
                  OR lower(m.url) LIKE 'https://' || ? || '%'
                  OR lower(m.url) LIKE ? || '%'
               ORDER BY p.checked_at DESC LIMIT 1""",
            (host.lower(), host.lower(), host.lower()),
        ).fetchone()
        last_status = (
            int(last_status_row["status_code"])
            if last_status_row is not None
            and last_status_row["status_code"] is not None
            else None
        )
    return {
        "host": host,
        "alias": domain_row["alias"],
        "last_seen": domain_row["last_seen"],
        "page_count": page_count,
        "flag_count": flag_count,
        "entity_count": findings_db.entity_count_for_domain(db, host),
        "last_status": last_status,
        "activity": activity_buckets(db, host),
        "entity_types": findings_db.entity_type_breakdown(db, host),
        # Labels attached to this domain (item 11), ids only — resolved to
        # name/color by the frontend catalog store.
        "label_ids": labels_db.domain_label_ids(db, host),
    }


def list_pages(
    db: "CrawlDB",
    host: str,
    *,
    limit: int = PAGE_LIST_DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Up to ``limit`` crawled pages for ``host``. Filtered resources excluded."""
    excluded = graph_filters_db.excluded_node_ids(db)
    with db.read() as c:
        rows = c.execute(
            """SELECT r.id, r.url, pv.title, pv.http_status AS status_code
               FROM resources r
               LEFT JOIN pages p ON p.resource_id = r.id
               LEFT JOIN page_versions pv ON pv.id = p.current_version_id
               WHERE r.host = ? AND r.state = 'crawled'
               ORDER BY r.first_seen DESC, r.id DESC
               LIMIT ?""",
            (host, limit + len(excluded) + 1),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        if int(r["id"]) in excluded:
            continue
        if len(out) >= limit:
            break
        out.append(
            {
                "id": int(r["id"]),
                "url": r["url"],
                "title": r["title"],
                "status_code": r["status_code"],
            }
        )
    return out


def activity_buckets(db: "CrawlDB", host: str) -> list[dict[str, Any]]:
    """Pages per day for the domain — bucketed by ``date(first_seen)``."""
    with db.read() as c:
        rows = c.execute(
            """SELECT date(first_seen) AS date, COUNT(*) AS count
               FROM resources
               WHERE host = ? AND state = 'crawled' AND first_seen IS NOT NULL
               GROUP BY date(first_seen)
               ORDER BY date""",
            (host,),
        ).fetchall()
    return [
        {"date": r["date"], "count": int(r["count"])}
        for r in rows
        if r["date"]
    ]


def list_snapshot_dates(db: "CrawlDB", host: str) -> list[str]:
    """Distinct UTC dates (``YYYY-MM-DD``) the host has any page version.

    Newest first. These are the snapshot boundaries the comparison picker
    offers — "the domain as crawled on this date". ``fetched_at`` is ISO-8601
    UTC, so ``substr(...,1,10)`` is the date and lexicographic order is
    chronological.
    """
    with db.read() as c:
        rows = c.execute(
            """SELECT DISTINCT substr(pv.fetched_at, 1, 10) AS d
                 FROM resources r
                 JOIN pages p ON p.resource_id = r.id
                 JOIN page_versions pv ON pv.page_id = p.id
                WHERE r.host = ? AND pv.fetched_at IS NOT NULL
                ORDER BY d DESC""",
            (host,),
        ).fetchall()
    return [r["d"] for r in rows if r["d"]]


def compare_snapshots(
    db: "CrawlDB", host: str, date_a: str, date_b: str
) -> dict[str, Any]:
    """Compare the host's pages between two as-of dates.

    "As of date D" = each page's latest version whose ``date(fetched_at) <= D``.
    Per page, classify the move from A→B:

    - **added** — no version as of A, has one as of B (page first appeared).
    - **removed** — had a version as of A, none as of B (only when A is after
      B; versions never disappear forward in time).
    - **drifted** — versions on both sides with differing ``body_hash``.
    - **identical** — versions on both sides with equal ``body_hash``.

    Returns the four counts plus a ``pages`` list of the *changed* rows
    (added / removed / drifted; identical pages are counted only). Each row
    carries both side version ids so the UI can deep-link a drifted page into
    the two-version diff. Filtered resources are excluded, mirroring
    :func:`list_pages`.
    """
    # Order the dates so A is the earlier boundary; report back in that order.
    if date_a > date_b:
        date_a, date_b = date_b, date_a
    excluded = graph_filters_db.excluded_node_ids(db)
    with db.read() as c:
        rows = c.execute(
            """SELECT r.id AS resource_id, r.url AS url, p.id AS page_id,
                      pv.id AS version_id, pv.body_hash AS body_hash,
                      pv.http_status AS http_status,
                      substr(pv.fetched_at, 1, 10) AS d
                 FROM resources r
                 JOIN pages p ON p.resource_id = r.id
                 JOIN page_versions pv ON pv.page_id = p.id
                WHERE r.host = ? AND pv.fetched_at IS NOT NULL
                ORDER BY p.id, pv.fetched_at, pv.id""",
            (host,),
        ).fetchall()

    # Fold the ordered version stream into per-page "as of A" / "as of B"
    # picks — the last row with date <= the boundary wins for each side.
    pages: dict[int, dict[str, Any]] = {}
    for r in rows:
        rid = int(r["resource_id"])
        if rid in excluded:
            continue
        entry = pages.setdefault(
            rid, {"url": r["url"], "a": None, "b": None}
        )
        side = {
            "version_id": int(r["version_id"]),
            "body_hash": r["body_hash"],
            "http_status": r["http_status"],
        }
        if r["d"] <= date_a:
            entry["a"] = side
        if r["d"] <= date_b:
            entry["b"] = side

    counts = {"added": 0, "removed": 0, "drifted": 0, "identical": 0}
    changed: list[dict[str, Any]] = []
    for rid, entry in pages.items():
        a, b = entry["a"], entry["b"]
        if a is None and b is None:
            continue
        if a is None:
            status = "added"
        elif b is None:
            status = "removed"
        elif a["body_hash"] == b["body_hash"]:
            status = "identical"
        else:
            status = "drifted"
        counts[status] += 1
        if status != "identical":
            changed.append(
                {
                    "resource_id": rid,
                    "url": entry["url"],
                    "status": status,
                    "a_version_id": a["version_id"] if a else None,
                    "b_version_id": b["version_id"] if b else None,
                    "http_status": (b or a)["http_status"],
                }
            )

    # Drifted first (the analyst's focus), then added, then removed.
    order = {"drifted": 0, "added": 1, "removed": 2}
    changed.sort(key=lambda p: (order[p["status"]], p["url"]))
    return {"a": date_a, "b": date_b, **counts, "pages": changed}


def rename_alias(
    db: "CrawlDB", host: str, alias: str | None
) -> dict[str, Any] | None:
    """Set or clear the alias.

    Returns the updated ``{host, alias}`` dict, or ``None`` if ``host`` is
    unknown. Whitespace-only alias is stored as NULL. Raises
    ``ValueError('duplicate_alias')`` if another host already owns the alias.
    """
    cleaned: str | None
    if alias is None:
        cleaned = None
    else:
        stripped = alias.strip()
        if not stripped:
            cleaned = None
        else:
            if len(stripped) > ALIAS_MAX:
                raise ValueError("alias_too_long")
            cleaned = stripped

    with db.transaction(immediate=True) as c:
        existing = c.execute(
            "SELECT host FROM domains WHERE host = ?", (host,)
        ).fetchone()
        if existing is None:
            return None
        if cleaned is not None:
            clash = c.execute(
                "SELECT host FROM domains "
                "WHERE alias = ? AND host != ?",
                (cleaned, host),
            ).fetchone()
            if clash is not None:
                raise ValueError("duplicate_alias")
        c.execute(
            "UPDATE domains SET alias = ? WHERE host = ?",
            (cleaned, host),
        )
    return {"host": host, "alias": cleaned}


__all__ = [
    "ALIAS_MAX",
    "PAGE_LIST_DEFAULT_LIMIT",
    "activity_buckets",
    "get_profile",
    "list_domains",
    "list_pages",
    "rename_alias",
    "touch_domain",
]
