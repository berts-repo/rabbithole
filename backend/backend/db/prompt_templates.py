"""Prompt-template CRUD (item 7, decision D3).

Named analyzer prompts, project-local. Built-in presets (``builtin=1``) are
seeded by ``core._seed_preset_prompts``; they can be hidden but not deleted.
Analyst templates (``builtin=0``) are fully editable and removable. A template
is just instruction text plus the ``analysis_type`` it targets — a NULL
``prompt_id`` on an analysis still means the free-form / engine-default prompt,
so templates are an opt-in convenience layered on top of the existing flow.

Every mutation runs inside ``db.transaction(immediate=True)``. Reads use
``db.read()`` per the DB-access seam.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .core import CrawlDB


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(r: Any) -> dict[str, Any]:
    return {k: r[k] for k in r.keys()}


def list_templates(
    db: "CrawlDB", *, include_hidden: bool = False
) -> list[dict[str, Any]]:
    """All templates ordered builtins-first, then by name.

    Hidden builtins are excluded unless ``include_hidden`` is set (the manage
    view passes it so the analyst can un-hide a preset).
    """
    clause = "" if include_hidden else "WHERE hidden = 0"
    with db.read() as c:
        rows = c.execute(
            f"SELECT * FROM prompt_templates {clause} "
            "ORDER BY builtin DESC, name ASC, id ASC"
        ).fetchall()
    return [_row(r) for r in rows]


def get(db: "CrawlDB", template_id: int) -> dict[str, Any] | None:
    with db.read() as c:
        row = c.execute(
            "SELECT * FROM prompt_templates WHERE id = ?", (template_id,)
        ).fetchone()
    return _row(row) if row is not None else None


def create(
    db: "CrawlDB", *, name: str, analysis_type: str, body: str
) -> int:
    """Insert an analyst template (``builtin=0``). Returns the new id."""
    when = _now_iso()
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "INSERT INTO prompt_templates"
            "(name, analysis_type, body, builtin, hidden, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, 0, ?, ?)",
            (name, analysis_type, body, when, when),
        )
        return int(cur.lastrowid)


def update(
    db: "CrawlDB",
    template_id: int,
    *,
    name: str | None = None,
    analysis_type: str | None = None,
    body: str | None = None,
) -> bool:
    """Patch editable fields of a template.

    Built-in presets cannot have their text edited (``name`` /
    ``analysis_type`` / ``body``) — use :func:`set_hidden` to manage their
    visibility instead. Returns False for an unknown or builtin row when text
    fields are supplied.
    """
    fields: list[str] = []
    args: list[Any] = []
    if name is not None:
        fields.append("name = ?")
        args.append(name)
    if analysis_type is not None:
        fields.append("analysis_type = ?")
        args.append(analysis_type)
    if body is not None:
        fields.append("body = ?")
        args.append(body)
    if not fields:
        return False
    fields.append("updated_at = ?")
    args.append(_now_iso())
    args.append(template_id)
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            f"UPDATE prompt_templates SET {', '.join(fields)} "
            "WHERE id = ? AND builtin = 0",
            args,
        )
        return cur.rowcount > 0


def clone(db: "CrawlDB", template_id: int, *, name: str) -> int | None:
    """Copy any template (builtin or not) into a new editable analyst template."""
    src = get(db, template_id)
    if src is None:
        return None
    return create(
        db,
        name=name,
        analysis_type=str(src["analysis_type"]),
        body=str(src["body"]),
    )


def set_hidden(db: "CrawlDB", template_id: int, hidden: bool) -> bool:
    """Hide/un-hide a template. The only mutation allowed on builtins."""
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "UPDATE prompt_templates SET hidden = ?, updated_at = ? WHERE id = ?",
            (1 if hidden else 0, _now_iso(), template_id),
        )
        return cur.rowcount > 0


def delete(db: "CrawlDB", template_id: int) -> bool:
    """Delete an analyst template. Built-in presets are refused (hide instead)."""
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "DELETE FROM prompt_templates WHERE id = ? AND builtin = 0",
            (template_id,),
        )
        return cur.rowcount > 0


__all__ = [
    "clone",
    "create",
    "delete",
    "get",
    "list_templates",
    "set_hidden",
    "update",
]
