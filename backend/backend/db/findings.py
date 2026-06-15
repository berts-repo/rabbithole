"""Findings — the merged home for extracted entities and analyst notes.

The schema reset folds the old ``entities`` and ``notes`` tables into one
``findings`` table:

* ``kind = 'entity'`` — a regex- or LLM-extracted entity. The entity **type**
  (``email`` / ``btc`` / ``xmr`` / ``pgp`` / ``onion`` / ``handle`` / ``blob``)
  and **source** (``crawl`` / ``llm``) live in ``metadata`` (JSON). The CHECK
  enum the old ``entities`` table enforced is now validated here, in the write
  path, before the row reaches disk.
* ``kind = 'note'`` — an analyst note; the body lives in ``value``.

A finding attaches to a ``resource_id`` (URL-level) and optionally a
``page_version_id``: NULL means "applies to the resource generally" (analyst
notes, user-applied findings); set means "extracted from this specific crawl's
content" (crawl/LLM entities point at the version they came from).

Entity read helpers (per-domain lists, common-across-resources, type
breakdown) replace the old read-only ``entities`` module. They join
``resources`` and count only ``state = 'crawled'`` resources — entities on a
not-yet-crawled URL are useless and would skew the "shared by N sites"
counters (the old code filtered ``nodes.stub = 0``).
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from .core import CrawlDB


ENTITY_TYPES = ("email", "btc", "xmr", "pgp", "onion", "i2p", "handle", "blob")
ENTITY_SOURCES = ("crawl", "llm")

COMMON_MAX_RESOURCE_IDS = 200
NOTE_BODY_MAX = 8192

# Find: how much of a matched note body to return as the result snippet. The
# full note stays available in the right panel; the list row only needs a peek.
NOTE_SNIPPET_CHARS = 200


def _like_escape(term: str) -> str:
    """Escape LIKE wildcards so a query is matched literally (ESCAPE '\\')."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_findings(
    db: "CrawlDB", *, query_text: str, limit: int
) -> list[dict[str, Any]]:
    """Substring search over the ``findings`` table for the Find sub-tab.

    Matches ``findings.value`` (entity values + note bodies) case-insensitively
    via ``LIKE``. Entities and notes are short, exact-ish strings, so substring
    match is the right tool and there is no FTS index on ``findings``;
    ``idx_findings_kind`` bounds the scan. Joins ``resources`` for the URL /
    node identity so each row can highlight its graph node.

    Returns rows shaped per ``docs/specs/explore-left-pane-find.md``:
    ``{type:'entity', node_id, url, entity_type, value}`` and
    ``{type:'note', node_id, url, snippet}``. Entities sort before notes.
    """
    term = (query_text or "").strip()
    if not term:
        return []
    pattern = "%" + _like_escape(term) + "%"
    with db.read() as c:
        rows = c.execute(
            r"""SELECT f.kind,
                       f.value,
                       json_extract(f.metadata, '$.type') AS entity_type,
                       r.id AS resource_id, r.url
                FROM findings f
                JOIN resources r ON r.id = f.resource_id
                WHERE f.value LIKE ? ESCAPE '\'
                ORDER BY f.kind, f.id DESC
                LIMIT ?""",
            (pattern, int(limit)),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        if r["kind"] == "entity":
            out.append(
                {
                    "type": "entity",
                    "node_id": int(r["resource_id"]),
                    "url": r["url"],
                    "entity_type": r["entity_type"],
                    "value": r["value"],
                }
            )
        else:
            body = r["value"] or ""
            snippet = body[:NOTE_SNIPPET_CHARS] + (
                "…" if len(body) > NOTE_SNIPPET_CHARS else ""
            )
            out.append(
                {
                    "type": "note",
                    "node_id": int(r["resource_id"]),
                    "url": r["url"],
                    "snippet": snippet,
                }
            )
    return out


# --- entity writes ---------------------------------------------------------


def insert_entities(
    db: "CrawlDB",
    resource_id: int,
    entries: Iterable[tuple[str, str]],
    *,
    source: str = "crawl",
    page_version_id: int | None = None,
    now: str | None = None,
) -> None:
    """Insert ``(type, value)`` entity findings for ``resource_id``.

    Type + source are validated against the legacy entity vocabulary (the
    CHECK enum is gone from the schema; validation moved here). Duplicate
    findings — same resource, type, value, source — are skipped so a re-crawl
    never stacks duplicate entities, matching the old ``INSERT OR IGNORE`` on
    the ``(node_id, type, value, source)`` PK.
    """
    if source not in ENTITY_SOURCES:
        raise ValueError(f"bad_entity_source:{source}")
    rows: list[tuple[int, int | None, str, str]] = []
    for etype, value in entries:
        if etype not in ENTITY_TYPES:
            raise ValueError(f"bad_entity_type:{etype}")
        meta = json.dumps({"type": etype, "source": source}, separators=(",", ":"))
        rows.append((resource_id, page_version_id, value, meta))
    if not rows:
        return
    with db.transaction(immediate=True) as c:
        for resource_id_, pv_id, value, meta in rows:
            etype = json.loads(meta)["type"]
            # Dedupe on (resource, type, value, source) — emulate the old PK.
            exists = c.execute(
                """SELECT 1 FROM findings
                    WHERE kind='entity' AND resource_id=? AND value=?
                      AND json_extract(metadata, '$.type')=?
                      AND json_extract(metadata, '$.source')=?""",
                (resource_id_, value, etype, source),
            ).fetchone()
            if exists is not None:
                continue
            c.execute(
                """INSERT INTO findings(
                    resource_id, page_version_id, kind, value, metadata, created_at
                ) VALUES (?, ?, 'entity', ?, ?, ?)""",
                (resource_id_, pv_id, value, meta, now),
            )


# --- entity reads ----------------------------------------------------------


def list_for_domain(db: "CrawlDB", host: str) -> list[dict[str, Any]]:
    """Distinct ``(type, value)`` entity findings on crawled resources for ``host``."""
    with db.read() as c:
        rows = c.execute(
            """SELECT DISTINCT json_extract(f.metadata, '$.type') AS type, f.value
               FROM findings f
               JOIN resources r ON r.id = f.resource_id
               WHERE f.kind='entity' AND r.host = ? AND r.state = 'crawled'
               ORDER BY type, f.value""",
            (host,),
        ).fetchall()
    return [{"type": r["type"], "value": r["value"]} for r in rows]


def list_common(db: "CrawlDB", resource_ids: list[int]) -> list[dict[str, Any]]:
    """Entity findings present on ≥ 2 of the given crawled resources.

    Each row carries ``matches`` (how many input resources share the entity)
    and ``total`` (how many input ids resolved to a crawled resource).
    """
    if not resource_ids:
        raise ValueError("bad_resource_ids")
    if len(resource_ids) > COMMON_MAX_RESOURCE_IDS:
        raise ValueError("too_many_ids")
    placeholders = ",".join("?" * len(resource_ids))
    with db.read() as c:
        total_row = c.execute(
            f"SELECT COUNT(*) AS n FROM resources "
            f"WHERE id IN ({placeholders}) AND state = 'crawled'",
            list(resource_ids),
        ).fetchone()
        total = int(total_row["n"])
        rows = c.execute(
            f"""SELECT json_extract(f.metadata, '$.type') AS type, f.value,
                       COUNT(DISTINCT f.resource_id) AS matches
                FROM findings f
                JOIN resources r ON r.id = f.resource_id
                WHERE f.kind='entity'
                  AND f.resource_id IN ({placeholders})
                  AND r.state = 'crawled'
                GROUP BY type, f.value
                HAVING matches >= 2
                ORDER BY matches DESC, type, f.value""",
            list(resource_ids),
        ).fetchall()
    return [
        {
            "type": r["type"],
            "value": r["value"],
            "matches": int(r["matches"]),
            "total": total,
        }
        for r in rows
    ]


def entity_count_for_domain(db: "CrawlDB", host: str) -> int:
    with db.read() as c:
        row = c.execute(
            """SELECT COUNT(*) AS n FROM (
                   SELECT DISTINCT json_extract(f.metadata, '$.type') AS type, f.value
                   FROM findings f
                   JOIN resources r ON r.id = f.resource_id
                   WHERE f.kind='entity' AND r.host = ? AND r.state = 'crawled'
               )""",
            (host,),
        ).fetchone()
    return int(row["n"])


def entity_type_breakdown(db: "CrawlDB", host: str) -> list[dict[str, Any]]:
    with db.read() as c:
        rows = c.execute(
            """SELECT json_extract(f.metadata, '$.type') AS type,
                      COUNT(DISTINCT f.value) AS count
               FROM findings f
               JOIN resources r ON r.id = f.resource_id
               WHERE f.kind='entity' AND r.host = ? AND r.state = 'crawled'
               GROUP BY type
               ORDER BY count DESC, type""",
            (host,),
        ).fetchall()
    return [{"type": r["type"], "count": int(r["count"])} for r in rows]


# --- notes -----------------------------------------------------------------


def list_notes(db: "CrawlDB", resource_id: int) -> list[dict[str, Any]]:
    with db.read() as c:
        rows = c.execute(
            "SELECT id, value AS body, created_at FROM findings "
            "WHERE kind='note' AND resource_id = ? ORDER BY id DESC",
            (resource_id,),
        ).fetchall()
    return [{k: r[k] for k in r.keys()} for r in rows]


def create_note(
    db: "CrawlDB", resource_id: int, body: str, *, now: str
) -> dict[str, Any]:
    cleaned = (body or "").strip()
    if not cleaned:
        raise ValueError("body_required")
    if len(cleaned) > NOTE_BODY_MAX:
        raise ValueError("body_too_long")
    with db.transaction(immediate=True) as c:
        exists = c.execute(
            "SELECT 1 FROM resources WHERE id = ?", (resource_id,)
        ).fetchone()
        if exists is None:
            raise ValueError("unknown_resource")
        cur = c.execute(
            "INSERT INTO findings(resource_id, kind, value, created_at) "
            "VALUES (?, 'note', ?, ?)",
            (resource_id, cleaned, now),
        )
        new_id = int(cur.lastrowid)
    return {"id": new_id, "body": cleaned, "created_at": now}


def delete_note(db: "CrawlDB", note_id: int) -> bool:
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "DELETE FROM findings WHERE kind='note' AND id = ?", (note_id,)
        )
        return cur.rowcount > 0


__all__ = [
    "COMMON_MAX_RESOURCE_IDS",
    "ENTITY_SOURCES",
    "ENTITY_TYPES",
    "NOTE_BODY_MAX",
    "NOTE_SNIPPET_CHARS",
    "create_note",
    "delete_note",
    "entity_count_for_domain",
    "entity_type_breakdown",
    "insert_entities",
    "list_common",
    "list_for_domain",
    "list_notes",
    "search_findings",
]
