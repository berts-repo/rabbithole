"""Label taxonomy — managed tags for resources and domains (item 11).

Two concepts share one UI panel but stay separate in the data model (decision
D2): **rename** (1:1 alias, lives on ``domains.alias`` / ``pages.alias``) and
**label** (N:M tag, here). This module owns the label taxonomy and the two
typed join tables:

- ``labels`` — the managed taxonomy. Presets ship ``builtin=1`` (recolorable /
  hideable, never deletable); analyst labels are ``builtin=0`` and fully
  editable. ``rank`` is the single analyst-controlled ordering (decision D5)
  that later resolves collapse-home, dominant-label color, and picker order —
  lower number ranks higher.
- ``resource_labels`` / ``domain_labels`` — attachment, FK-cascaded so deleting
  a label or its target wipes the attachment row.

The seed lives in ``core.py`` (``PRESET_LABELS`` + ``_seed_preset_labels``)
alongside the schema it seeds, mirroring ``PRESET_PROMPTS``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .core import CrawlDB


LABEL_NAME_MAX = 64
COLOR_MAX = 32
DESCRIPTION_MAX = 512


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_name(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        raise ValueError("empty_name")
    if len(stripped) > LABEL_NAME_MAX:
        raise ValueError("name_too_long")
    return stripped


def _row_to_label(r: Any) -> dict[str, Any]:
    return {
        "id": int(r["id"]),
        "name": r["name"],
        "color": r["color"],
        "description": r["description"],
        "builtin": bool(r["builtin"]),
        "rank": int(r["rank"]),
        "hidden": bool(r["hidden"]),
    }


def list_labels(
    db: "CrawlDB", *, include_hidden: bool = True
) -> list[dict[str, Any]]:
    """All labels in rank order, each with resource + domain member counts.

    ``include_hidden=False`` drops presets the analyst hid from the picker
    (``hidden=1``); the bottom-pane tab and settings show everything, the apply
    picker hides them. Counts are computed at query time via correlated
    subqueries over the join tables — the schema stores no denormalized tally.
    """
    where = "" if include_hidden else "WHERE l.hidden = 0"
    with db.read() as c:
        rows = c.execute(
            f"""SELECT l.id, l.name, l.color, l.description, l.builtin,
                       l.rank, l.hidden,
                       (SELECT COUNT(*) FROM resource_labels rl
                         WHERE rl.label_id = l.id) AS resource_count,
                       (SELECT COUNT(*) FROM domain_labels dl
                         WHERE dl.label_id = l.id) AS domain_count
                  FROM labels l
                  {where}
                 ORDER BY l.rank ASC, l.name COLLATE NOCASE ASC""",
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        label = _row_to_label(r)
        label["resource_count"] = int(r["resource_count"])
        label["domain_count"] = int(r["domain_count"])
        out.append(label)
    return out


def get_label(db: "CrawlDB", label_id: int) -> dict[str, Any] | None:
    with db.read() as c:
        row = c.execute(
            "SELECT id, name, color, description, builtin, rank, hidden "
            "FROM labels WHERE id = ?",
            (label_id,),
        ).fetchone()
    return None if row is None else _row_to_label(row)


def create_label(
    db: "CrawlDB",
    *,
    name: str,
    color: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a custom (``builtin=0``) label. Returns the new label dict.

    New labels rank at the bottom of the list (``max(rank) + 1``) so seeding /
    creation never displaces the analyst's existing ordering. Raises
    ``ValueError('duplicate_name')`` on a name clash (UNIQUE), ``'empty_name'``
    / ``'name_too_long'`` on a bad name.
    """
    cleaned = _clean_name(name)
    with db.transaction(immediate=True) as c:
        clash = c.execute(
            "SELECT 1 FROM labels WHERE name = ?", (cleaned,)
        ).fetchone()
        if clash is not None:
            raise ValueError("duplicate_name")
        next_rank = int(
            c.execute("SELECT COALESCE(MAX(rank), -1) + 1 AS r FROM labels")
            .fetchone()["r"]
        )
        cur = c.execute(
            "INSERT INTO labels"
            "(name, color, description, builtin, rank, hidden, created_at) "
            "VALUES (?, ?, ?, 0, ?, 0, ?)",
            (cleaned, color, description, next_rank, _now()),
        )
        label_id = int(cur.lastrowid)
    result = get_label(db, label_id)
    assert result is not None
    return result


def update_label(
    db: "CrawlDB",
    label_id: int,
    *,
    name: str,
    color: str | None,
    description: str | None,
    hidden: bool,
) -> dict[str, Any] | None:
    """Update a label's name / color / description / hidden flag.

    Returns the updated label dict, or ``None`` if the id is unknown. Presets
    (``builtin=1``) can be recolored, redescribed, and hidden but **not
    renamed** (decision D3) — a name change on a preset raises
    ``ValueError('builtin_rename')``. A clash with another label's name raises
    ``ValueError('duplicate_name')``. ``rank`` is not set here; it is owned by
    :func:`reorder`.
    """
    cleaned = _clean_name(name)
    with db.transaction(immediate=True) as c:
        existing = c.execute(
            "SELECT name, builtin FROM labels WHERE id = ?", (label_id,)
        ).fetchone()
        if existing is None:
            return None
        if bool(existing["builtin"]) and cleaned != existing["name"]:
            raise ValueError("builtin_rename")
        clash = c.execute(
            "SELECT 1 FROM labels WHERE name = ? AND id != ?",
            (cleaned, label_id),
        ).fetchone()
        if clash is not None:
            raise ValueError("duplicate_name")
        c.execute(
            "UPDATE labels SET name = ?, color = ?, description = ?, hidden = ? "
            "WHERE id = ?",
            (cleaned, color, description, 1 if hidden else 0, label_id),
        )
    return get_label(db, label_id)


def delete_label(db: "CrawlDB", label_id: int) -> bool:
    """Delete a custom label. Returns ``True`` if a row was removed.

    Cascade on the join tables wipes all attachments. Presets cannot be deleted
    (decision D3) — a delete of a ``builtin=1`` label raises
    ``ValueError('builtin_undeletable')``.
    """
    with db.transaction(immediate=True) as c:
        existing = c.execute(
            "SELECT builtin FROM labels WHERE id = ?", (label_id,)
        ).fetchone()
        if existing is None:
            return False
        if bool(existing["builtin"]):
            raise ValueError("builtin_undeletable")
        cur = c.execute("DELETE FROM labels WHERE id = ?", (label_id,))
        return cur.rowcount > 0


def reorder(db: "CrawlDB", ordered_ids: list[int]) -> None:
    """Write ``rank`` from list position — ``ordered_ids[0]`` ranks highest.

    The analyst's drag-to-reorder list *is* the ranking (decision D5). Any label
    not named keeps its row but is pushed below the named ones, preserving its
    relative order, so a partial list (e.g. only the picker-visible labels) is
    safe. Unknown ids are ignored.
    """
    with db.transaction(immediate=True) as c:
        valid = {
            int(r["id"]) for r in c.execute("SELECT id FROM labels")
        }
        rank = 0
        seen: set[int] = set()
        for lid in ordered_ids:
            if lid in valid and lid not in seen:
                c.execute(
                    "UPDATE labels SET rank = ? WHERE id = ?", (rank, lid)
                )
                seen.add(lid)
                rank += 1
        # Append every label the caller didn't name, keeping their prior order.
        for r in c.execute(
            "SELECT id FROM labels WHERE id NOT IN "
            "(SELECT value FROM json_each(?)) ORDER BY rank, name COLLATE NOCASE",
            (_json_ids(seen),),
        ):
            c.execute(
                "UPDATE labels SET rank = ? WHERE id = ?", (rank, int(r["id"]))
            )
            rank += 1


def _json_ids(ids: set[int]) -> str:
    import json

    return json.dumps(sorted(ids))


# --- attachment: resources -------------------------------------------------


def attach_resource(db: "CrawlDB", label_id: int, resource_id: int) -> bool:
    """Attach ``label_id`` to a resource. Returns ``True`` if newly attached.

    Idempotent: re-attaching an existing pair is a no-op returning ``False``.
    Raises ``ValueError('unknown_label')`` / ``'unknown_resource'`` if either
    side is missing (FK would raise an opaque IntegrityError otherwise).
    """
    with db.transaction(immediate=True) as c:
        _require(c, "labels", "id", label_id, "unknown_label")
        _require(c, "resources", "id", resource_id, "unknown_resource")
        cur = c.execute(
            "INSERT OR IGNORE INTO resource_labels(label_id, resource_id) "
            "VALUES (?, ?)",
            (label_id, resource_id),
        )
        return cur.rowcount > 0


def detach_resource(db: "CrawlDB", label_id: int, resource_id: int) -> bool:
    """Remove the label↔resource attachment. ``True`` if a row was removed."""
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "DELETE FROM resource_labels WHERE label_id = ? AND resource_id = ?",
            (label_id, resource_id),
        )
        return cur.rowcount > 0


# --- attachment: domains ---------------------------------------------------


def attach_domain(db: "CrawlDB", label_id: int, host: str) -> bool:
    """Attach ``label_id`` to a domain. Returns ``True`` if newly attached."""
    with db.transaction(immediate=True) as c:
        _require(c, "labels", "id", label_id, "unknown_label")
        _require(c, "domains", "host", host, "unknown_domain")
        cur = c.execute(
            "INSERT OR IGNORE INTO domain_labels(label_id, host) VALUES (?, ?)",
            (label_id, host),
        )
        return cur.rowcount > 0


def detach_domain(db: "CrawlDB", label_id: int, host: str) -> bool:
    """Remove the label↔domain attachment. ``True`` if a row was removed."""
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "DELETE FROM domain_labels WHERE label_id = ? AND host = ?",
            (label_id, host),
        )
        return cur.rowcount > 0


# --- membership reads ------------------------------------------------------
#
# The read side of attachment, for chips / picker / graph payload. Ids only,
# rank-ordered — the frontend catalog store resolves id → name/color, so label
# appearance has one source of truth and never goes stale on a recolor. The
# bulk variants back ``build_payload`` (one query each instead of N).


def resource_label_ids(db: "CrawlDB", resource_id: int) -> list[int]:
    """Label ids directly attached to one resource, highest rank first."""
    with db.read() as c:
        rows = c.execute(
            """SELECT rl.label_id FROM resource_labels rl
                 JOIN labels l ON l.id = rl.label_id
                WHERE rl.resource_id = ?
                ORDER BY l.rank ASC, l.name COLLATE NOCASE ASC""",
            (resource_id,),
        ).fetchall()
    return [int(r["label_id"]) for r in rows]


def domain_label_ids(db: "CrawlDB", host: str) -> list[int]:
    """Label ids attached to one domain, highest rank first."""
    with db.read() as c:
        rows = c.execute(
            """SELECT dl.label_id FROM domain_labels dl
                 JOIN labels l ON l.id = dl.label_id
                WHERE dl.host = ?
                ORDER BY l.rank ASC, l.name COLLATE NOCASE ASC""",
            (host,),
        ).fetchall()
    return [int(r["label_id"]) for r in rows]


def all_resource_label_ids(db: "CrawlDB") -> dict[int, list[int]]:
    """Every resource → its directly-attached label ids (rank order)."""
    with db.read() as c:
        rows = c.execute(
            """SELECT rl.resource_id, rl.label_id FROM resource_labels rl
                 JOIN labels l ON l.id = rl.label_id
                ORDER BY l.rank ASC, l.name COLLATE NOCASE ASC"""
        ).fetchall()
    out: dict[int, list[int]] = {}
    for r in rows:
        out.setdefault(int(r["resource_id"]), []).append(int(r["label_id"]))
    return out


def all_domain_label_ids(db: "CrawlDB") -> dict[str, list[int]]:
    """Every host → its attached label ids (rank order)."""
    with db.read() as c:
        rows = c.execute(
            """SELECT dl.host, dl.label_id FROM domain_labels dl
                 JOIN labels l ON l.id = dl.label_id
                ORDER BY l.rank ASC, l.name COLLATE NOCASE ASC"""
        ).fetchall()
    out: dict[str, list[int]] = {}
    for r in rows:
        out.setdefault(r["host"], []).append(int(r["label_id"]))
    return out


def label_members(db: "CrawlDB", label_id: int) -> dict[str, Any]:
    """The resources + domains attached to one label, for the bottom-pane
    Labels tab's expand row.

    Resources carry enough to render a row and drive selection: ``id`` is the
    graph node id (``resources.id``), plus url, host, the page alias (the
    analyst's rename) and current title. Domains carry host + alias. Both are
    ordered for a stable list — resources by url, domains by host.
    """
    with db.read() as c:
        resources = c.execute(
            """SELECT r.id, r.url, r.host, p.alias AS alias, pv.title AS title
                 FROM resource_labels rl
                 JOIN resources r ON r.id = rl.resource_id
                 LEFT JOIN pages p ON p.resource_id = r.id
                 LEFT JOIN page_versions pv ON pv.id = p.current_version_id
                WHERE rl.label_id = ?
                ORDER BY r.url COLLATE NOCASE ASC""",
            (label_id,),
        ).fetchall()
        domains = c.execute(
            """SELECT d.host, d.alias
                 FROM domain_labels dl
                 JOIN domains d ON d.host = dl.host
                WHERE dl.label_id = ?
                ORDER BY d.host COLLATE NOCASE ASC""",
            (label_id,),
        ).fetchall()
    return {
        "resources": [
            {
                "id": int(r["id"]),
                "url": r["url"],
                "host": r["host"],
                "alias": r["alias"],
                "title": r["title"],
            }
            for r in resources
        ],
        "domains": [{"host": d["host"], "alias": d["alias"]} for d in domains],
    }


def _require(c: Any, table: str, key: str, value: Any, err: str) -> None:
    if c.execute(
        f"SELECT 1 FROM {table} WHERE {key} = ?", (value,)
    ).fetchone() is None:
        raise ValueError(err)


__all__ = [
    "COLOR_MAX",
    "DESCRIPTION_MAX",
    "LABEL_NAME_MAX",
    "all_domain_label_ids",
    "all_resource_label_ids",
    "attach_domain",
    "attach_resource",
    "create_label",
    "delete_label",
    "detach_domain",
    "detach_resource",
    "domain_label_ids",
    "get_label",
    "label_members",
    "list_labels",
    "reorder",
    "resource_label_ids",
    "update_label",
]
