"""v6 → v7 additive migration — the ``network`` discriminant.

I2P support adds one schema change: a ``network`` column on ``resources`` and
``search_engines`` (``'tor'`` / ``'i2p'``). The upgrade is non-destructive —
every pre-v7 row is an onion crawl, so the constant ``'tor'`` default backfills
existing rows correctly. This stands up a v6-shaped DB by hand (those two tables
without the ``network`` column, ``schema_version`` pinned at 6), opens it through
``CrawlDB``, and asserts the column is added and existing rows backfill to
``'tor'`` without disturbing their data.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.db.core import SCHEMA_VERSION, CrawlDB

# v6 shapes: current DDL minus the v7 ``network`` column. CREATE IF NOT EXISTS in
# _init_schema leaves these hand-built tables intact, so the migration's
# _ensure_column is what must add ``network``.
_V6_RESOURCES = """CREATE TABLE resources (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    url               TEXT    UNIQUE NOT NULL,
    host              TEXT    NOT NULL,
    state             TEXT    NOT NULL CHECK (state IN
        ('unknown','known','crawled','dead')),
    first_seen        TEXT    NOT NULL,
    last_seen         TEXT,
    last_state_change TEXT,
    FOREIGN KEY (host) REFERENCES domains(host) ON DELETE CASCADE
)"""

_V6_SEARCH_ENGINES = """CREATE TABLE search_engines (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT,
    url   TEXT UNIQUE NOT NULL
)"""

_V6_DOMAINS = """CREATE TABLE domains (
    host      TEXT PRIMARY KEY,
    alias     TEXT,
    last_seen TEXT
)"""

ONION_HOST = "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczyd.onion"
ONION_URL = f"http://{ONION_HOST}/"


def _build_v6_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
        conn.execute("INSERT INTO schema_version(version) VALUES (6)")
        conn.execute(_V6_DOMAINS)
        conn.execute(_V6_RESOURCES)
        conn.execute(_V6_SEARCH_ENGINES)
        conn.execute("INSERT INTO domains(host) VALUES (?)", (ONION_HOST,))
        conn.execute(
            "INSERT INTO resources(id, url, host, state, first_seen) "
            "VALUES (5, ?, ?, 'crawled', '2026-01-01T00:00:00+00:00')",
            (ONION_URL, ONION_HOST),
        )
        conn.execute(
            "INSERT INTO search_engines(id, label, url) VALUES (9, 'Ahmia', ?)",
            (f"http://{ONION_HOST}/?q={{q}}",),
        )
        conn.commit()
    finally:
        conn.close()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_v6_db_backfills_network_to_tor(tmp_path: Path) -> None:
    path = tmp_path / "legacy_v6.db"
    _build_v6_db(path)

    # Sanity: the fixture is a v6 shape with no network column before we open it.
    pre = sqlite3.connect(path)
    try:
        assert pre.execute("SELECT version FROM schema_version").fetchone()[0] == 6
        assert "network" not in _columns(pre, "resources")
        assert "network" not in _columns(pre, "search_engines")
    finally:
        pre.close()

    db = CrawlDB(path)
    try:
        conn = db._conn
        # Version stamped forward to current.
        v = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert v == SCHEMA_VERSION == 7

        # Column added on both tables.
        assert "network" in _columns(conn, "resources")
        assert "network" in _columns(conn, "search_engines")

        # Existing rows backfilled to 'tor', data otherwise untouched.
        res = conn.execute("SELECT * FROM resources WHERE id = 5").fetchone()
        assert res["network"] == "tor"
        assert res["url"] == ONION_URL
        assert res["state"] == "crawled"

        eng = conn.execute(
            "SELECT * FROM search_engines WHERE id = 9"
        ).fetchone()
        assert eng["network"] == "tor"
        assert eng["label"] == "Ahmia"
    finally:
        db.close()
