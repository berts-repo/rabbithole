"""Analysis / Intel pane (item 7) — v4 → v5 additive migration (hard gate).

The schema-reset cutover (→ v4) was a deliberate DB delete. The analysis-intel
work (→ v5) is the opposite: an *additive*, non-destructive migration. This
test stands up a v4-shaped DB by hand (the pre-v5 ``analyses`` /
``collection_analyses`` tables without the ``prompt_id`` column, no
analysis-intel tables, ``schema_version`` pinned at 4), opens it with
``CrawlDB``, and asserts the upgrade adds the new tables + columns and seeds the
builtins **without touching existing rows**.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.db.core import PRESET_PROMPTS, SCHEMA_VERSION, CrawlDB


# v4 shape: exactly the current `analyses` DDL minus the v5 `prompt_id` column,
# and without the REFERENCES clause so the fixture needs no companion tables.
_V4_ANALYSES = """CREATE TABLE analyses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id   INTEGER NOT NULL,
    analysis_type TEXT    NOT NULL,
    model         TEXT,
    result        TEXT,
    question      TEXT,
    priority      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT,
    updated_at    TEXT
)"""

_V4_COLLECTION_ANALYSES = """CREATE TABLE collection_analyses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL,
    analysis_type TEXT    NOT NULL,
    model         TEXT,
    result        TEXT,
    created_at    TEXT,
    updated_at    TEXT
)"""


def _build_v4_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
        conn.execute("INSERT INTO schema_version(version) VALUES (4)")
        conn.execute(_V4_ANALYSES)
        conn.execute(_V4_COLLECTION_ANALYSES)
        # A pre-existing analysis row that must survive the upgrade untouched.
        conn.execute(
            "INSERT INTO analyses(id, resource_id, analysis_type, model, result) "
            "VALUES (42, 7, 'Summary', 'qwen2.5:3b', 'legacy result')"
        )
        conn.commit()
    finally:
        conn.close()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_v4_db_upgrades_to_v5_additively(tmp_path: Path) -> None:
    path = tmp_path / "legacy_v4.db"
    _build_v4_db(path)

    # Sanity: the fixture really is a v4 shape before we open it.
    pre = sqlite3.connect(path)
    try:
        assert pre.execute("SELECT version FROM schema_version").fetchone()[0] == 4
        assert "prompt_id" not in _columns(pre, "analyses")
        existing = {
            r[0] for r in pre.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "prompt_templates" not in existing
        assert "cluster_analyses" not in existing
    finally:
        pre.close()

    # Opening through CrawlDB runs the migration.
    db = CrawlDB(path)
    try:
        conn = db._conn

        # Version stamped forward.
        # A v4 DB now migrates straight to current in one additive pass
        # (v5 prompt_id columns + v6 label tables / pages.alias + v7
        # resources/search_engines.network).
        v = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert v == SCHEMA_VERSION == 7

        # New tables created.
        tables = {
            r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"prompt_templates", "auto_analysis_rules", "cluster_analyses"} <= tables

        # prompt_id backfilled onto the pre-existing analysis tables (nullable).
        assert "prompt_id" in _columns(conn, "analyses")
        assert "prompt_id" in _columns(conn, "collection_analyses")

        # Existing data preserved verbatim, with the new column defaulting NULL.
        row = conn.execute("SELECT * FROM analyses WHERE id = 42").fetchone()
        assert row["resource_id"] == 7
        assert row["result"] == "legacy result"
        assert row["prompt_id"] is None

        # Builtins seeded exactly once.
        seeded = conn.execute(
            "SELECT COUNT(*) FROM prompt_templates WHERE builtin = 1"
        ).fetchone()[0]
        assert seeded == len(PRESET_PROMPTS)
    finally:
        db.close()


def test_reopen_is_idempotent(tmp_path: Path) -> None:
    """Re-opening an already-migrated DB is a no-op: no duplicate builtins, no error."""
    path = tmp_path / "legacy_v4.db"
    _build_v4_db(path)

    CrawlDB(path).close()  # first open migrates
    db = CrawlDB(path)  # second open must not re-seed or re-migrate
    try:
        seeded = db._conn.execute(
            "SELECT COUNT(*) FROM prompt_templates WHERE builtin = 1"
        ).fetchone()[0]
        assert seeded == len(PRESET_PROMPTS)
        assert db._conn.execute(
            "SELECT version FROM schema_version"
        ).fetchone()[0] == SCHEMA_VERSION
    finally:
        db.close()
