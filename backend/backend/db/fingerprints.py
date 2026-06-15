"""Header fingerprint clusters + the storage helper the crawler uses.

PLAN.md:321. Fingerprint clusters are computed on demand from the
``response_headers`` table — no derived index. The daemon was removed
during planning (the crawler already invalidates the graph cache).

This module is also the single ingress point for ``response_headers``
writes (used by ``db.page_versions.record_fetch`` /
``record_failed_fetch``). It enforces:

* Header name must match RFC 7230 token chars (``[!-9;-~]+``). Invalid
  names are dropped silently with a debug log; the rest of the page's
  headers persist.
* Header value capped at ``HEADER_VALUE_MAX`` bytes (UTF-8). Oversize
  values are truncated, not rejected.
"""
from __future__ import annotations

import csv as csv_module
import io
import logging
import math
import re
import sqlite3
from typing import TYPE_CHECKING, Any

from . import graph_filters as graph_filters_db

if TYPE_CHECKING:
    from .core import CrawlDB


log = logging.getLogger(__name__)


RFC7230_TOKEN_RE = re.compile(r"^[!-9;-~]+$")
HEADER_VALUE_MAX = 4096

# Headers that change per-response, leak session state, or are operational
# noise — never useful for clustering. Compared lowercase against the stored
# key. Mirrors ``db.graph._EPHEMERAL_HEADERS`` (kept aligned by hand — the
# two contexts can diverge: clustering tolerates more headers than the IDF
# infra-cluster pass cares about, but in practice they're the same set).
_EPHEMERAL: frozenset[str] = frozenset(
    name.lower()
    for name in (
        "Date",
        "Set-Cookie",
        "Cookie",
        "Expires",
        "Last-Modified",
        "ETag",
        "Content-Length",
        "Age",
        "Cache-Control",
        "Server-Timing",
        "Vary",
        "X-Request-Id",
        "X-Request-ID",
        "Request-Id",
        "CF-Ray",
    )
)

# Same formula-injection prefix list as ``export.csv`` — keep the two in
# sync if either ever grows.
_FORMULA_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r")


def validate_header_name(name: object) -> bool:
    return isinstance(name, str) and bool(RFC7230_TOKEN_RE.match(name))


def normalize_header_value(value: object) -> str:
    """Coerce to str and truncate at ``HEADER_VALUE_MAX`` UTF-8 bytes."""
    if value is None:
        return ""
    s = str(value)
    encoded = s.encode("utf-8", errors="replace")
    if len(encoded) <= HEADER_VALUE_MAX:
        return s
    truncated = encoded[:HEADER_VALUE_MAX]
    # Avoid splitting a multi-byte sequence at the boundary.
    return truncated.decode("utf-8", errors="ignore")


def insert_response_headers(
    db: "CrawlDB", page_version_id: int, headers: dict[str, object]
) -> int:
    """Replace the header set for one page version. Returns the count written.

    Headers are captured per fetch and stored against the ``page_versions``
    row they came from. The crawl-write path keeps only the current version's
    headers (a version advance deletes the prior version's rows in the same
    transaction; CASCADE also covers version deletion), so clustering always
    reads current-fetch headers.

    Per-row tolerance:
      * Invalid header name (fails RFC 7230 token check) → skipped + debug log.
      * Value larger than ``HEADER_VALUE_MAX`` bytes → truncated.

    The caller runs this inside the crawl-write transaction; it opens its own
    (reentrant) transaction so it can also be invoked standalone.
    """
    if not headers:
        with db.transaction(immediate=True) as c:
            c.execute(
                "DELETE FROM response_headers WHERE page_version_id = ?",
                (page_version_id,),
            )
        return 0

    accepted: list[tuple[int, str, str]] = []
    for raw_key, raw_value in headers.items():
        if not validate_header_name(raw_key):
            log.debug(
                "dropping header with non-RFC7230 name on page_version %s: %r",
                page_version_id,
                raw_key,
            )
            continue
        value = normalize_header_value(raw_value)
        accepted.append((page_version_id, raw_key, value))

    with db.transaction(immediate=True) as c:
        c.execute(
            "DELETE FROM response_headers WHERE page_version_id = ?",
            (page_version_id,),
        )
        if accepted:
            c.executemany(
                "INSERT OR IGNORE INTO response_headers(page_version_id, key, value) "
                "VALUES (?, ?, ?)",
                accepted,
            )
    return len(accepted)


def list_clusters(
    db: "CrawlDB", *, min_sites: int = 2
) -> list[dict[str, Any]]:
    """Return clusters whose ``(key, value)`` is shared by ≥ ``min_sites`` nodes.

    Ephemeral headers and rows whose key fails RFC 7230 are dropped. Nodes
    in ``graph_filters.excluded_node_ids`` are removed before counting.
    """
    if min_sites < 1:
        raise ValueError("bad_min_sites")
    excluded = graph_filters_db.excluded_node_ids(db)

    with db.read() as c:
        total_row = c.execute(
            "SELECT COUNT(*) AS n FROM resources WHERE state = 'crawled'"
        ).fetchone()
        total_nodes = max(int(total_row["n"]), 0)
        # Excluded nodes shouldn't count toward the universe size either.
        if excluded:
            total_nodes -= len(excluded)

        # Headers are keyed per page version; only the current version's rows
        # are retained, so join through pages.current_version_id to map each
        # header back to its crawled resource.
        rows = c.execute(
            "SELECT p.resource_id AS node_id, rh.key, rh.value "
            "FROM response_headers rh "
            "JOIN pages p     ON p.current_version_id = rh.page_version_id "
            "JOIN resources r ON r.id = p.resource_id "
            "WHERE r.state = 'crawled'"
        ).fetchall()

    # Build (key, value) -> set(node_id) in Python so we can apply
    # graph-filter exclusion + name validation cheaply.
    clusters: dict[tuple[str, str], set[int]] = {}
    for r in rows:
        node_id = int(r["node_id"])
        if node_id in excluded:
            continue
        key = r["key"]
        value = r["value"]
        if not validate_header_name(key):
            continue
        if key.lower() in _EPHEMERAL:
            continue
        if value is None:
            continue
        clusters.setdefault((key, value), set()).add(node_id)

    out: list[dict[str, Any]] = []
    for (key, value), members in clusters.items():
        sites = len(members)
        if sites < min_sites:
            continue
        idf = math.log(total_nodes / sites) if total_nodes > 0 and sites > 0 else 0.0
        out.append({"key": key, "value": value, "sites": sites, "idf": idf})

    out.sort(key=lambda row: (-row["idf"], -row["sites"], row["key"], row["value"]))
    return out


def list_cluster_members(
    db: "CrawlDB",
    *,
    key: str,
    value: str,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Members of a single ``(key, value)`` cluster, capped at ``limit``."""
    if not key or value is None:
        raise ValueError("missing_key_value")
    excluded = graph_filters_db.excluded_node_ids(db)

    with db.read() as c:
        rows = c.execute(
            """SELECT r.id, r.url, pv.title AS title, p.category,
                      (SELECT a.result FROM analyses a
                       WHERE a.resource_id = r.id
                         AND a.analysis_type = 'Risk Score'
                         AND a.result IS NOT NULL
                       ORDER BY a.id DESC LIMIT 1) AS risk_score
               FROM response_headers rh
               JOIN pages p     ON p.current_version_id = rh.page_version_id
               JOIN resources r ON r.id = p.resource_id
               LEFT JOIN page_versions pv ON pv.id = p.current_version_id
               WHERE rh.key = ?
                 AND rh.value = ?
                 AND r.state = 'crawled'
               ORDER BY r.id
               LIMIT ?""",
            (key, value, limit),
        ).fetchall()

    out: list[dict[str, Any]] = []
    for r in rows:
        node_id = int(r["id"])
        if node_id in excluded:
            continue
        out.append(
            {
                "id": node_id,
                "url": r["url"],
                "title": r["title"],
                "category": r["category"],
                "risk_score": r["risk_score"],
            }
        )
    return out


def export_clusters_csv(db: "CrawlDB", *, min_sites: int = 2) -> str:
    """Render the cluster list as CSV with formula-injection guards."""
    clusters = list_clusters(db, min_sites=min_sites)
    buf = io.StringIO()
    writer = csv_module.writer(buf, lineterminator="\n")
    writer.writerow(("header_key", "header_value", "sites", "idf"))
    for row in clusters:
        writer.writerow(
            (
                _csv_safe(row["key"]),
                _csv_safe(row["value"]),
                row["sites"],
                f"{row['idf']:.6g}",
            )
        )
    return buf.getvalue()


def _csv_safe(value: object) -> str:
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in _FORMULA_PREFIXES:
        return "'" + s
    return s


__all__ = [
    "HEADER_VALUE_MAX",
    "RFC7230_TOKEN_RE",
    "export_clusters_csv",
    "insert_response_headers",
    "list_cluster_members",
    "list_clusters",
    "normalize_header_value",
    "validate_header_name",
]
