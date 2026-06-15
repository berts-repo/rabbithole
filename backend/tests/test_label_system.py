"""Label system (item 11) Phase 1 — schema, CRUD, attach/detach, page rename.

Covers the db layer (`db/labels.py`, `db/pages.rename_alias`), the routes
(`routes/labels.py`, `PATCH /api/pages/{id}/alias`), and the additive v5 → v6
migration (new label tables + `pages.alias`, presets seeded, existing rows
untouched).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.db import domains as domains_db
from backend.db import graph as graph_db
from backend.db import labels as labels_db
from backend.db import pages as pages_db
from backend.db.core import PRESET_LABELS, SCHEMA_VERSION, CrawlDB


# --- fixtures --------------------------------------------------------------


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "labels.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


def _seed_resource(db: CrawlDB, host: str = "abc.onion") -> int:
    """Insert a domain + one crawled resource, return the resource id."""
    with db.transaction(immediate=True) as c:
        c.execute(
            "INSERT OR IGNORE INTO domains(host, last_seen) VALUES (?, ?)",
            (host, "2026-01-01"),
        )
        cur = c.execute(
            "INSERT INTO resources(url, host, state, first_seen) "
            "VALUES (?, ?, 'crawled', '2026-01-01')",
            (f"http://{host}/{host}", host),
        )
        return int(cur.lastrowid)


# --- preset seeding --------------------------------------------------------


def test_presets_seeded_with_ranks(db: CrawlDB) -> None:
    labels = labels_db.list_labels(db)
    assert len(labels) == len(PRESET_LABELS)
    assert all(label["builtin"] for label in labels)
    # Warnings rank highest (lowest number) per decision D5.
    assert labels[0]["name"] == "Avoid"
    assert labels[1]["name"] == "Scam"
    assert labels[0]["rank"] < labels[2]["rank"]


def test_preset_seed_idempotent_on_reopen(tmp_path: Path) -> None:
    path = tmp_path / "reopen.db"
    CrawlDB(path).close()
    db = CrawlDB(path)
    try:
        assert len(labels_db.list_labels(db)) == len(PRESET_LABELS)
    finally:
        db.close()


# --- CRUD ------------------------------------------------------------------


def test_create_custom_label_ranks_at_bottom(db: CrawlDB) -> None:
    created = labels_db.create_label(db, name="Drug marketplace", color="#abc")
    assert created["builtin"] is False
    assert created["rank"] == len(PRESET_LABELS)  # max(rank)+1
    assert created["name"] == "Drug marketplace"


def test_create_duplicate_name_rejected(db: CrawlDB) -> None:
    with pytest.raises(ValueError, match="duplicate_name"):
        labels_db.create_label(db, name="Market")


def test_create_empty_name_rejected(db: CrawlDB) -> None:
    with pytest.raises(ValueError, match="empty_name"):
        labels_db.create_label(db, name="   ")


def test_update_preset_recolor_ok_rename_blocked(db: CrawlDB) -> None:
    avoid = next(label for label in labels_db.list_labels(db) if label["name"] == "Avoid")
    # Recolor + redescribe + hide a preset — allowed.
    updated = labels_db.update_label(
        db, avoid["id"], name="Avoid", color="#111", description="d", hidden=True
    )
    assert updated is not None
    assert updated["color"] == "#111"
    assert updated["hidden"] is True
    # Renaming a preset — blocked (D3).
    with pytest.raises(ValueError, match="builtin_rename"):
        labels_db.update_label(
            db, avoid["id"], name="Avoid2", color="#111", description="d", hidden=True
        )


def test_update_unknown_label_returns_none(db: CrawlDB) -> None:
    assert labels_db.update_label(
        db, 9999, name="x", color=None, description=None, hidden=False
    ) is None


def test_update_duplicate_name_rejected(db: CrawlDB) -> None:
    custom = labels_db.create_label(db, name="Custom")
    with pytest.raises(ValueError, match="duplicate_name"):
        labels_db.update_label(
            db, custom["id"], name="Market", color=None, description=None, hidden=False
        )


def test_delete_preset_blocked_custom_cascades(db: CrawlDB) -> None:
    rid = _seed_resource(db)
    avoid = next(label for label in labels_db.list_labels(db) if label["name"] == "Avoid")
    with pytest.raises(ValueError, match="builtin_undeletable"):
        labels_db.delete_label(db, avoid["id"])

    custom = labels_db.create_label(db, name="Temp")
    labels_db.attach_resource(db, custom["id"], rid)
    assert labels_db.delete_label(db, custom["id"]) is True
    # Cascade wiped the attachment row.
    with db.read() as c:
        n = c.execute("SELECT COUNT(*) AS n FROM resource_labels").fetchone()["n"]
    assert n == 0


def test_delete_unknown_label_returns_false(db: CrawlDB) -> None:
    assert labels_db.delete_label(db, 9999) is False


# --- attachment ------------------------------------------------------------


def test_attach_detach_resource_idempotent(db: CrawlDB) -> None:
    rid = _seed_resource(db)
    market = next(label for label in labels_db.list_labels(db) if label["name"] == "Market")
    assert labels_db.attach_resource(db, market["id"], rid) is True
    assert labels_db.attach_resource(db, market["id"], rid) is False  # idempotent
    counts = next(label for label in labels_db.list_labels(db) if label["id"] == market["id"])
    assert counts["resource_count"] == 1
    assert labels_db.detach_resource(db, market["id"], rid) is True
    assert labels_db.detach_resource(db, market["id"], rid) is False


def test_attach_domain_member_count(db: CrawlDB) -> None:
    _seed_resource(db, "shop.onion")
    market = next(label for label in labels_db.list_labels(db) if label["name"] == "Market")
    assert labels_db.attach_domain(db, market["id"], "shop.onion") is True
    counts = next(label for label in labels_db.list_labels(db) if label["id"] == market["id"])
    assert counts["domain_count"] == 1


def test_attach_unknown_targets_rejected(db: CrawlDB) -> None:
    market = next(label for label in labels_db.list_labels(db) if label["name"] == "Market")
    with pytest.raises(ValueError, match="unknown_resource"):
        labels_db.attach_resource(db, market["id"], 9999)
    with pytest.raises(ValueError, match="unknown_domain"):
        labels_db.attach_domain(db, market["id"], "nope.onion")
    rid = _seed_resource(db)
    with pytest.raises(ValueError, match="unknown_label"):
        labels_db.attach_resource(db, 9999, rid)


# --- membership reads ------------------------------------------------------


def _label_id(db: CrawlDB, name: str) -> int:
    return next(label["id"] for label in labels_db.list_labels(db) if label["name"] == name)


def test_resource_label_ids_rank_ordered(db: CrawlDB) -> None:
    rid = _seed_resource(db)
    market = _label_id(db, "Market")
    avoid = _label_id(db, "Avoid")  # warnings rank high (lower rank number)
    labels_db.attach_resource(db, market, rid)
    labels_db.attach_resource(db, avoid, rid)
    # Highest rank (Avoid) leads, regardless of attach order.
    assert labels_db.resource_label_ids(db, rid) == [avoid, market]
    assert labels_db.resource_label_ids(db, 9999) == []


def test_domain_label_ids(db: CrawlDB) -> None:
    _seed_resource(db, "shop.onion")
    market = _label_id(db, "Market")
    labels_db.attach_domain(db, market, "shop.onion")
    assert labels_db.domain_label_ids(db, "shop.onion") == [market]
    assert labels_db.domain_label_ids(db, "nope.onion") == []


def test_bulk_label_id_maps(db: CrawlDB) -> None:
    r1 = _seed_resource(db, "a.onion")
    r2 = _seed_resource(db, "b.onion")
    market = _label_id(db, "Market")
    forum = _label_id(db, "Forum")
    labels_db.attach_resource(db, market, r1)
    labels_db.attach_resource(db, forum, r2)
    labels_db.attach_domain(db, market, "a.onion")
    res_map = labels_db.all_resource_label_ids(db)
    dom_map = labels_db.all_domain_label_ids(db)
    assert res_map == {r1: [market], r2: [forum]}
    assert dom_map == {"a.onion": [market]}


def test_label_members_lists_resources_and_domains(db: CrawlDB) -> None:
    rid = _seed_resource(db, "mem.onion")
    market = _label_id(db, "Market")
    labels_db.attach_resource(db, market, rid)
    labels_db.attach_domain(db, market, "mem.onion")
    members = labels_db.label_members(db, market)
    assert [r["id"] for r in members["resources"]] == [rid]
    assert members["resources"][0]["host"] == "mem.onion"
    assert [d["host"] for d in members["domains"]] == ["mem.onion"]
    # An empty label has both lists empty, not an error.
    forum = _label_id(db, "Forum")
    assert labels_db.label_members(db, forum) == {"resources": [], "domains": []}


def test_label_members_route_404_on_unknown(auth_client, active_db) -> None:
    market = _label_id(active_db, "Market")
    rid = _seed_resource(active_db, "route.onion")
    labels_db.attach_resource(active_db, market, rid)
    ok = auth_client.get(f"/api/labels/{market}/members")
    assert ok.status_code == 200
    assert [r["id"] for r in ok.json()["resources"]] == [rid]
    assert auth_client.get("/api/labels/9999/members").status_code == 404


def test_graph_payload_carries_labels_with_via_domain_dedupe(db: CrawlDB) -> None:
    rid = _seed_resource(db, "mkt.onion")
    market = _label_id(db, "Market")
    avoid = _label_id(db, "Avoid")
    # Market is attached both directly and via the domain → renders once, as
    # direct (deduped out of the via-domain list). Avoid is via-domain only.
    labels_db.attach_resource(db, market, rid)
    labels_db.attach_domain(db, market, "mkt.onion")
    labels_db.attach_domain(db, avoid, "mkt.onion")
    node = next(n for n in graph_db.build_payload(db)["nodes"] if n["id"] == rid)
    assert node["label_ids"] == [market]
    assert node["domain_label_ids"] == [avoid]


def test_node_detail_carries_labels(db: CrawlDB) -> None:
    rid = _seed_resource(db, "n.onion")
    market = _label_id(db, "Market")
    avoid = _label_id(db, "Avoid")
    labels_db.attach_resource(db, market, rid)
    labels_db.attach_domain(db, avoid, "n.onion")
    detail = pages_db.get_page_detail(db, rid)
    assert detail["label_ids"] == [market]
    assert detail["domain_label_ids"] == [avoid]


def test_domain_profile_carries_labels(db: CrawlDB) -> None:
    _seed_resource(db, "d.onion")
    market = _label_id(db, "Market")
    labels_db.attach_domain(db, market, "d.onion")
    profile = domains_db.get_profile(db, "d.onion")
    assert profile["label_ids"] == [market]


def test_attach_route_invalidates_graph_cache(auth_client, active_db) -> None:
    rid = _seed_resource(active_db, "cache.onion")
    market = _label_id(active_db, "Market")
    # Warm the cache, then attach — the route must bust it so the next read
    # reflects the new membership (the payload carries label ids per node).
    assert auth_client.get("/api/graph").status_code == 200
    auth_client.post(f"/api/labels/{market}/resources/{rid}")
    node = next(n for n in auth_client.get("/api/graph").json()["nodes"] if n["id"] == rid)
    assert node["label_ids"] == [market]
    auth_client.delete(f"/api/labels/{market}/resources/{rid}")
    node = next(n for n in auth_client.get("/api/graph").json()["nodes"] if n["id"] == rid)
    assert node["label_ids"] == []


# --- reorder ---------------------------------------------------------------


def test_reorder_writes_rank_by_position(db: CrawlDB) -> None:
    ids = [label["id"] for label in labels_db.list_labels(db)]
    labels_db.reorder(db, list(reversed(ids)))
    reordered = labels_db.list_labels(db)
    assert reordered[0]["id"] == ids[-1]
    assert reordered[0]["rank"] == 0


def test_reorder_partial_list_appends_unnamed(db: CrawlDB) -> None:
    custom = labels_db.create_label(db, name="Z-custom")
    # Name only the custom label; presets keep relative order below it.
    labels_db.reorder(db, [custom["id"]])
    ordered = labels_db.list_labels(db)
    assert ordered[0]["id"] == custom["id"]
    assert ordered[0]["rank"] == 0
    assert len(ordered) == len(PRESET_LABELS) + 1


def test_hidden_filter(db: CrawlDB) -> None:
    avoid = next(label for label in labels_db.list_labels(db) if label["name"] == "Avoid")
    labels_db.update_label(
        db, avoid["id"], name="Avoid", color=None, description=None, hidden=True
    )
    visible = labels_db.list_labels(db, include_hidden=False)
    assert all(label["name"] != "Avoid" for label in visible)
    assert len(visible) == len(PRESET_LABELS) - 1


# --- page alias ------------------------------------------------------------


def test_page_alias_set_and_clear(db: CrawlDB) -> None:
    rid = _seed_resource(db)
    assert pages_db.rename_alias(db, rid, "  Vendor X  ") == {
        "resource_id": rid,
        "alias": "Vendor X",
    }
    assert pages_db.get_page_detail(db, rid)["alias"] == "Vendor X"
    # Whitespace-only clears to NULL.
    assert pages_db.rename_alias(db, rid, "   ")["alias"] is None
    assert pages_db.get_page_detail(db, rid)["alias"] is None


def test_page_alias_unknown_resource(db: CrawlDB) -> None:
    assert pages_db.rename_alias(db, 9999, "x") is None


def test_page_alias_too_long(db: CrawlDB) -> None:
    rid = _seed_resource(db)
    with pytest.raises(ValueError, match="alias_too_long"):
        pages_db.rename_alias(db, rid, "a" * (pages_db.ALIAS_MAX + 1))


# --- routes ----------------------------------------------------------------


def test_route_list_labels(auth_client, active_db) -> None:
    r = auth_client.get("/api/labels")
    assert r.status_code == 200
    names = {label["name"] for label in r.json()["labels"]}
    assert "Avoid" in names and "Market" in names


def test_route_create_and_duplicate(auth_client, active_db) -> None:
    r = auth_client.post("/api/labels", json={"name": "Leak site", "color": "#f00"})
    assert r.status_code == 200
    assert r.json()["name"] == "Leak site"
    dup = auth_client.post("/api/labels", json={"name": "Market"})
    assert dup.status_code == 409
    assert dup.json()["error"] == "duplicate_name"


def test_route_update_and_preset_rename_409(auth_client, active_db) -> None:
    labels = auth_client.get("/api/labels").json()["labels"]
    avoid = next(label for label in labels if label["name"] == "Avoid")
    ok = auth_client.patch(
        f"/api/labels/{avoid['id']}",
        json={"name": "Avoid", "color": "#000", "description": "x", "hidden": True},
    )
    assert ok.status_code == 200
    assert ok.json()["hidden"] is True
    blocked = auth_client.patch(
        f"/api/labels/{avoid['id']}",
        json={"name": "Renamed", "color": "#000", "description": "x", "hidden": True},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"] == "builtin_rename"


def test_route_delete_preset_409_custom_ok(auth_client, active_db) -> None:
    labels = auth_client.get("/api/labels").json()["labels"]
    avoid = next(label for label in labels if label["name"] == "Avoid")
    blocked = auth_client.delete(f"/api/labels/{avoid['id']}")
    assert blocked.status_code == 409
    assert blocked.json()["error"] == "builtin_undeletable"

    created = auth_client.post("/api/labels", json={"name": "Temp"}).json()
    assert auth_client.delete(f"/api/labels/{created['id']}").status_code == 200


def test_route_attach_detach_resource(auth_client, active_db) -> None:
    rid = _seed_resource(active_db)
    labels = auth_client.get("/api/labels").json()["labels"]
    market = next(label for label in labels if label["name"] == "Market")
    a = auth_client.post(f"/api/labels/{market['id']}/resources/{rid}")
    assert a.status_code == 200 and a.json()["attached"] is True
    d = auth_client.delete(f"/api/labels/{market['id']}/resources/{rid}")
    assert d.status_code == 200 and d.json()["detached"] is True


def test_route_attach_unknown_resource_404(auth_client, active_db) -> None:
    labels = auth_client.get("/api/labels").json()["labels"]
    market = next(label for label in labels if label["name"] == "Market")
    r = auth_client.post(f"/api/labels/{market['id']}/resources/9999")
    assert r.status_code == 404
    assert r.json()["error"] == "unknown_resource"


def test_route_reorder(auth_client, active_db) -> None:
    labels = auth_client.get("/api/labels").json()["labels"]
    ids = [label["id"] for label in labels]
    r = auth_client.patch("/api/labels/order", json={"ids": list(reversed(ids))})
    assert r.status_code == 200
    assert r.json()["labels"][0]["id"] == ids[-1]


def test_route_page_alias_set_clear_and_404(auth_client, active_db) -> None:
    rid = _seed_resource(active_db)
    r = auth_client.patch(f"/api/pages/{rid}/alias", json={"alias": "Vendor X"})
    assert r.status_code == 200
    assert r.json() == {"resource_id": rid, "alias": "Vendor X"}
    clear = auth_client.patch(f"/api/pages/{rid}/alias", json={"alias": None})
    assert clear.json()["alias"] is None
    missing = auth_client.patch("/api/pages/9999/alias", json={"alias": "x"})
    assert missing.status_code == 404


# --- migration -------------------------------------------------------------


# v5 pages shape: the current DDL minus the v6 `alias` column, REFERENCES
# dropped so the fixture needs no companion tables (mirrors test_intel_migration).
_V5_PAGES = """CREATE TABLE pages (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id        INTEGER NOT NULL UNIQUE,
    current_version_id INTEGER,
    summary            TEXT,
    category           TEXT,
    reviewed           INTEGER NOT NULL DEFAULT 0,
    analysis_excluded  INTEGER NOT NULL DEFAULT 0,
    embed_excluded     INTEGER NOT NULL DEFAULT 0,
    opened_at          TEXT,
    created_at         TEXT
)"""


def _build_v5_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
        conn.execute("INSERT INTO schema_version(version) VALUES (5)")
        conn.execute(_V5_PAGES)
        # A pre-existing page row that must survive the upgrade untouched.
        conn.execute(
            "INSERT INTO pages(id, resource_id, summary) VALUES (99, 7, 'legacy')"
        )
        conn.commit()
    finally:
        conn.close()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_v5_db_upgrades_to_v6_additively(tmp_path: Path) -> None:
    path = tmp_path / "legacy_v5.db"
    _build_v5_db(path)

    pre = sqlite3.connect(path)
    try:
        assert pre.execute("SELECT version FROM schema_version").fetchone()[0] == 5
        assert "alias" not in _columns(pre, "pages")
        tables = {
            r[0] for r in pre.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "labels" not in tables
    finally:
        pre.close()

    db = CrawlDB(path)
    try:
        conn = db._conn
        assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == SCHEMA_VERSION

        tables = {
            r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"labels", "resource_labels", "domain_labels"} <= tables

        # pages.alias backfilled, nullable.
        assert "alias" in _columns(conn, "pages")
        row = conn.execute("SELECT summary, alias FROM pages WHERE id = 99").fetchone()
        assert row["summary"] == "legacy"
        assert row["alias"] is None

        # Presets seeded exactly once.
        seeded = conn.execute(
            "SELECT COUNT(*) FROM labels WHERE builtin = 1"
        ).fetchone()[0]
        assert seeded == len(PRESET_LABELS)
    finally:
        db.close()
