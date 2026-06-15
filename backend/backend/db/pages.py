"""Pages — page-level analyst/LLM state, 1:1 with a crawled resource.

A ``pages`` row holds the durable per-page state that survives across crawls:
the LLM ``summary`` / ``category``, the analyst ``reviewed`` flag, the
``analysis_excluded`` / ``embed_excluded`` toggles, and ``opened_at``. The
actual fetched content is in ``page_versions``; ``pages.current_version_id``
points at the latest one.

Pages are created lazily — :func:`ensure_page` is called from the crawl-write
path (``page_versions.record_fetch``) and from any analyst toggle on a
resource that has not been crawled yet. Toggles key by ``resource_id`` (the
identity the rest of the app uses), resolving to the 1:1 page row.

``reviewed`` is a boolean here (schema-reset decision D4, revised): the typed
``review_state`` machine is item 7's work, built whole with the review
workflow. This module keeps today's yes/no semantics.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from . import labels as labels_db
from .flags import ACTIVE_STATUSES

if TYPE_CHECKING:
    from .core import CrawlDB


BODY_TEXT_PREVIEW_CHARS = 500


def ensure_page(db: "CrawlDB", resource_id: int, *, now: str | None = None) -> int:
    """Return the page id for ``resource_id``, creating the row if missing."""
    with db.transaction(immediate=True) as c:
        row = c.execute(
            "SELECT id FROM pages WHERE resource_id = ?", (resource_id,)
        ).fetchone()
        if row is not None:
            return int(row["id"])
        cur = c.execute(
            "INSERT INTO pages(resource_id, created_at) VALUES (?, ?)",
            (resource_id, now),
        )
        return int(cur.lastrowid)


def _update_page_col(
    db: "CrawlDB", resource_id: int, column: str, value: Any
) -> bool:
    """Set a single page column by resource id, creating the page if needed."""
    ensure_page(db, resource_id)
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            f"UPDATE pages SET {column} = ? WHERE resource_id = ?",
            (value, resource_id),
        )
        return cur.rowcount > 0


def set_opened(db: "CrawlDB", resource_id: int, when: str) -> bool:
    return _update_page_col(db, resource_id, "opened_at", when)


def set_reviewed(db: "CrawlDB", resource_id: int, reviewed: bool) -> bool:
    return _update_page_col(db, resource_id, "reviewed", 1 if reviewed else 0)


def set_analysis_excluded(db: "CrawlDB", resource_id: int, excluded: bool) -> bool:
    return _update_page_col(
        db, resource_id, "analysis_excluded", 1 if excluded else 0
    )


def set_embed_excluded(db: "CrawlDB", resource_id: int, excluded: bool) -> bool:
    """Poison-pill flag flipped by the embed worker after repeated failures."""
    return _update_page_col(
        db, resource_id, "embed_excluded", 1 if excluded else 0
    )


def set_category(db: "CrawlDB", resource_id: int, category: str | None) -> bool:
    """Set ``pages.category`` from a validated LLM Category result."""
    return _update_page_col(db, resource_id, "category", category)


def set_summary(db: "CrawlDB", resource_id: int, summary: str | None) -> bool:
    """Set ``pages.summary`` from a validated LLM Summary result."""
    return _update_page_col(db, resource_id, "summary", summary)


ALIAS_MAX = 128


def rename_alias(
    db: "CrawlDB", resource_id: int, alias: str | None
) -> dict[str, Any] | None:
    """Set or clear a page's display alias (item 11, decision D1).

    Mirrors :func:`db.domains.rename_alias` for the page half of rename, but
    page aliases need no uniqueness constraint — many pages may legitimately
    share a human label ("Vendor profile"), unlike a domain's 1:1 host alias.
    Keys by ``resource_id`` (the identity the rest of the app uses), resolving
    to the 1:1 page row and creating it if the resource has no page yet.

    Returns ``{resource_id, alias}`` with the stored value (whitespace-only is
    stored as NULL), or ``None`` if ``resource_id`` is unknown. Raises
    ``ValueError('alias_too_long')`` past :data:`ALIAS_MAX`.
    """
    cleaned: str | None
    if alias is None or not alias.strip():
        cleaned = None
    else:
        stripped = alias.strip()
        if len(stripped) > ALIAS_MAX:
            raise ValueError("alias_too_long")
        cleaned = stripped

    with db.read() as c:
        exists = c.execute(
            "SELECT 1 FROM resources WHERE id = ?", (resource_id,)
        ).fetchone()
    if exists is None:
        return None
    _update_page_col(db, resource_id, "alias", cleaned)
    return {"resource_id": resource_id, "alias": cleaned}


def get_analysis_excluded(db: "CrawlDB", resource_id: int) -> bool | None:
    """Read just the ``analysis_excluded`` bit. ``None`` when no page row."""
    with db.read() as c:
        row = c.execute(
            "SELECT analysis_excluded FROM pages WHERE resource_id = ?",
            (resource_id,),
        ).fetchone()
    return None if row is None else bool(row["analysis_excluded"])


def get_page_detail(db: "CrawlDB", resource_id: int) -> dict[str, Any] | None:
    """Right-panel shape for one resource.

    Combines the ``resources`` identity/state row, its 1:1 ``pages`` row, the
    current ``page_versions`` snapshot (title/status/body), joined response
    headers (current version), entity findings, version history, the active
    flag, and a truncated body preview. Returns ``None`` if the resource is
    unknown.
    """
    with db.read() as c:
        res = c.execute(
            "SELECT * FROM resources WHERE id = ?", (resource_id,)
        ).fetchone()
        if res is None:
            return None
        page = c.execute(
            "SELECT * FROM pages WHERE resource_id = ?", (resource_id,)
        ).fetchone()
        version = None
        headers: list[Any] = []
        if page is not None and page["current_version_id"] is not None:
            version = c.execute(
                "SELECT * FROM page_versions WHERE id = ?",
                (page["current_version_id"],),
            ).fetchone()
            headers = c.execute(
                "SELECT key, value FROM response_headers WHERE page_version_id = ?",
                (page["current_version_id"],),
            ).fetchall()
        entities = c.execute(
            """SELECT json_extract(metadata, '$.type') AS type, value,
                      json_extract(metadata, '$.source') AS source
                 FROM findings
                WHERE kind = 'entity' AND resource_id = ?
                ORDER BY type, value""",
            (resource_id,),
        ).fetchall()
        history: list[Any] = []
        if page is not None:
            history = c.execute(
                "SELECT id, fetched_at, http_status, title, content_changed "
                "FROM page_versions WHERE page_id = ? ORDER BY fetched_at DESC",
                (page["id"],),
            ).fetchall()
        _active = ",".join("?" * len(ACTIVE_STATUSES))
        flag_row = c.execute(
            f"""SELECT id, status, source, priority, note FROM flags
                 WHERE node_id = ? AND status IN ({_active})
                 ORDER BY priority ASC, id DESC LIMIT 1""",
            (resource_id, *ACTIVE_STATUSES),
        ).fetchone()

    data: dict[str, Any] = {
        "id": int(res["id"]),
        "url": res["url"],
        "domain": res["host"],
        "network": res["network"],
        "state": res["state"],
        "first_seen": res["first_seen"],
        "last_seen": res["last_seen"],
        "last_state_change": res["last_state_change"],
    }
    if page is not None:
        data.update(
            {
                "page_id": int(page["id"]),
                "current_version_id": page["current_version_id"],
                "alias": page["alias"],
                "summary": page["summary"],
                "category": page["category"],
                "reviewed": bool(page["reviewed"]),
                "analysis_excluded": bool(page["analysis_excluded"]),
                "embed_excluded": bool(page["embed_excluded"]),
                "opened_at": page["opened_at"],
            }
        )
    else:
        data.update(
            {
                "page_id": None,
                "current_version_id": None,
                "alias": None,
                "summary": None,
                "category": None,
                "reviewed": False,
                "analysis_excluded": False,
                "embed_excluded": False,
                "opened_at": None,
            }
        )
    if version is not None:
        data["title"] = version["title"]
        data["status_code"] = version["http_status"]
        data["body_text"] = version["body_text"]
        data["body_text_clean"] = version["body_text_clean"]
    else:
        data["title"] = None
        data["status_code"] = None
        data["body_text"] = None
        data["body_text_clean"] = None

    data["response_headers"] = {h["key"]: h["value"] for h in headers}
    data["entities"] = [
        {"type": e["type"], "value": e["value"], "source": e["source"]}
        for e in entities
    ]
    data["history"] = [
        {
            "id": int(h["id"]),
            "fetched_at": h["fetched_at"],
            "http_status": h["http_status"],
            "title": h["title"],
            "content_changed": bool(h["content_changed"]) if h["content_changed"] is not None else None,
        }
        for h in history
    ]
    source_text = data.get("body_text_clean") or data.get("body_text") or ""
    data["body_text_preview"] = (
        source_text[:BODY_TEXT_PREVIEW_CHARS] if source_text else None
    )
    data["flag"] = (
        {k: flag_row[k] for k in flag_row.keys()} if flag_row is not None else None
    )
    # Label membership (item 11), mirroring the graph payload: direct resource
    # labels plus via-domain ones (deduped against the direct set), ids only —
    # the frontend catalog store resolves id → name/color.
    direct = labels_db.resource_label_ids(db, resource_id)
    direct_set = set(direct)
    host = res["host"]
    via_domain = (
        [lid for lid in labels_db.domain_label_ids(db, host) if lid not in direct_set]
        if host
        else []
    )
    data["label_ids"] = direct
    data["domain_label_ids"] = via_domain
    return data


# --- full-text search over current page content ---------------------------


class FtsQueryError(Exception):
    """Raised when the FTS5 engine rejects a query string."""


def _build_snippet(text: str, query: str, *, max_tokens: int) -> str:
    """Reconstruct a ``<mark>``-highlighted snippet from the page's clean text.

    ``pages_fts`` is contentless (``content=''``), so FTS5's ``snippet()`` /
    ``highlight()`` return NULL — the source text isn't stored in the index.
    We rebuild the snippet here from the current version's clean text: take a
    window of ``max_tokens`` words centred on the first query-term hit and wrap
    each matched term in ``<mark>…</mark>`` (preserving the original case),
    flanking the window with ``…`` when it's truncated.
    """
    if not text:
        return ""
    tokens = text.split()
    if not tokens:
        return ""
    terms = {t for t in re.findall(r"\w+", query.lower()) if t}
    hit = None
    if terms:
        for i, tok in enumerate(tokens):
            if re.sub(r"\W+", "", tok).lower() in terms:
                hit = i
                break
    start = 0 if hit is None else max(0, hit - max_tokens // 2)
    end = min(len(tokens), start + max_tokens)
    pattern = (
        re.compile(rf"\b({'|'.join(re.escape(t) for t in terms)})\b", re.IGNORECASE)
        if terms
        else None
    )
    window = [
        pattern.sub(r"<mark>\1</mark>", tok) if pattern else tok
        for tok in tokens[start:end]
    ]
    snippet = " ".join(window)
    if start > 0:
        snippet = "… " + snippet
    if end < len(tokens):
        snippet = snippet + " …"
    return snippet


def keyword_search(
    db: "CrawlDB",
    *,
    fts_query: str,
    query_text: str,
    limit: int,
    snippet_tokens: int,
) -> list[dict[str, Any]]:
    """FTS5 ``MATCH`` against ``pages_fts`` (current page text), one hit per page.

    ``pages_fts`` is contentless and keyed ``rowid = pages.id``; it indexes the
    current version's clean text, so results are one row per crawled page with
    no per-version duplicates. Joins back to ``pages`` → ``resources`` for the
    URL/identity and to the current ``page_versions`` row for the title and the
    clean text used to build the snippet (``fts_query`` drives the MATCH;
    ``query_text`` is the raw user query used for highlight terms).

    Raises :class:`FtsQueryError` if SQLite rejects the query (route → 400).
    """
    try:
        with db.read() as c:
            rows = c.execute(
                """SELECT r.id AS resource_id, r.url, pv.title,
                          pv.body_text_clean AS clean
                   FROM pages_fts
                   JOIN pages p     ON p.id = pages_fts.rowid
                   JOIN resources r ON r.id = p.resource_id
                   LEFT JOIN page_versions pv ON pv.id = p.current_version_id
                   WHERE pages_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (fts_query, int(limit)),
            ).fetchall()
    except Exception as exc:  # noqa: BLE001 — SQLite raises a mix of types
        raise FtsQueryError(str(exc)) from exc
    return [
        {
            "type": "page",
            "node_id": int(r["resource_id"]),
            "url": r["url"],
            "title": r["title"],
            "snippet": _build_snippet(
                r["clean"] or "", query_text, max_tokens=int(snippet_tokens)
            ),
        }
        for r in rows
    ]


__all__ = [
    "ALIAS_MAX",
    "BODY_TEXT_PREVIEW_CHARS",
    "FtsQueryError",
    "ensure_page",
    "get_analysis_excluded",
    "get_page_detail",
    "keyword_search",
    "rename_alias",
    "set_analysis_excluded",
    "set_category",
    "set_embed_excluded",
    "set_opened",
    "set_reviewed",
    "set_summary",
]
