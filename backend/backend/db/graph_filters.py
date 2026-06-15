"""graph_filters CRUD + shared exclusion helper.

PLAN.md:325 — the Hidden sub-tab persists terms whose case-insensitive
substring match against a node's URL or title removes that node (and every
incident edge) from the graph payload, the Domains list, fingerprint
expansion, and exports (PLAN.md:308).

``db/graph.py`` reads ``graph_filters`` directly via ``_load_filter_terms``;
B7e (fingerprints) and B7f (domains) call :func:`excluded_node_ids` so the
exclusion logic stays in one place.
"""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import CrawlDB


MAX_TERM_LEN = 256
MAX_TERMS = 500


def list_terms(db: "CrawlDB") -> list[str]:
    with db.read() as c:
        rows = c.execute(
            "SELECT term FROM graph_filters ORDER BY term"
        ).fetchall()
    return [r["term"] for r in rows]


def add_term(db: "CrawlDB", term: str) -> str:
    """Insert ``term`` (trimmed). Returns the stored value.

    Raises ``ValueError`` with one of: ``term_required``, ``term_too_long``,
    ``too_many_terms``, ``duplicate_term``.
    """
    cleaned = (term or "").strip()
    if not cleaned:
        raise ValueError("term_required")
    if len(cleaned) > MAX_TERM_LEN:
        raise ValueError("term_too_long")
    with db.transaction(immediate=True) as c:
        existing = c.execute("SELECT COUNT(*) FROM graph_filters").fetchone()[0]
        if existing >= MAX_TERMS:
            raise ValueError("too_many_terms")
        try:
            c.execute("INSERT INTO graph_filters(term) VALUES (?)", (cleaned,))
        except sqlite3.IntegrityError as exc:
            raise ValueError("duplicate_term") from exc
    return cleaned


def remove_term(db: "CrawlDB", term: str) -> bool:
    with db.transaction(immediate=True) as c:
        cur = c.execute("DELETE FROM graph_filters WHERE term = ?", (term,))
        return cur.rowcount > 0


def excluded_node_ids(db: "CrawlDB") -> set[int]:
    """Return the set of resource ids hidden by any active filter term.

    Used by B7e fingerprints and B7f domains. The graph payload itself
    short-circuits earlier (it never loads filtered nodes), but those
    downstream queries need an explicit exclusion set. A term matches a
    resource's URL or its current page version's title (title moved to
    ``page_versions`` in the schema reset).
    """
    terms = list_terms(db)
    if not terms:
        return set()
    excluded: set[int] = set()
    with db.read() as c:
        for term in terms:
            pattern = f"%{term.lower()}%"
            rows = c.execute(
                "SELECT r.id FROM resources r "
                "LEFT JOIN pages p ON p.resource_id = r.id "
                "LEFT JOIN page_versions pv ON pv.id = p.current_version_id "
                "WHERE lower(IFNULL(r.url, '')) LIKE ? "
                "   OR lower(IFNULL(pv.title, '')) LIKE ?",
                (pattern, pattern),
            ).fetchall()
            for r in rows:
                excluded.add(int(r["id"]))
    return excluded


__all__ = [
    "MAX_TERM_LEN",
    "MAX_TERMS",
    "add_term",
    "excluded_node_ids",
    "list_terms",
    "remove_term",
]
