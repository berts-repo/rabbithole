"""Auto-analysis rule CRUD (item 7, decision D4).

The single typed home for auto-analysis. A rule says "when trigger X happens,
queue analyzer Y." Two trigger kinds:

* ``crawl`` — run the analyzer on every newly crawled page. (The crawl trigger
  migrates onto these rows in Phase 3; Phase 1 only stores them.)
* ``collection_add`` — run the analyzer when a page is added to the collection
  named in ``target_filter`` (``{"collection_id": N}``).

``model`` NULL falls back to the ``llm.model`` setting at fire time;
``prompt_id`` NULL means the free-form / engine-default prompt. ``target_filter``
is stored as JSON text and surfaced as a dict.

Mutations run inside ``db.transaction(immediate=True)``; reads use ``db.read()``.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .core import CrawlDB


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(r: Any) -> dict[str, Any]:
    data = {k: r[k] for k in r.keys()}
    raw = data.get("target_filter")
    data["target_filter"] = json.loads(raw) if raw else None
    return data


def list_rules(
    db: "CrawlDB",
    *,
    trigger_kind: str | None = None,
    enabled_only: bool = False,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    args: list[Any] = []
    if trigger_kind is not None:
        clauses.append("trigger_kind = ?")
        args.append(trigger_kind)
    if enabled_only:
        clauses.append("enabled = 1")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with db.read() as c:
        rows = c.execute(
            f"SELECT * FROM auto_analysis_rules {where} "
            "ORDER BY id ASC",
            args,
        ).fetchall()
    return [_row(r) for r in rows]


def get(db: "CrawlDB", rule_id: int) -> dict[str, Any] | None:
    with db.read() as c:
        row = c.execute(
            "SELECT * FROM auto_analysis_rules WHERE id = ?", (rule_id,)
        ).fetchone()
    return _row(row) if row is not None else None


def create(
    db: "CrawlDB",
    *,
    trigger_kind: str,
    analysis_type: str,
    model: str | None = None,
    prompt_id: int | None = None,
    target_filter: dict[str, Any] | None = None,
    enabled: bool = True,
) -> int:
    """Insert a rule. A bad ``trigger_kind`` trips the CHECK → ``ValueError``."""
    import sqlite3

    when = _now_iso()
    tf = json.dumps(target_filter) if target_filter is not None else None
    with db.transaction(immediate=True) as c:
        try:
            cur = c.execute(
                "INSERT INTO auto_analysis_rules"
                "(trigger_kind, analysis_type, model, prompt_id, target_filter,"
                " enabled, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (trigger_kind, analysis_type, model, prompt_id, tf,
                 1 if enabled else 0, when, when),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(str(exc)) from exc
        return int(cur.lastrowid)


def update(
    db: "CrawlDB",
    rule_id: int,
    *,
    analysis_type: str | None = None,
    model: str | None = None,
    prompt_id: int | None = None,
    target_filter: dict[str, Any] | None = None,
    enabled: bool | None = None,
) -> bool:
    fields: list[str] = []
    args: list[Any] = []
    if analysis_type is not None:
        fields.append("analysis_type = ?")
        args.append(analysis_type)
    if model is not None:
        fields.append("model = ?")
        args.append(model)
    if prompt_id is not None:
        fields.append("prompt_id = ?")
        args.append(prompt_id)
    if target_filter is not None:
        fields.append("target_filter = ?")
        args.append(json.dumps(target_filter))
    if enabled is not None:
        fields.append("enabled = ?")
        args.append(1 if enabled else 0)
    if not fields:
        return False
    fields.append("updated_at = ?")
    args.append(_now_iso())
    args.append(rule_id)
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            f"UPDATE auto_analysis_rules SET {', '.join(fields)} WHERE id = ?",
            args,
        )
        return cur.rowcount > 0


def delete(db: "CrawlDB", rule_id: int) -> bool:
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "DELETE FROM auto_analysis_rules WHERE id = ?", (rule_id,)
        )
        return cur.rowcount > 0


# Legacy ``llm.auto_enqueue.*`` suffix per crawl analysis type. The crawl
# trigger used to live in those settings; ``seed_crawl_rules`` carries their
# state onto the typed rules once (item 7, D4). After the seed the rule's
# ``enabled`` flag is the single runtime source and the setting is vestigial.
_CRAWL_SETTING_SUFFIX: dict[str, str] = {
    "Summary": "summary",
    "Category": "category",
    "Domain Label": "domain_label",
    "Entities (LLM)": "entities_llm",
    "Risk Score": "risk_score",
}


def seed_crawl_rules(db: "CrawlDB") -> None:
    """Idempotently ensure one ``crawl`` rule per auto-enqueue type (item 7, D4).

    Enabled state is carried from the legacy ``llm.auto_enqueue.*`` setting at
    first seed so crawl auto-enqueue fires identically before/after the
    migration onto rules. No-ops once a ``crawl`` rule for a type already
    exists, so later analyst toggles in the Intel UI are never clobbered.
    """
    from ..prompts import AUTO_ENQUEUE_TYPES
    from .settings import get_setting

    existing = {
        str(r["analysis_type"]) for r in list_rules(db, trigger_kind="crawl")
    }
    for analysis_type in AUTO_ENQUEUE_TYPES:
        if analysis_type in existing:
            continue
        suffix = _CRAWL_SETTING_SUFFIX.get(analysis_type, "")
        legacy = get_setting(db, f"llm.auto_enqueue.{suffix}") if suffix else None
        enabled = (legacy or "").strip().lower() == "true"
        create(db, trigger_kind="crawl", analysis_type=analysis_type, enabled=enabled)


def rules_for_collection_add(
    db: "CrawlDB", collection_id: int
) -> list[dict[str, Any]]:
    """Enabled ``collection_add`` rules targeting ``collection_id``.

    Matched on ``json_extract(target_filter, '$.collection_id')`` so the filter
    lives in one place. Used by the collection-add hook (Phase 1 wiring).
    """
    with db.read() as c:
        rows = c.execute(
            "SELECT * FROM auto_analysis_rules "
            "WHERE trigger_kind = 'collection_add' AND enabled = 1 "
            "  AND json_extract(target_filter, '$.collection_id') = ? "
            "ORDER BY id ASC",
            (collection_id,),
        ).fetchall()
    return [_row(r) for r in rows]


__all__ = [
    "create",
    "delete",
    "get",
    "list_rules",
    "rules_for_collection_add",
    "seed_crawl_rules",
    "update",
]
