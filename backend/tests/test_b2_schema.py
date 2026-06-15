"""Phase B2 (schema-reset v4) — schema, FTS5, sqlite-vec, FK cascades, defaults.

Rewritten for the schema-reset cutover: the god ``nodes`` table is gone,
replaced by ``resources`` / ``pages`` / ``page_versions``; ``entities`` and
``notes`` fold into ``findings``; all work-tracking lives in one ``jobs``
table. This file is the schema lock — it asserts the v4 surface directly.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import sqlite_vec

from backend.db import page_versions as versions_db
from backend.db.core import (
    DEFAULT_SETTINGS,
    EMBED_DIM,
    EXPECTED_TABLES,
    SCHEMA_VERSION,
    CrawlDB,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_tables(db: CrawlDB) -> set[str]:
    return {
        r[0] for r in db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _all_indices(db: CrawlDB) -> set[str]:
    return {
        r[0] for r in db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name NOT LIKE 'sqlite_%'"
        )
    }


def _host(url: str) -> str:
    return url.split("//", 1)[1].split("/", 1)[0]


def _make_resource(
    db: CrawlDB, url: str = "http://aaa.onion", body: str = "hello world"
) -> tuple[int, int]:
    """Crawl ``url`` once → ``(resource_id, version_id)``.

    Exercises the real crawl-write path (resource + page + version + manual
    pages_fts maintenance), so it stands in for the old raw ``INSERT INTO
    nodes`` helper.
    """
    return versions_db.record_fetch(
        db,
        url=url,
        host=_host(url),
        status_code=200,
        title="t",
        body_text=body,
        body_text_clean=body,
        response_headers={},
        when="2026-01-01T00:00:00+00:00",
    )


def _page_id(db: CrawlDB, resource_id: int) -> int:
    return db._conn.execute(
        "SELECT id FROM pages WHERE resource_id=?", (resource_id,)
    ).fetchone()[0]


# ---------------------------------------------------------------------------
# 1. Idempotent init
# ---------------------------------------------------------------------------

def test_init_is_idempotent(db_path: Path) -> None:
    a = CrawlDB(db_path)
    tables_first = _all_tables(a)
    indices_first = _all_indices(a)
    a.close()

    b = CrawlDB(db_path)
    assert _all_tables(b) == tables_first
    assert _all_indices(b) == indices_first
    # Still exactly one schema_version row.
    assert b._conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 1
    b.close()


# ---------------------------------------------------------------------------
# 2. PRAGMAs
# ---------------------------------------------------------------------------

def test_wal_and_fk_pragmas(db: CrawlDB) -> None:
    assert db._conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert db._conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# 3. Expected tables present
# ---------------------------------------------------------------------------

def test_all_expected_tables_present(db: CrawlDB) -> None:
    tables = _all_tables(db)
    assert EXPECTED_TABLES.issubset(tables), EXPECTED_TABLES - tables
    # The dropped tables must be gone.
    for gone in ("nodes", "entities", "notes", "crawl_queue", "nodes_fts"):
        assert gone not in tables, f"{gone} should have been dropped"
    # pages_fts (contentless FTS5) + embeddings (vec0) show up in sqlite_master.
    assert "pages_fts" in tables
    assert "embeddings" in tables


# ---------------------------------------------------------------------------
# 4. Expected indices present
# ---------------------------------------------------------------------------

REQUIRED_INDICES = {
    "idx_resources_host",
    "idx_resources_state",
    "idx_resources_last_seen",
    "page_versions_page_idx",
    "idx_graph_nodes_cluster",
    "idx_response_headers_kv",
    "idx_edges_from",
    "idx_edges_to",
    "idx_findings_resource",
    "idx_findings_kind",
    "idx_collection_items_node",
    "idx_crawl_nodes_node",
    "idx_probes_monitor",
    "idx_analyses_resource",
    "idx_flags_status",
    "idx_flags_node",
    "jobs_status_idx",
    "jobs_kind_idx",
}


def test_required_indices_present(db: CrawlDB) -> None:
    indices = _all_indices(db)
    missing = REQUIRED_INDICES - indices
    assert not missing, f"missing indices: {missing}"
    # No leftover indices on the dropped tables.
    for stale in ("idx_nodes_domain", "idx_nodes_stub", "idx_entities_node",
                  "idx_notes_node", "idx_analyses_status"):
        assert stale not in indices, f"{stale} should have been dropped"


# ---------------------------------------------------------------------------
# 5. FK cascade — resource delete wipes children
# ---------------------------------------------------------------------------

def test_resource_delete_cascades(db: CrawlDB) -> None:
    rid, vid = _make_resource(db)
    with db.transaction() as c:
        c.execute(
            "INSERT INTO edges(from_id, to_id, source) VALUES (?, ?, 'crawl')",
            (rid, rid),
        )
        c.execute(
            "INSERT INTO findings(resource_id, kind, value, metadata) "
            "VALUES (?, 'entity', 'x@y.onion', json_object('type','email','source','crawl'))",
            (rid,),
        )
        c.execute(
            "INSERT INTO findings(resource_id, kind, value) VALUES (?, 'note', 'n')",
            (rid,),
        )
        c.execute(
            "INSERT INTO flags(node_id, status, source, priority) "
            "VALUES (?, 'pending', 'analyst', 1)",
            (rid,),
        )
        c.execute(
            "INSERT INTO analyses(resource_id, analysis_type) VALUES (?, 'Summary')",
            (rid,),
        )
        c.execute(
            "INSERT INTO response_headers(page_version_id, key, value) "
            "VALUES (?, 'Server', 'nginx')",
            (vid,),
        )

    with db.transaction() as c:
        c.execute("DELETE FROM resources WHERE id=?", (rid,))

    edge_count = db._conn.execute(
        "SELECT COUNT(*) FROM edges WHERE from_id=? OR to_id=?", (rid, rid)
    ).fetchone()[0]
    assert edge_count == 0, "edges still reference deleted resource"

    for table in ("findings", "flags", "analyses"):
        col = "node_id" if table == "flags" else "resource_id"
        count = db._conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {col}=?", (rid,)
        ).fetchone()[0]
        assert count == 0, f"{table} still has rows for resource {rid}"

    # pages / page_versions / response_headers cascade off resources too.
    assert db._conn.execute(
        "SELECT COUNT(*) FROM pages WHERE resource_id=?", (rid,)
    ).fetchone()[0] == 0
    assert db._conn.execute(
        "SELECT COUNT(*) FROM page_versions WHERE id=?", (vid,)
    ).fetchone()[0] == 0
    assert db._conn.execute(
        "SELECT COUNT(*) FROM response_headers WHERE page_version_id=?", (vid,)
    ).fetchone()[0] == 0


# ---------------------------------------------------------------------------
# 6. FK cascade — collection delete: items CASCADE, crawls SET NULL
# ---------------------------------------------------------------------------

def test_collection_delete_cascades_and_set_null(db: CrawlDB) -> None:
    rid, _ = _make_resource(db, url="http://col.onion")
    with db.transaction() as c:
        cur = c.execute("INSERT INTO collections(name) VALUES ('mycoll')")
        coll_id = cur.lastrowid
        c.execute(
            "INSERT INTO collection_items(collection_id, node_id) VALUES (?, ?)",
            (coll_id, rid),
        )
        cur = c.execute(
            "INSERT INTO crawls(seed_url, mode, collection_id) "
            "VALUES ('http://seed.onion', 'BFS', ?)",
            (coll_id,),
        )
        crawl_id = cur.lastrowid

    with db.transaction() as c:
        c.execute("DELETE FROM collections WHERE id=?", (coll_id,))

    items_left = db._conn.execute(
        "SELECT COUNT(*) FROM collection_items WHERE collection_id=?", (coll_id,)
    ).fetchone()[0]
    assert items_left == 0, "collection_items rows should CASCADE"

    crawl_coll = db._conn.execute(
        "SELECT collection_id FROM crawls WHERE id=?", (crawl_id,)
    ).fetchone()[0]
    assert crawl_coll is None, "crawls.collection_id should be SET NULL"


# ---------------------------------------------------------------------------
# 7. CHECK constraints fire
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "sql, params",
    [
        # resources.state enum
        (
            "INSERT INTO resources(url, host, state, first_seen) "
            "VALUES ('http://x.onion', 'x.onion', 'banana', '2026-01-01')",
            (),
        ),
        # edges.source enum
        ("INSERT INTO edges(from_id, to_id, source) VALUES (?, ?, 'ai')", (1, 1)),
        # flags enums
        ("INSERT INTO flags(node_id, status, priority) VALUES (?, 'pending', 5)", (1,)),
        ("INSERT INTO flags(node_id, status, priority) VALUES (?, 'banana', 1)", (1,)),
        # crawls.mode enum (status column is gone)
        (
            "INSERT INTO crawls(seed_url, mode) VALUES ('http://x.onion', 'Telepathy')",
            (),
        ),
        # findings.kind enum
        ("INSERT INTO findings(resource_id, kind, value) VALUES (?, 'banana', 'x')", (1,)),
        # jobs enums
        (
            "INSERT INTO jobs(kind, target_type, target_id, status) "
            "VALUES ('banana', 'url', 1, 'pending')",
            (),
        ),
        (
            "INSERT INTO jobs(kind, target_type, target_id, status) "
            "VALUES ('crawl', 'banana', 1, 'pending')",
            (),
        ),
        (
            "INSERT INTO jobs(kind, target_type, target_id, status) "
            "VALUES ('crawl', 'url', 1, 'banana')",
            (),
        ),
    ],
)
def test_check_constraints_fire(db: CrawlDB, sql: str, params: tuple) -> None:
    _make_resource(db)  # so resource_id=1 exists for FK satisfaction
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction() as c:
            c.execute(sql, params)


# ---------------------------------------------------------------------------
# 8. FTS5 insert + match (contentless pages_fts, maintained by the crawl write)
# ---------------------------------------------------------------------------

def test_fts5_insert_and_match(db: CrawlDB) -> None:
    rid_a, _ = _make_resource(db, url="http://a.onion", body="red panda lives in nepal")
    _make_resource(db, url="http://b.onion", body="blue whale lives in ocean")
    page_a = _page_id(db, rid_a)

    hits = [
        r[0]
        for r in db._conn.execute(
            "SELECT rowid FROM pages_fts WHERE pages_fts MATCH 'panda'"
        )
    ]
    assert hits == [page_a]

    # Re-crawl page a with new text → the manual FTS maintenance in the crawl
    # write txn swaps the indexed text: old term drops, new term matches.
    _make_resource(db, url="http://a.onion", body="aurora borealis")
    panda_hits = list(
        db._conn.execute("SELECT rowid FROM pages_fts WHERE pages_fts MATCH 'panda'")
    )
    aurora_hits = list(
        db._conn.execute("SELECT rowid FROM pages_fts WHERE pages_fts MATCH 'aurora'")
    )
    assert panda_hits == []
    assert [r[0] for r in aurora_hits] == [page_a]


# ---------------------------------------------------------------------------
# 9. Re-crawl header prune rule (D5: keep only the current version's headers)
# ---------------------------------------------------------------------------

def test_recrawl_prunes_prior_version_headers(db: CrawlDB) -> None:
    url = "http://hdr.onion"
    rid, v1 = versions_db.record_fetch(
        db, url=url, host=_host(url), status_code=200, title="t",
        body_text="a", body_text_clean="a",
        response_headers={"Server": "nginx", "X-Powered-By": "PHP/7"},
        when="2026-01-01T00:00:00+00:00",
    )
    _, v2 = versions_db.record_fetch(
        db, url=url, host=_host(url), status_code=200, title="t",
        body_text="b", body_text_clean="b",
        response_headers={"Server": "apache", "Content-Type": "text/html"},
        when="2026-01-02T00:00:00+00:00",
    )
    assert v2 != v1

    v1_rows = db._conn.execute(
        "SELECT COUNT(*) FROM response_headers WHERE page_version_id=?", (v1,)
    ).fetchone()[0]
    assert v1_rows == 0, "prior version's headers should be pruned on re-crawl"

    v2_rows = {
        r["key"]: r["value"]
        for r in db._conn.execute(
            "SELECT key, value FROM response_headers WHERE page_version_id=?", (v2,)
        )
    }
    assert v2_rows == {"Server": "apache", "Content-Type": "text/html"}


# ---------------------------------------------------------------------------
# 10. sqlite-vec loaded + roundtrip (embeddings keyed page_id)
# ---------------------------------------------------------------------------

def test_sqlite_vec_loaded_and_insert(db: CrawlDB) -> None:
    version = db._conn.execute("SELECT vec_version()").fetchone()[0]
    assert version.startswith("v")

    rid, _ = _make_resource(db)
    page_id = _page_id(db, rid)
    blob = sqlite_vec.serialize_float32([0.1] * EMBED_DIM)
    with db.transaction() as c:
        c.execute(
            "INSERT INTO embeddings(page_id, vector, model, created_at) "
            "VALUES (?, ?, ?, ?)",
            (page_id, blob, "test-model", "2026-01-01T00:00:00Z"),
        )
    row = db._conn.execute(
        "SELECT page_id, model FROM embeddings WHERE page_id=?", (page_id,)
    ).fetchone()
    assert row["page_id"] == page_id
    assert row["model"] == "test-model"


# ---------------------------------------------------------------------------
# 11. Defaults seeded + not overwritten on reopen
# ---------------------------------------------------------------------------

def test_defaults_seeded(db: CrawlDB) -> None:
    for key, expected in DEFAULT_SETTINGS.items():
        row = db._conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        assert row is not None and row[0] == expected, key


def test_defaults_not_overwritten_on_reopen(db_path: Path) -> None:
    a = CrawlDB(db_path)
    with a.transaction() as c:
        c.execute(
            "UPDATE settings SET value=? WHERE key='tor.proxy'",
            ("socks5h://127.0.0.1:9999",),
        )
    a.close()

    b = CrawlDB(db_path)
    val = b._conn.execute(
        "SELECT value FROM settings WHERE key='tor.proxy'"
    ).fetchone()[0]
    assert val == "socks5h://127.0.0.1:9999"
    b.close()


# ---------------------------------------------------------------------------
# 12. schema_version == SCHEMA_VERSION == 7
# ---------------------------------------------------------------------------

def test_schema_version_pinned(db: CrawlDB) -> None:
    v = db._conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert v == SCHEMA_VERSION == 7


# ---------------------------------------------------------------------------
# 13. Crash sweep — running jobs become failed on reopen; pending survives
# ---------------------------------------------------------------------------

def test_crash_sweep_marks_running_jobs_failed(db_path: Path) -> None:
    a = CrawlDB(db_path)
    with a.transaction() as c:
        c.execute(
            "INSERT INTO jobs(kind, target_type, target_id, status) "
            "VALUES ('crawl', 'url', 1, 'running')"
        )
        c.execute(
            "INSERT INTO jobs(kind, target_type, target_id, status) "
            "VALUES ('crawl', 'url', 2, 'pending')"
        )
        c.execute(
            "INSERT INTO jobs(kind, target_type, target_id, status) "
            "VALUES ('crawl', 'url', 3, 'done')"
        )
    a.close()

    b = CrawlDB(db_path)
    rows = {
        r["target_id"]: (r["status"], r["error"])
        for r in b._conn.execute("SELECT target_id, status, error FROM jobs")
    }
    assert rows[1] == ("failed", "process restarted")
    assert rows[2] == ("pending", None)
    assert rows[3] == ("done", None)
    b.close()


# ---------------------------------------------------------------------------
# 14. Transaction context manager — nesting + rollback
# ---------------------------------------------------------------------------

def test_transaction_nesting_commits_on_outer(db: CrawlDB) -> None:
    with db.transaction() as c:
        c.execute("INSERT INTO seeds(url, label) VALUES ('http://a.onion', 'a')")
        with db.transaction() as inner:
            inner.execute("INSERT INTO seeds(url, label) VALUES ('http://b.onion', 'b')")
    rows = {r[0] for r in db._conn.execute("SELECT url FROM seeds")}
    assert rows == {"http://a.onion", "http://b.onion"}


def test_transaction_exception_rolls_back_everything(db: CrawlDB) -> None:
    with pytest.raises(RuntimeError):
        with db.transaction() as c:
            c.execute("INSERT INTO seeds(url, label) VALUES ('http://x.onion', 'x')")
            raise RuntimeError("boom")
    assert db._conn.execute("SELECT COUNT(*) FROM seeds").fetchone()[0] == 0
