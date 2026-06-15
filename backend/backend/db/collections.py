"""Collection CRUD + membership + export builder.

F3 shipped ``list_collections`` and ``create_collection`` for the Crawl
sub-tab dropdown. B7 fills the rest (PATCH, DELETE, item add/remove,
export payload). Collection-scoped LLM synthesis lands with B8.
"""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

from . import graph as graph_db

if TYPE_CHECKING:
    from .core import CrawlDB


NAME_MAX = 120
DESCRIPTION_MAX = 4096


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def list_collections(db: "CrawlDB") -> list[dict[str, object]]:
    """Return ``[{id, name, description, item_count}, ...]`` newest id first."""
    with db.read() as c:
        rows = c.execute(
            """SELECT c.id, c.name, c.description,
                      (SELECT COUNT(*) FROM collection_items ci
                       WHERE ci.collection_id = c.id) AS item_count
               FROM collections c
               ORDER BY c.id DESC"""
        ).fetchall()
    return [{k: r[k] for k in r.keys()} for r in rows]


def get_collection(db: "CrawlDB", cid: int) -> dict[str, Any] | None:
    with db.read() as c:
        row = c.execute(
            "SELECT id, name, description FROM collections WHERE id = ?",
            (cid,),
        ).fetchone()
    return _row_to_dict(row)


def create_collection(
    db: "CrawlDB",
    name: str,
    *,
    description: str | None = None,
) -> int:
    """Insert a new collection. Returns the new row id.

    Raises ``ValueError`` if ``name`` is empty after trim, longer than
    ``NAME_MAX`` chars, or collides with an existing row (the schema marks
    ``name`` UNIQUE).
    """
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValueError("name_required")
    if len(cleaned) > NAME_MAX:
        raise ValueError("name_too_long")
    if description is not None and len(description) > DESCRIPTION_MAX:
        raise ValueError("description_too_long")
    try:
        with db.transaction(immediate=True) as c:
            cur = c.execute(
                "INSERT INTO collections(name, description) VALUES (?, ?)",
                (cleaned, description),
            )
            return int(cur.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise ValueError("duplicate_name") from exc


def find_or_create_by_name(db: "CrawlDB", name: str) -> int:
    """Return the id of the collection named ``name``, creating it if needed.

    Case-insensitive match (``name`` is ``UNIQUE COLLATE NOCASE``), so
    "Investigations" and "investigations" resolve to one row. Used by crawl
    intake to resolve a pending collection name to an id at enqueue time
    (replaces the old ``crawl_queue.resolve_pending_collection``).
    """
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValueError("name_required")
    if len(cleaned) > NAME_MAX:
        raise ValueError("name_too_long")
    with db.transaction(immediate=True) as c:
        row = c.execute(
            "SELECT id FROM collections WHERE name = ? COLLATE NOCASE",
            (cleaned,),
        ).fetchone()
        if row is not None:
            return int(row["id"])
        cur = c.execute(
            "INSERT INTO collections(name) VALUES (?)", (cleaned,)
        )
        return int(cur.lastrowid)


def update_collection(
    db: "CrawlDB",
    cid: int,
    *,
    name: str | None = None,
    description: str | None = None,
    clear_description: bool = False,
) -> dict[str, Any] | None:
    sets: list[str] = []
    params: list[Any] = []
    if name is not None:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("name_required")
        if len(cleaned) > NAME_MAX:
            raise ValueError("name_too_long")
        sets.append("name = ?")
        params.append(cleaned)
    if clear_description:
        sets.append("description = NULL")
    elif description is not None:
        if len(description) > DESCRIPTION_MAX:
            raise ValueError("description_too_long")
        sets.append("description = ?")
        params.append(description)
    if not sets:
        return get_collection(db, cid)
    params.append(cid)
    try:
        with db.transaction(immediate=True) as c:
            cur = c.execute(
                f"UPDATE collections SET {', '.join(sets)} WHERE id = ?",
                params,
            )
            if cur.rowcount == 0:
                return None
            row = c.execute(
                "SELECT id, name, description FROM collections WHERE id = ?",
                (cid,),
            ).fetchone()
    except sqlite3.IntegrityError as exc:
        raise ValueError("duplicate_name") from exc
    return _row_to_dict(row)


def delete_collection(db: "CrawlDB", cid: int) -> bool:
    with db.transaction(immediate=True) as c:
        cur = c.execute("DELETE FROM collections WHERE id = ?", (cid,))
        return cur.rowcount > 0


def list_items(db: "CrawlDB", cid: int) -> list[dict[str, Any]]:
    """Joined with resources for url/state + current version title/status.

    Newest membership first. ``collection_items.node_id`` references
    ``resources(id)`` after the schema reset; title and status come from the
    current page version, and ``state`` replaces the old ``stub`` boolean.
    """
    with db.read() as c:
        rows = c.execute(
            """SELECT r.id, r.url, r.host AS domain, r.state,
                      pv.title AS title, pv.http_status AS status_code
               FROM collection_items ci
               JOIN resources r ON r.id = ci.node_id
               LEFT JOIN pages p ON p.resource_id = r.id
               LEFT JOIN page_versions pv ON pv.id = p.current_version_id
               WHERE ci.collection_id = ?
               ORDER BY r.id DESC""",
            (cid,),
        ).fetchall()
    return [
        {
            "id": int(r["id"]),
            "url": r["url"],
            "title": r["title"],
            "state": r["state"],
            "status_code": r["status_code"],
            "domain": r["domain"],
        }
        for r in rows
    ]


def add_item(db: "CrawlDB", cid: int, node_id: int) -> bool:
    """Idempotent. Returns True if the row was newly inserted.

    Raises ``ValueError`` with ``unknown_collection`` / ``unknown_node``.
    """
    with db.transaction(immediate=True) as c:
        if (
            c.execute(
                "SELECT 1 FROM collections WHERE id = ?", (cid,)
            ).fetchone()
            is None
        ):
            raise ValueError("unknown_collection")
        if (
            c.execute(
                "SELECT 1 FROM resources WHERE id = ?", (node_id,)
            ).fetchone()
            is None
        ):
            raise ValueError("unknown_node")
        cur = c.execute(
            "INSERT OR IGNORE INTO collection_items(collection_id, node_id) "
            "VALUES (?, ?)",
            (cid, node_id),
        )
        return cur.rowcount > 0


def add_items(
    db: "CrawlDB", cid: int, node_ids: list[int]
) -> dict[str, Any]:
    """Bulk-add nodes to a collection. Idempotent per node, one transaction.

    Returns ``{"added": n, "skipped": n, "added_ids": [...]}`` — ``added``
    counts newly inserted memberships, ``added_ids`` is exactly those ids (in
    input order), and ``skipped`` counts ids that were already members or do
    not reference an existing node (batch semantics: one bad id does not fail
    the whole call). ``added_ids`` lets the collection-add auto-analysis hook
    fire only for genuinely new members. Raises
    ``ValueError('unknown_collection')`` if ``cid`` is unknown.

    Input order is preserved and duplicate ids within the batch are deduped.
    """
    ids = list(dict.fromkeys(int(n) for n in node_ids))
    with db.transaction(immediate=True) as c:
        if (
            c.execute("SELECT 1 FROM collections WHERE id = ?", (cid,)).fetchone()
            is None
        ):
            raise ValueError("unknown_collection")
        if not ids:
            return {"added": 0, "skipped": 0, "added_ids": []}
        placeholders = ",".join("?" for _ in ids)
        known = {
            int(r["id"])
            for r in c.execute(
                f"SELECT id FROM resources WHERE id IN ({placeholders})", ids
            ).fetchall()
        }
        added_ids: list[int] = []
        for nid in ids:
            if nid not in known:
                continue
            cur = c.execute(
                "INSERT OR IGNORE INTO collection_items(collection_id, node_id) "
                "VALUES (?, ?)",
                (cid, nid),
            )
            if cur.rowcount > 0:
                added_ids.append(nid)
    return {
        "added": len(added_ids),
        "skipped": len(ids) - len(added_ids),
        "added_ids": added_ids,
    }


def remove_item(db: "CrawlDB", cid: int, node_id: int) -> bool:
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "DELETE FROM collection_items "
            "WHERE collection_id = ? AND node_id = ?",
            (cid, node_id),
        )
        return cur.rowcount > 0


def list_for_node(db: "CrawlDB", node_id: int) -> list[dict[str, Any]]:
    """Return ``[{id, name}, ...]`` collections this node belongs to."""
    with db.read() as c:
        rows = c.execute(
            """SELECT c.id, c.name FROM collections c
               JOIN collection_items ci ON ci.collection_id = c.id
               WHERE ci.node_id = ?
               ORDER BY c.name""",
            (node_id,),
        ).fetchall()
    return [{"id": int(r["id"]), "name": r["name"]} for r in rows]


def member_ids(db: "CrawlDB", cid: int) -> set[int] | None:
    """Return the node-id membership set for a collection.

    Returns ``None`` when the collection id is unknown (distinct from
    "exists but empty", which returns an empty set). Callers that need
    to differentiate ``404`` from "no rows" must inspect for ``None``.
    """
    with db.read() as c:
        exists = c.execute(
            "SELECT 1 FROM collections WHERE id = ?", (cid,)
        ).fetchone()
        if exists is None:
            return None
        rows = c.execute(
            "SELECT node_id FROM collection_items WHERE collection_id = ?",
            (cid,),
        ).fetchall()
    return {int(r["node_id"]) for r in rows}


def filter_payload_to_members(
    payload: dict[str, Any], members: set[int]
) -> dict[str, Any]:
    """Pure post-filter — keep nodes in ``members``, edges with both ends surviving.

    Operates on the ``{nodes, edges}`` shape produced by
    ``db.graph.build_payload`` so the graph route can hand off its cached
    full payload without rebuilding.

    Uncrawled nodes (``state != 'crawled'``) are never in ``members``
    (collection_items only stores crawled resources), but the frontend's
    "show uncrawled" toggle needs them in the payload. We include uncrawled
    nodes that are targets of edges from member nodes so the client can gate
    their visibility on its own filter, matching global-tab behaviour.
    """
    nodes = [n for n in payload["nodes"] if int(n["id"]) in members]
    surviving = {int(n["id"]) for n in nodes}

    uncrawled_by_id = {
        int(n["id"]): n
        for n in payload["nodes"]
        if n.get("state") != "crawled"
    }
    reachable_uncrawled: set[int] = set()
    for e in payload["edges"]:
        if int(e["from"]) in surviving and int(e["to"]) in uncrawled_by_id:
            reachable_uncrawled.add(int(e["to"]))
    for sid in sorted(reachable_uncrawled):
        nodes.append(uncrawled_by_id[sid])

    surviving_all = surviving | reachable_uncrawled
    edges = [
        e for e in payload["edges"]
        if int(e["from"]) in surviving_all and int(e["to"]) in surviving_all
    ]
    return {"nodes": nodes, "edges": edges}


def build_export_payload(db: "CrawlDB", cid: int) -> dict[str, Any]:
    """Build a graph-shaped payload restricted to a collection's members.

    Reuses ``db.graph.build_payload`` (which honors the ``graph_filters``
    exclusion) and post-filters to ``collection_items``. Edges are kept only
    when both endpoints survive the filter.

    Raises ``ValueError('unknown_collection')`` if the collection doesn't exist.
    """
    meta = get_collection(db, cid)
    if meta is None:
        raise ValueError("unknown_collection")

    members = member_ids(db, cid)
    assert members is not None  # get_collection just confirmed existence
    base = graph_db.build_payload(db)
    filtered = filter_payload_to_members(base, members)
    return {
        "collection": meta,
        "nodes": filtered["nodes"],
        "edges": filtered["edges"],
    }


__all__ = [
    "DESCRIPTION_MAX",
    "NAME_MAX",
    "add_item",
    "add_items",
    "build_export_payload",
    "create_collection",
    "delete_collection",
    "filter_payload_to_members",
    "find_or_create_by_name",
    "get_collection",
    "list_collections",
    "list_for_node",
    "list_items",
    "member_ids",
    "remove_item",
    "update_collection",
]
