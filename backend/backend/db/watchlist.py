"""Watchlist CRUD — literal terms only.

PLAN.md:38, :296 — literal-term watchlist, case-insensitive matching done by
the crawl runtime's Aho-Corasick automaton. The DB layer's job is to enforce
the two caps:

  * each term ≤ 256 chars
  * total terms ≤ 200

Both are enforced at write time so a malformed POST never lands a bad row.
``ValueError`` subclasses surface to the route handlers as 400s.
"""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import CrawlDB


MAX_TERM_LEN = 256
MAX_TERMS = 200


class WatchlistError(ValueError):
    """Validation failure surfaced to routes as 400."""


def count_terms(db: "CrawlDB") -> int:
    with db.read() as c:
        row = c.execute("SELECT COUNT(*) FROM watchlist").fetchone()
    return int(row[0])


def list_terms(db: "CrawlDB") -> list[dict[str, object]]:
    """Return ``[{id, term}, ...]`` ordered by id ascending."""
    with db.read() as c:
        rows = c.execute(
            "SELECT id, term FROM watchlist ORDER BY id ASC"
        ).fetchall()
    return [{"id": int(r["id"]), "term": r["term"]} for r in rows]


def add_term(db: "CrawlDB", term: object) -> int:
    """Insert ``term``, returning its row id.

    Raises ``WatchlistError`` on bad input (non-string, empty after strip,
    over the length cap, over the total-count cap, duplicate).
    """
    if not isinstance(term, str):
        raise WatchlistError(f"term must be a string, got {type(term).__name__}")
    normalized = term.strip()
    if not normalized:
        raise WatchlistError("term is empty")
    if len(normalized) > MAX_TERM_LEN:
        raise WatchlistError(f"term exceeds {MAX_TERM_LEN} chars")
    if count_terms(db) >= MAX_TERMS:
        raise WatchlistError(f"watchlist already at the {MAX_TERMS}-term cap")
    try:
        with db.transaction(immediate=True) as c:
            cur = c.execute(
                "INSERT INTO watchlist(term) VALUES (?)", (normalized,)
            )
            return int(cur.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise WatchlistError("duplicate_term") from exc


def update_term(db: "CrawlDB", term_id: int, term: object) -> bool:
    """Rename an existing term. Returns ``True`` if a row matched.

    Runs the same shape validation as ``add_term`` (string, non-empty after
    strip, under the length cap, not a duplicate) but skips the total-count cap
    — an edit never grows the list. Raises ``WatchlistError`` on bad input.
    """
    if not isinstance(term, str):
        raise WatchlistError(f"term must be a string, got {type(term).__name__}")
    normalized = term.strip()
    if not normalized:
        raise WatchlistError("term is empty")
    if len(normalized) > MAX_TERM_LEN:
        raise WatchlistError(f"term exceeds {MAX_TERM_LEN} chars")
    try:
        with db.transaction(immediate=True) as c:
            cur = c.execute(
                "UPDATE watchlist SET term = ? WHERE id = ?",
                (normalized, term_id),
            )
            return cur.rowcount > 0
    except sqlite3.IntegrityError as exc:
        raise WatchlistError("duplicate_term") from exc


def remove_term(db: "CrawlDB", term_id: int) -> bool:
    """Delete by id. Returns ``True`` if a row was removed."""
    with db.transaction(immediate=True) as c:
        cur = c.execute("DELETE FROM watchlist WHERE id = ?", (term_id,))
        return cur.rowcount > 0


__all__ = [
    "MAX_TERM_LEN",
    "MAX_TERMS",
    "WatchlistError",
    "add_term",
    "count_terms",
    "list_terms",
    "remove_term",
    "update_term",
]
