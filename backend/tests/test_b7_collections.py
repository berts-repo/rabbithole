"""Phase B7c — collection CRUD, membership, exports.

Absorbs the original ``test_f3_collections.py`` (deleted as part of B7c)
plus PATCH/DELETE/items/exports per PLAN.md:317.
"""
from __future__ import annotations

import csv as csv_module
import io
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from backend.db import page_versions as versions_db
from backend.db.core import CrawlDB


def _insert_node(db: CrawlDB, url: str, *, title: str | None = None) -> int:
    """Crawl a URL once → its resource id (the id collection_items points at)."""
    host = url.split("/")[2] if "//" in url else url
    rid, _vid = versions_db.record_fetch(
        db,
        url=url,
        host=host,
        status_code=200,
        title=title,
        body_text=None,
        body_text_clean=None,
        response_headers={},
        when="2026-05-14T00:00:00+00:00",
    )
    return rid


def _insert_edge(db: CrawlDB, from_id: int, to_id: int) -> None:
    with db.transaction(immediate=True) as c:
        c.execute(
            "INSERT INTO edges(from_id, to_id, source) VALUES (?, ?, 'crawl')",
            (from_id, to_id),
        )


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "b7c.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    app.state.project_state.graph_cache.invalidate()
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        app.state.project_state.graph_cache.invalidate()
        db.close()


# ---------------------------------------------------------------------------
# Migrated from test_f3_collections.py
# ---------------------------------------------------------------------------


def test_list_empty(auth_client, active_db):
    r = auth_client.get("/api/collections")
    assert r.status_code == 200
    assert r.json() == {"collections": []}


def test_create_and_list(auth_client, active_db):
    r = auth_client.post("/api/collections", json={"name": "case-42"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "case-42"
    assert isinstance(body["id"], int)

    r = auth_client.get("/api/collections")
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["collections"]]
    assert "case-42" in names


def test_create_trims_whitespace(auth_client, active_db):
    r = auth_client.post("/api/collections", json={"name": "  spaced  "})
    assert r.status_code == 200
    assert r.json()["name"] == "spaced"


def test_create_rejects_empty(auth_client, active_db):
    r = auth_client.post("/api/collections", json={"name": "   "})
    assert r.status_code == 400
    assert r.json()["error"] == "name_required"


def test_create_rejects_too_long(auth_client, active_db):
    r = auth_client.post("/api/collections", json={"name": "x" * 200})
    assert r.status_code == 400
    assert r.json()["error"] == "name_too_long"


def test_create_rejects_duplicate_409(auth_client, active_db):
    auth_client.post("/api/collections", json={"name": "dup"})
    r = auth_client.post("/api/collections", json={"name": "dup"})
    assert r.status_code == 409
    assert r.json()["error"] == "duplicate_name"


def test_list_orders_newest_first(auth_client, active_db):
    auth_client.post("/api/collections", json={"name": "first"})
    auth_client.post("/api/collections", json={"name": "second"})
    rows = auth_client.get("/api/collections").json()["collections"]
    assert rows[0]["name"] == "second"
    assert rows[1]["name"] == "first"


# ---------------------------------------------------------------------------
# New for B7
# ---------------------------------------------------------------------------


def test_get_collection_404(auth_client, active_db):
    r = auth_client.get("/api/collections/9999")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_collection"


def test_get_collection_shape(auth_client, active_db):
    cid = auth_client.post(
        "/api/collections",
        json={"name": "case", "description": "desc"},
    ).json()["id"]
    r = auth_client.get(f"/api/collections/{cid}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == cid
    assert body["name"] == "case"
    assert body["description"] == "desc"
    assert body["items"] == []


def test_patch_rename(auth_client, active_db):
    cid = auth_client.post("/api/collections", json={"name": "old"}).json()["id"]
    r = auth_client.patch(f"/api/collections/{cid}", json={"name": "new"})
    assert r.status_code == 200
    assert r.json()["name"] == "new"


def test_patch_rename_duplicate_409(auth_client, active_db):
    auth_client.post("/api/collections", json={"name": "taken"})
    cid = auth_client.post("/api/collections", json={"name": "other"}).json()["id"]
    r = auth_client.patch(f"/api/collections/{cid}", json={"name": "taken"})
    assert r.status_code == 409
    assert r.json()["error"] == "duplicate_name"


def test_patch_description(auth_client, active_db):
    cid = auth_client.post("/api/collections", json={"name": "c"}).json()["id"]
    r = auth_client.patch(
        f"/api/collections/{cid}", json={"description": "notes here"}
    )
    assert r.status_code == 200
    assert r.json()["description"] == "notes here"


def test_patch_unknown_404(auth_client, active_db):
    r = auth_client.patch("/api/collections/9999", json={"name": "x"})
    assert r.status_code == 404


def test_delete_cascades_items(auth_client, active_db):
    cid = auth_client.post("/api/collections", json={"name": "c"}).json()["id"]
    nid = _insert_node(active_db, "http://a.onion/")
    auth_client.post(f"/api/collections/{cid}/items", json={"node_ids": [nid]})

    r = auth_client.delete(f"/api/collections/{cid}")
    assert r.status_code == 200
    # collection_items row gone (FK ON DELETE CASCADE)
    with active_db._lock:  # noqa: SLF001
        rows = active_db._conn.execute(
            "SELECT * FROM collection_items WHERE collection_id = ?", (cid,)
        ).fetchall()
    assert rows == []


def test_delete_unknown_404(auth_client, active_db):
    r = auth_client.delete("/api/collections/9999")
    assert r.status_code == 404


def test_add_item_idempotent(auth_client, active_db):
    cid = auth_client.post("/api/collections", json={"name": "c"}).json()["id"]
    nid = _insert_node(active_db, "http://a.onion/")
    r1 = auth_client.post(f"/api/collections/{cid}/items", json={"node_ids": [nid]})
    assert r1.status_code == 200
    assert r1.json() == {"added": 1, "skipped": 0, "added_ids": [nid]}
    r2 = auth_client.post(f"/api/collections/{cid}/items", json={"node_ids": [nid]})
    assert r2.status_code == 200
    assert r2.json() == {"added": 0, "skipped": 1, "added_ids": []}


def test_add_items_batch(auth_client, active_db):
    cid = auth_client.post("/api/collections", json={"name": "c"}).json()["id"]
    a = _insert_node(active_db, "http://a.onion/")
    b = _insert_node(active_db, "http://b.onion/")
    c = _insert_node(active_db, "http://c.onion/")
    r = auth_client.post(
        f"/api/collections/{cid}/items", json={"node_ids": [a, b, c]}
    )
    assert r.status_code == 200
    assert r.json() == {"added": 3, "skipped": 0, "added_ids": [a, b, c]}
    items = auth_client.get(f"/api/collections/{cid}").json()["items"]
    assert {it["id"] for it in items} == {a, b, c}


def test_add_items_dedup_and_unknown_skipped(auth_client, active_db):
    """Duplicate ids within the batch and unknown ids both count as skipped."""
    cid = auth_client.post("/api/collections", json={"name": "c"}).json()["id"]
    a = _insert_node(active_db, "http://a.onion/")
    r = auth_client.post(
        f"/api/collections/{cid}/items", json={"node_ids": [a, a, 99999]}
    )
    assert r.status_code == 200
    # ``a`` deduped to one add; ``99999`` is unknown → skipped.
    assert r.json() == {"added": 1, "skipped": 1, "added_ids": [a]}


def test_add_item_unknown_collection_404(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/")
    r = auth_client.post("/api/collections/9999/items", json={"node_ids": [nid]})
    assert r.status_code == 404
    assert r.json()["error"] == "unknown_collection"


def test_add_item_unknown_node_skipped(auth_client, active_db):
    """An unknown node id is skipped, not a 404 — batch semantics: one bad
    id must not fail the whole call."""
    cid = auth_client.post("/api/collections", json={"name": "c"}).json()["id"]
    r = auth_client.post(f"/api/collections/{cid}/items", json={"node_ids": [99999]})
    assert r.status_code == 200
    assert r.json() == {"added": 0, "skipped": 1, "added_ids": []}


def test_remove_item(auth_client, active_db):
    cid = auth_client.post("/api/collections", json={"name": "c"}).json()["id"]
    nid = _insert_node(active_db, "http://a.onion/")
    auth_client.post(f"/api/collections/{cid}/items", json={"node_ids": [nid]})
    r = auth_client.delete(f"/api/collections/{cid}/items/{nid}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_remove_item_unknown_404(auth_client, active_db):
    cid = auth_client.post("/api/collections", json={"name": "c"}).json()["id"]
    nid = _insert_node(active_db, "http://a.onion/")
    r = auth_client.delete(f"/api/collections/{cid}/items/{nid}")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_item"


def test_list_for_node(auth_client, active_db):
    cid_a = auth_client.post("/api/collections", json={"name": "alpha"}).json()["id"]
    cid_b = auth_client.post("/api/collections", json={"name": "bravo"}).json()["id"]
    nid = _insert_node(active_db, "http://a.onion/")
    auth_client.post(f"/api/collections/{cid_a}/items", json={"node_ids": [nid]})
    auth_client.post(f"/api/collections/{cid_b}/items", json={"node_ids": [nid]})
    rows = auth_client.get(f"/api/nodes/{nid}/collections").json()["collections"]
    names = {r["name"] for r in rows}
    assert names == {"alpha", "bravo"}


def test_export_json_shape(auth_client, active_db):
    cid = auth_client.post("/api/collections", json={"name": "export-me"}).json()["id"]
    a = _insert_node(active_db, "http://a.onion/", title="A")
    b = _insert_node(active_db, "http://b.onion/", title="B")
    c = _insert_node(active_db, "http://c.onion/", title="C")
    _insert_edge(active_db, a, b)
    _insert_edge(active_db, a, c)
    auth_client.post(f"/api/collections/{cid}/items", json={"node_ids": [a]})
    auth_client.post(f"/api/collections/{cid}/items", json={"node_ids": [b]})

    r = auth_client.get(f"/api/collections/{cid}/export?format=json")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    payload = json.loads(r.content)
    assert payload["collection"]["name"] == "export-me"
    ids = {n["id"] for n in payload["nodes"]}
    assert ids == {a, b}
    # Edge to non-member ``c`` must be dropped.
    edges = payload["edges"]
    assert all(e["from"] in ids and e["to"] in ids for e in edges)
    assert len(edges) == 1


def test_export_csv_filters_to_members(auth_client, active_db):
    cid = auth_client.post("/api/collections", json={"name": "csv"}).json()["id"]
    a = _insert_node(active_db, "http://a.onion/", title="A")
    _insert_node(active_db, "http://b.onion/", title="B")
    auth_client.post(f"/api/collections/{cid}/items", json={"node_ids": [a]})

    r = auth_client.get(f"/api/collections/{cid}/export?format=csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    reader = csv_module.reader(io.StringIO(r.text))
    rows = list(reader)
    # 1 header row + 1 member row
    assert len(rows) == 2
    assert rows[1][1] == "http://a.onion/"


def test_export_gexf_filters_to_members(auth_client, active_db):
    cid = auth_client.post("/api/collections", json={"name": "gx"}).json()["id"]
    a = _insert_node(active_db, "http://a.onion/")
    _insert_node(active_db, "http://b.onion/")
    auth_client.post(f"/api/collections/{cid}/items", json={"node_ids": [a]})

    r = auth_client.get(f"/api/collections/{cid}/export?format=gexf")
    assert r.status_code == 200
    root = ET.fromstring(r.content)
    nodes = root.findall(".//{http://gexf.net/1.3}node")
    assert len(nodes) == 1
    assert nodes[0].get("id") == str(a)


def test_export_bad_format_400(auth_client, active_db):
    cid = auth_client.post("/api/collections", json={"name": "c"}).json()["id"]
    r = auth_client.get(f"/api/collections/{cid}/export?format=xml")
    assert r.status_code == 400
    assert r.json()["error"] == "bad_format"


def test_export_unknown_collection_404(auth_client, active_db):
    r = auth_client.get("/api/collections/9999/export?format=json")
    assert r.status_code == 404
    assert r.json()["error"] == "unknown_collection"


def test_collection_membership_does_not_invalidate_graph_cache(
    auth_client, active_db, monkeypatch
):
    from backend.db import graph as graph_db
    from backend.routes import graph as graph_routes

    cid = auth_client.post("/api/collections", json={"name": "c"}).json()["id"]
    nid = _insert_node(active_db, "http://a.onion/")

    calls = {"n": 0}
    real = graph_db.build_payload

    def counting(db):
        calls["n"] += 1
        return real(db)

    monkeypatch.setattr(graph_routes, "build_payload", counting)

    auth_client.get("/api/graph")
    auth_client.post(f"/api/collections/{cid}/items", json={"node_ids": [nid]})
    auth_client.get("/api/graph")
    assert calls["n"] == 1  # membership change is not graph-visible state
