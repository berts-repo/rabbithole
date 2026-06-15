"""Phase B7a — per-node analyst notes."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import graph as graph_db
from backend.db import resources as resources_db
from backend.db.core import CrawlDB


def _insert_node(db: CrawlDB, url: str) -> int:
    """A resource id for the URL — notes are ``findings`` keyed by resource."""
    host = url.split("/")[2] if "//" in url else url
    return resources_db.upsert_resource(db, url, host, state="known")


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "b7a_notes.db")
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


def test_list_empty(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/")
    r = auth_client.get(f"/api/nodes/{nid}/notes")
    assert r.status_code == 200
    assert r.json() == {"notes": []}


def test_create_persists(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/")
    r = auth_client.post(f"/api/nodes/{nid}/notes", json={"body": "first thought"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["body"] == "first thought"
    assert isinstance(body["id"], int)
    assert isinstance(body["created_at"], str)

    rows = auth_client.get(f"/api/nodes/{nid}/notes").json()["notes"]
    assert len(rows) == 1
    assert rows[0]["body"] == "first thought"


def test_create_strips_and_rejects_empty(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/")
    r = auth_client.post(f"/api/nodes/{nid}/notes", json={"body": "   "})
    assert r.status_code == 400
    assert r.json()["error"] == "body_required"


def test_create_trims_whitespace(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/")
    r = auth_client.post(f"/api/nodes/{nid}/notes", json={"body": "  hi  "})
    assert r.status_code == 200
    assert r.json()["body"] == "hi"


def test_create_unknown_node_404(auth_client, active_db):
    r = auth_client.post("/api/nodes/99999/notes", json={"body": "x"})
    assert r.status_code == 404
    assert r.json()["error"] == "unknown_resource"


def test_delete_ok(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/")
    note_id = auth_client.post(
        f"/api/nodes/{nid}/notes", json={"body": "x"}
    ).json()["id"]
    r = auth_client.delete(f"/api/notes/{note_id}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    r2 = auth_client.delete(f"/api/notes/{note_id}")
    assert r2.status_code == 404


def test_delete_unknown_404(auth_client, active_db):
    r = auth_client.delete("/api/notes/99999")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_note"


def test_list_newest_first(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/")
    auth_client.post(f"/api/nodes/{nid}/notes", json={"body": "first"})
    auth_client.post(f"/api/nodes/{nid}/notes", json={"body": "second"})
    rows = auth_client.get(f"/api/nodes/{nid}/notes").json()["notes"]
    assert [r["body"] for r in rows] == ["second", "first"]


def test_notes_do_not_invalidate_graph_cache(auth_client, active_db, app, monkeypatch):
    nid = _insert_node(active_db, "http://a.onion/")
    calls = {"n": 0}
    real = graph_db.build_payload

    def counting(db):
        calls["n"] += 1
        return real(db)

    from backend.routes import graph as graph_routes
    monkeypatch.setattr(graph_routes, "build_payload", counting)

    auth_client.get("/api/graph")
    auth_client.post(f"/api/nodes/{nid}/notes", json={"body": "x"})
    auth_client.get("/api/graph")
    assert calls["n"] == 1  # cache still warm — note didn't invalidate
