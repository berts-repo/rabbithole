"""Page versions — per-crawl snapshots and the crawl-write orchestration.

Each crawl of a URL appends a ``page_versions`` row instead of overwriting the
previous one. A version stores the fetched text (``body_text`` +
``body_text_clean``), a ``body_hash`` of the clean text for fast change
detection, the ``title``, the ``http_status``, and ``content_changed`` (1 when
the hash differs from the prior version). ``pages.current_version_id`` is a
cached pointer to the newest version.

This module owns the **crawl-write orchestration** — :func:`record_fetch` and
:func:`record_failed_fetch` — that the crawler runtime calls once per page. In
one transaction it:

1. upserts the ``resources`` identity and promotes it to ``crawled``,
2. ensures the 1:1 ``pages`` row,
3. inserts a new ``page_versions`` row (computing ``body_hash`` /
   ``content_changed`` against the prior current version),
4. advances ``pages.current_version_id``,
5. maintains the contentless ``pages_fts`` index by hand (delete the stale
   current row, insert the new current text) — there are no FTS triggers in
   the v3 schema because the indexed text lives in ``page_versions``, not in
   the keyed ``pages`` table,
6. writes the current-version response headers (via ``fingerprints``).

Both functions return ``(resource_id, version_id)``. ``resource_id`` is the
identity edges / crawl_nodes / collections / entities point at.
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from . import fingerprints as fingerprints_db
from . import pages as pages_db
from . import resources as resources_db

if TYPE_CHECKING:
    from .core import CrawlDB


def _hash(clean: str | None) -> str | None:
    if not clean:
        return None
    return hashlib.sha256(clean.encode("utf-8", errors="replace")).hexdigest()


def hash_clean_text(clean: str | None) -> str | None:
    """Public alias for the clean-text content hash.

    The monitor daemon hashes a probe's fetched text with the *same* function
    the crawl-write path uses, so a probe's ``body_hash`` is directly
    comparable to a page version's.
    """
    return _hash(clean)


def _current_version_row(c: Any, page_id: int) -> Any:
    """The current version row for a page, or None."""
    return c.execute(
        """SELECT pv.id, pv.body_hash, pv.body_text_clean
             FROM pages p
             JOIN page_versions pv ON pv.id = p.current_version_id
            WHERE p.id = ?""",
        (page_id,),
    ).fetchone()


def _maintain_fts(c: Any, page_id: int, old_clean: str | None, new_clean: str | None) -> None:
    """Keep ``pages_fts`` (contentless, rowid = page_id) on the current text.

    Delete the stale current row if one was indexed, then insert the new
    current text. An empty new body leaves the page with no searchable row,
    matching the "search reflects the current version" rule.
    """
    if old_clean:
        c.execute(
            "INSERT INTO pages_fts(pages_fts, rowid, body_text_clean) "
            "VALUES('delete', ?, ?)",
            (page_id, old_clean),
        )
    if new_clean:
        c.execute(
            "INSERT INTO pages_fts(rowid, body_text_clean) VALUES (?, ?)",
            (page_id, new_clean),
        )


def _append_version(
    db: "CrawlDB",
    *,
    url: str,
    host: str,
    status_code: int | None,
    title: str | None,
    body_text: str | None,
    body_text_clean: str | None,
    response_headers: dict[str, object],
    when: str,
) -> tuple[int, int]:
    """Shared write path for both fetched and content-rejected pages."""
    new_clean = body_text_clean
    body_hash = _hash(new_clean)
    with db.transaction(immediate=True) as c:
        resource_id = resources_db.upsert_resource(db, url, host, state="known", when=when)
        c.execute(
            "UPDATE resources SET state='crawled', last_seen=?, "
            "last_state_change=CASE WHEN state='crawled' THEN last_state_change ELSE ? END "
            "WHERE id=?",
            (when, when, resource_id),
        )
        page_id = pages_db.ensure_page(db, resource_id, now=when)

        prior = _current_version_row(c, page_id)
        old_clean = prior["body_text_clean"] if prior is not None else None
        prior_hash = prior["body_hash"] if prior is not None else None
        content_changed = 1 if body_hash != prior_hash else 0

        # Retain only the current fetch's headers (decision D5): prune the
        # prior version's header rows as the version advances.
        if prior is not None:
            c.execute(
                "DELETE FROM response_headers WHERE page_version_id = ?",
                (prior["id"],),
            )

        cur = c.execute(
            """INSERT INTO page_versions(
                page_id, fetched_at, http_status, body_text, body_text_clean,
                body_hash, title, content_changed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (page_id, when, status_code, body_text, new_clean, body_hash, title, content_changed),
        )
        version_id = int(cur.lastrowid)
        c.execute(
            "UPDATE pages SET current_version_id=? WHERE id=?",
            (version_id, page_id),
        )
        _maintain_fts(c, page_id, old_clean, new_clean)
        # Headers are keyed per current version; the helper runs in this txn
        # (reentrant) so the whole page write is atomic.
        fingerprints_db.insert_response_headers(db, version_id, response_headers)
    return resource_id, version_id


def record_fetch(
    db: "CrawlDB",
    *,
    url: str,
    host: str,
    status_code: int,
    title: str | None,
    body_text: str | None,
    body_text_clean: str | None,
    response_headers: dict[str, object],
    when: str,
) -> tuple[int, int]:
    """Persist a successfully fetched page. Returns ``(resource_id, version_id)``."""
    return _append_version(
        db,
        url=url,
        host=host,
        status_code=status_code,
        title=title,
        body_text=body_text,
        body_text_clean=body_text_clean,
        response_headers=response_headers,
        when=when,
    )


def record_failed_fetch(
    db: "CrawlDB",
    *,
    url: str,
    status_code: int | None,
    response_headers: dict[str, object],
    host: str,
    when: str,
) -> tuple[int, int]:
    """Persist a reached-but-content-rejected page (no body).

    The URL was successfully reached (e.g. a non-HTML Content-Type), so the
    resource is ``crawled`` and a version records the status + headers with no
    body. Distinct from a true fetch failure, which the runtime counts without
    writing a row (and which feeds the dead-state threshold via
    ``resources.recent_failure_count``).
    """
    return _append_version(
        db,
        url=url,
        host=host,
        status_code=status_code,
        title=None,
        body_text=None,
        body_text_clean=None,
        response_headers=response_headers,
        when=when,
    )


# --- reads ------------------------------------------------------------------


def list_history(db: "CrawlDB", page_id: int) -> list[dict[str, Any]]:
    """Every version of a page, newest first (timeline / version picker)."""
    with db.read() as c:
        rows = c.execute(
            "SELECT id, fetched_at, http_status, title, body_hash, content_changed "
            "FROM page_versions WHERE page_id = ? ORDER BY fetched_at DESC, id DESC",
            (page_id,),
        ).fetchall()
    return [
        {
            "id": int(r["id"]),
            "fetched_at": r["fetched_at"],
            "http_status": r["http_status"],
            "title": r["title"],
            "body_hash": r["body_hash"],
            "content_changed": (
                bool(r["content_changed"]) if r["content_changed"] is not None else None
            ),
        }
        for r in rows
    ]


def get_version(db: "CrawlDB", version_id: int) -> dict[str, Any] | None:
    """Full version row including body text (diff view, version picker)."""
    with db.read() as c:
        row = c.execute(
            "SELECT * FROM page_versions WHERE id = ?", (version_id,)
        ).fetchone()
    return {k: row[k] for k in row.keys()} if row is not None else None


def latest_hash(db: "CrawlDB", page_id: int) -> str | None:
    """Current version's ``body_hash`` — monitors compare against this."""
    with db.read() as c:
        row = _current_version_row(c, page_id)
    return row["body_hash"] if row is not None else None


def current_clean_text(
    db: "CrawlDB", resource_ids: list[int]
) -> dict[int, str]:
    """``{resource_id: current-version body_text_clean}`` for the given ids.

    Reads each resource's current page version (via ``pages.current_version_id``)
    and returns only the entries with non-empty clean text. Resources that are
    uncrawled, have no current version, or have an empty body are absent from
    the map. Shared by the LLM collection-synthesis path and the embed worker —
    the content lives on ``page_versions`` now, so the reader lives here.
    """
    if not resource_ids:
        return {}
    placeholders = ",".join("?" * len(resource_ids))
    with db.read() as c:
        rows = c.execute(
            f"""SELECT p.resource_id AS rid, pv.body_text_clean AS clean
                  FROM pages p
                  JOIN page_versions pv ON pv.id = p.current_version_id
                 WHERE p.resource_id IN ({placeholders})""",
            [int(r) for r in resource_ids],
        ).fetchall()
    return {int(r["rid"]): r["clean"] for r in rows if r["clean"]}


__all__ = [
    "current_clean_text",
    "get_version",
    "hash_clean_text",
    "latest_hash",
    "list_history",
    "record_failed_fetch",
    "record_fetch",
]
