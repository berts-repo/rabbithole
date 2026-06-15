"""Investigation flags CRUD.

One ``flags`` row per investigation marker per node. Multiple rows per node
are permitted (history of flagging decisions) but the right panel and graph
payload only ever surface the *active* flag — the flag whose ``status`` is
``pending``, ``flagged``, or ``investigating`` (:data:`ACTIVE_STATUSES`),
picked by lowest priority number (1 = High beats 2 = Medium beats 3 = Low)
and breaking ties by newest id.

``status`` is a pure lifecycle (pending → flagged → investigating → done,
plus dismissed as the rejection branch); ``source`` records provenance
independently — ``watchlist`` for crawler auto-flags, ``analyst`` for
analyst-created ones. The crawler auto-flags watchlist hits via
:func:`insert_watchlist_flag` (below); this module is the analyst-facing path.

``done``/``dismissed`` rows are retained for audit but never shown — and no UI
sets them yet (the F6 right panel / F7 Flags sub-tab will; see the tracked
item in ``docs/work/archive/2026-05-20-todo/outcome.md``).
"""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import CrawlDB


VALID_STATUSES = frozenset(
    {"pending", "flagged", "investigating", "done", "dismissed"}
)
VALID_SOURCES = frozenset({"watchlist", "analyst"})
VALID_PRIORITIES = frozenset({1, 2, 3})
# Statuses whose flags surface in the graph payload + right panel.
ACTIVE_STATUSES = ("pending", "flagged", "investigating")


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def _node_exists(c: sqlite3.Cursor, node_id: int) -> bool:
    return (
        c.execute("SELECT 1 FROM resources WHERE id = ?", (node_id,)).fetchone()
        is not None
    )


def insert_watchlist_flag(
    db: "CrawlDB", resource_id: int, matched_terms: list[str]
) -> int:
    """Auto-flag a resource whose body matched watchlist terms (crawler path).

    Carries the ``watchlist:`` note prefix and ``source='watchlist'`` so the
    Flags pane can tell auto-flags from analyst ones. Moved here from the old
    ``db.nodes`` module in the schema reset.
    """
    note = "watchlist:" + ",".join(matched_terms)
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "INSERT INTO flags(node_id, status, source, priority, note) "
            "VALUES (?, 'pending', 'watchlist', 2, ?)",
            (resource_id, note),
        )
        return int(cur.lastrowid)


def list_flags(db: "CrawlDB") -> list[dict[str, object]]:
    """Return every flag joined with resource url + current title for the list."""
    with db.read() as c:
        rows = c.execute(
            """SELECT f.id, f.node_id, f.status, f.source, f.priority, f.note,
                      r.url, pv.title AS title
               FROM flags f
               JOIN resources r ON r.id = f.node_id
               LEFT JOIN pages p ON p.resource_id = r.id
               LEFT JOIN page_versions pv ON pv.id = p.current_version_id
               ORDER BY f.priority ASC, f.id DESC"""
        ).fetchall()
    return [{k: r[k] for k in r.keys()} for r in rows]


def get_flag(db: "CrawlDB", flag_id: int) -> dict[str, object] | None:
    with db.read() as c:
        row = c.execute(
            "SELECT id, node_id, status, source, priority, note "
            "FROM flags WHERE id = ?",
            (flag_id,),
        ).fetchone()
    return _row_to_dict(row)


def get_active_flag_for_node(
    db: "CrawlDB", node_id: int
) -> dict[str, object] | None:
    """Return the highest-priority active flag for a node, or ``None``."""
    placeholders = ",".join("?" * len(ACTIVE_STATUSES))
    with db.read() as c:
        row = c.execute(
            f"""SELECT id, node_id, status, source, priority, note
                FROM flags
                WHERE node_id = ? AND status IN ({placeholders})
                ORDER BY priority ASC, id DESC
                LIMIT 1""",
            (node_id, *ACTIVE_STATUSES),
        ).fetchone()
    return _row_to_dict(row)


def create_flag(
    db: "CrawlDB",
    node_id: int,
    *,
    status: str = "pending",
    source: str = "analyst",
    priority: int = 2,
    note: str | None = None,
) -> int:
    """Insert a flag row. Returns the new id.

    ``source`` defaults to ``analyst`` — the watchlist auto-flagger uses
    :func:`insert_watchlist_flag` instead of this path.

    Raises ``ValueError`` with ``bad_status`` / ``bad_source`` /
    ``bad_priority`` / ``unknown_node`` codes — the route layer maps those to
    HTTP statuses.
    """
    if status not in VALID_STATUSES:
        raise ValueError("bad_status")
    if source not in VALID_SOURCES:
        raise ValueError("bad_source")
    if priority not in VALID_PRIORITIES:
        raise ValueError("bad_priority")
    with db.transaction(immediate=True) as c:
        if not _node_exists(c, node_id):
            raise ValueError("unknown_node")
        cur = c.execute(
            "INSERT INTO flags(node_id, status, source, priority, note) "
            "VALUES (?, ?, ?, ?, ?)",
            (node_id, status, source, priority, note),
        )
        return int(cur.lastrowid)


def update_flag(
    db: "CrawlDB",
    flag_id: int,
    *,
    status: str | None = None,
    priority: int | None = None,
    note: str | None = None,
    clear_note: bool = False,
) -> dict[str, object] | None:
    """Partial update. Returns the updated row, or ``None`` if id unknown.

    ``note`` defaults to "leave alone" — pass ``clear_note=True`` to write
    NULL explicitly.
    """
    if status is not None and status not in VALID_STATUSES:
        raise ValueError("bad_status")
    if priority is not None and priority not in VALID_PRIORITIES:
        raise ValueError("bad_priority")

    sets: list[str] = []
    params: list[object] = []
    if status is not None:
        sets.append("status = ?")
        params.append(status)
    if priority is not None:
        sets.append("priority = ?")
        params.append(priority)
    if clear_note:
        sets.append("note = NULL")
    elif note is not None:
        sets.append("note = ?")
        params.append(note)

    with db.transaction(immediate=True) as c:
        if not sets:
            row = c.execute(
                "SELECT id, node_id, status, source, priority, note "
                "FROM flags WHERE id = ?",
                (flag_id,),
            ).fetchone()
            return _row_to_dict(row)
        params.append(flag_id)
        cur = c.execute(
            f"UPDATE flags SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        if cur.rowcount == 0:
            return None
        row = c.execute(
            "SELECT id, node_id, status, priority, note "
            "FROM flags WHERE id = ?",
            (flag_id,),
        ).fetchone()
    return _row_to_dict(row)


def delete_flag(db: "CrawlDB", flag_id: int) -> bool:
    with db.transaction(immediate=True) as c:
        cur = c.execute("DELETE FROM flags WHERE id = ?", (flag_id,))
        return cur.rowcount > 0


def delete_flags_for_node(db: "CrawlDB", node_id: int) -> int:
    """Clear every flag for a node. Returns the number deleted.

    Backs the right-click "Remove Flag" menu item: the frontend only
    knows the node's active ``flag_status`` (from the /api/graph payload),
    not individual flag ids, so the toggle is a node-level operation.
    """
    with db.transaction(immediate=True) as c:
        cur = c.execute("DELETE FROM flags WHERE node_id = ?", (node_id,))
        return int(cur.rowcount)


__all__ = [
    "ACTIVE_STATUSES",
    "VALID_PRIORITIES",
    "VALID_SOURCES",
    "VALID_STATUSES",
    "create_flag",
    "delete_flag",
    "delete_flags_for_node",
    "get_active_flag_for_node",
    "get_flag",
    "insert_watchlist_flag",
    "list_flags",
    "update_flag",
]
