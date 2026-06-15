"""Phase B7a — flags CRUD + flag_status backfill in the graph payload."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import flags as flags_db
from backend.db import graph as graph_db
from backend.db import page_versions as versions_db
from backend.db.core import CrawlDB


def _insert_node(db: CrawlDB, url: str, *, title: str | None = None) -> int:
    """Crawl a URL so its resource exists with the given title on the current
    page version. Returns the resource id."""
    host = url.split("/")[2] if "//" in url else url
    return versions_db.record_fetch(
        db,
        url=url,
        host=host,
        status_code=200,
        title=title,
        body_text="x",
        body_text_clean="x",
        response_headers={},
        when="2026-05-12T00:00:00+00:00",
    )[0]


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "b7a_flags.db")
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
    r = auth_client.get("/api/flags")
    assert r.status_code == 200
    assert r.json() == {"flags": []}


def test_create_minimal_defaults(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/")
    r = auth_client.post("/api/flags", json={"node_id": nid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["node_id"] == nid
    assert body["status"] == "pending"
    assert body["priority"] == 2
    assert body["note"] is None
    assert isinstance(body["id"], int)


def test_create_full(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/")
    r = auth_client.post(
        "/api/flags",
        json={
            "node_id": nid,
            "status": "investigating",
            "priority": 1,
            "note": "tip from analyst",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "investigating"
    assert body["priority"] == 1
    assert body["note"] == "tip from analyst"


def test_create_unknown_node_404(auth_client, active_db):
    r = auth_client.post("/api/flags", json={"node_id": 99_999})
    assert r.status_code == 404
    assert r.json()["error"] == "unknown_node"


def test_create_bad_status_400(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/")
    r = auth_client.post("/api/flags", json={"node_id": nid, "status": "wat"})
    assert r.status_code == 400
    assert r.json()["error"] == "bad_status"


def test_create_bad_priority_400(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/")
    r = auth_client.post("/api/flags", json={"node_id": nid, "priority": 9})
    assert r.status_code == 400
    assert r.json()["error"] == "bad_priority"


def test_patch_partial(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/")
    fid = auth_client.post("/api/flags", json={"node_id": nid}).json()["id"]
    r = auth_client.patch(f"/api/flags/{fid}", json={"status": "done"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done"
    assert body["priority"] == 2  # preserved


def test_patch_unknown_404(auth_client, active_db):
    r = auth_client.patch("/api/flags/99999", json={"status": "done"})
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_flag"


def test_patch_bad_status_400(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/")
    fid = auth_client.post("/api/flags", json={"node_id": nid}).json()["id"]
    r = auth_client.patch(f"/api/flags/{fid}", json={"status": "wat"})
    assert r.status_code == 400
    assert r.json()["error"] == "bad_status"


def test_delete_ok(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/")
    fid = auth_client.post("/api/flags", json={"node_id": nid}).json()["id"]
    r = auth_client.delete(f"/api/flags/{fid}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    r2 = auth_client.delete(f"/api/flags/{fid}")
    assert r2.status_code == 404


def test_delete_unknown_404(auth_client, active_db):
    r = auth_client.delete("/api/flags/99999")
    assert r.status_code == 404


def test_clear_node_flags_deletes_all(auth_client, active_db):
    """DELETE /api/nodes/:id/flags wipes every flag on the node."""
    nid = _insert_node(active_db, "http://a.onion/")
    auth_client.post(
        "/api/flags",
        json={"node_id": nid, "status": "pending", "priority": 1},
    )
    auth_client.post(
        "/api/flags",
        json={"node_id": nid, "status": "investigating", "priority": 2},
    )
    r = auth_client.delete(f"/api/nodes/{nid}/flags")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "cleared": 2}
    # Idempotent: a second call returns ok with cleared=0, not 404.
    r2 = auth_client.delete(f"/api/nodes/{nid}/flags")
    assert r2.status_code == 200
    assert r2.json() == {"ok": True, "cleared": 0}
    # Graph payload reflects the wipe.
    payload = auth_client.get("/api/graph").json()
    node = next(n for n in payload["nodes"] if n["id"] == nid)
    assert node["flag_status"] is None


def test_clear_node_flags_invalidates_graph_cache(
    auth_client, active_db, app, monkeypatch
):
    nid = _insert_node(active_db, "http://a.onion/")
    auth_client.post("/api/flags", json={"node_id": nid})

    calls = {"n": 0}
    real = graph_db.build_payload

    def counting(db):
        calls["n"] += 1
        return real(db)

    from backend.routes import graph as graph_routes
    monkeypatch.setattr(graph_routes, "build_payload", counting)

    auth_client.get("/api/graph")
    assert calls["n"] == 1
    auth_client.delete(f"/api/nodes/{nid}/flags")
    auth_client.get("/api/graph")
    assert calls["n"] == 2
    # No flags left — second clear is a no-op, must NOT invalidate.
    auth_client.delete(f"/api/nodes/{nid}/flags")
    auth_client.get("/api/graph")
    assert calls["n"] == 2


def test_list_shape(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/", title="Page A")
    auth_client.post(
        "/api/flags",
        json={"node_id": nid, "status": "pending", "priority": 1},
    )
    rows = auth_client.get("/api/flags").json()["flags"]
    assert len(rows) == 1
    r = rows[0]
    assert r["node_id"] == nid
    assert r["url"] == "http://a.onion/"
    assert r["title"] == "Page A"
    assert r["priority"] == 1


def test_create_invalidates_graph_cache(auth_client, active_db, app, monkeypatch):
    nid = _insert_node(active_db, "http://a.onion/", title="a")
    calls = {"n": 0}
    real = graph_db.build_payload

    def counting(db):
        calls["n"] += 1
        return real(db)

    from backend.routes import graph as graph_routes
    monkeypatch.setattr(graph_routes, "build_payload", counting)

    auth_client.get("/api/graph")
    assert calls["n"] == 1
    auth_client.post("/api/flags", json={"node_id": nid})
    auth_client.get("/api/graph")
    assert calls["n"] == 2


def test_patch_invalidates_graph_cache(auth_client, active_db, app, monkeypatch):
    nid = _insert_node(active_db, "http://a.onion/")
    fid = auth_client.post("/api/flags", json={"node_id": nid}).json()["id"]

    calls = {"n": 0}
    real = graph_db.build_payload

    def counting(db):
        calls["n"] += 1
        return real(db)

    from backend.routes import graph as graph_routes
    monkeypatch.setattr(graph_routes, "build_payload", counting)

    auth_client.get("/api/graph")
    auth_client.patch(f"/api/flags/{fid}", json={"status": "investigating"})
    auth_client.get("/api/graph")
    assert calls["n"] == 2


def test_delete_invalidates_graph_cache(auth_client, active_db, app, monkeypatch):
    nid = _insert_node(active_db, "http://a.onion/")
    fid = auth_client.post("/api/flags", json={"node_id": nid}).json()["id"]

    calls = {"n": 0}
    real = graph_db.build_payload

    def counting(db):
        calls["n"] += 1
        return real(db)

    from backend.routes import graph as graph_routes
    monkeypatch.setattr(graph_routes, "build_payload", counting)

    auth_client.get("/api/graph")
    auth_client.delete(f"/api/flags/{fid}")
    auth_client.get("/api/graph")
    assert calls["n"] == 2


def test_flag_status_appears_in_graph_payload(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/", title="a")
    auth_client.post(
        "/api/flags",
        json={"node_id": nid, "status": "investigating", "priority": 1},
    )
    payload = auth_client.get("/api/graph").json()
    node = next(n for n in payload["nodes"] if n["id"] == nid)
    assert node["flag_status"] == "investigating"


def test_done_flag_does_not_set_graph_flag_status(auth_client, active_db):
    """Done/dismissed flags must leave the graph node with flag_status=None."""
    nid = _insert_node(active_db, "http://a.onion/")
    fid = auth_client.post("/api/flags", json={"node_id": nid}).json()["id"]
    auth_client.patch(f"/api/flags/{fid}", json={"status": "done"})
    payload = auth_client.get("/api/graph").json()
    node = next(n for n in payload["nodes"] if n["id"] == nid)
    assert node["flag_status"] is None


def test_highest_priority_active_flag_wins(auth_client, active_db):
    """Multiple active flags on one node — priority 1 (High) wins over 3 (Low)."""
    nid = _insert_node(active_db, "http://a.onion/")
    auth_client.post(
        "/api/flags",
        json={"node_id": nid, "status": "pending", "priority": 3},
    )
    auth_client.post(
        "/api/flags",
        json={"node_id": nid, "status": "investigating", "priority": 1},
    )
    payload = auth_client.get("/api/graph").json()
    node = next(n for n in payload["nodes"] if n["id"] == nid)
    assert node["flag_status"] == "investigating"


def test_node_detail_includes_active_flag(auth_client, active_db):
    """``GET /api/nodes/:id`` returns a ``flag`` object for the active flag."""
    nid = _insert_node(active_db, "http://a.onion/")
    fid = auth_client.post(
        "/api/flags",
        json={"node_id": nid, "status": "pending", "priority": 1, "note": "n"},
    ).json()["id"]
    body = auth_client.get(f"/api/nodes/{nid}").json()
    assert body["flag"] == {
        "id": fid,
        "status": "pending",
        "source": "analyst",
        "priority": 1,
        "note": "n",
    }


def test_node_detail_flag_null_when_no_active_flag(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/")
    body = auth_client.get(f"/api/nodes/{nid}").json()
    assert body["flag"] is None


# ---------------------------------------------------------------------------
# F4b — 5-state lifecycle + source column
# ---------------------------------------------------------------------------


def test_create_flagged_status(auth_client, active_db):
    """The new ``flagged`` lifecycle state is accepted."""
    nid = _insert_node(active_db, "http://a.onion/")
    r = auth_client.post(
        "/api/flags", json={"node_id": nid, "status": "flagged"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "flagged"


def test_create_source_defaults_analyst(auth_client, active_db):
    """Flags raised through the route are analyst-sourced."""
    nid = _insert_node(active_db, "http://a.onion/")
    r = auth_client.post("/api/flags", json={"node_id": nid})
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "analyst"


def test_list_flags_includes_source(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/", title="a")
    auth_client.post("/api/flags", json={"node_id": nid})
    rows = auth_client.get("/api/flags").json()["flags"]
    assert rows[0]["source"] == "analyst"


def test_create_bad_source_rejected(active_db):
    """``create_flag`` validates ``source`` against VALID_SOURCES."""
    nid = _insert_node(active_db, "http://a.onion/")
    with pytest.raises(ValueError, match="bad_source"):
        flags_db.create_flag(active_db, nid, source="bogus")


def test_watchlist_flag_has_watchlist_source(active_db):
    """The crawler's auto-flag path records ``source='watchlist'``."""
    nid = _insert_node(active_db, "http://a.onion/", title="a")
    flags_db.insert_watchlist_flag(active_db, nid, ["bitcoin"])
    rows = flags_db.list_flags(active_db)
    assert len(rows) == 1
    assert rows[0]["source"] == "watchlist"
    assert rows[0]["status"] == "pending"


def test_flagged_status_appears_in_graph_payload(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/", title="a")
    auth_client.post(
        "/api/flags", json={"node_id": nid, "status": "flagged"}
    )
    payload = auth_client.get("/api/graph").json()
    node = next(n for n in payload["nodes"] if n["id"] == nid)
    assert node["flag_status"] == "flagged"


def test_flag_persists_across_reopen(tmp_path: Path):
    """A flag survives closing and reopening the DB (fresh v3 schema — no
    in-place migration)."""
    path = tmp_path / "reopen.db"
    db = CrawlDB(path)
    nid = _insert_node(db, "http://a.onion/")
    flags_db.create_flag(db, nid, status="flagged")
    db.close()
    db = CrawlDB(path)
    try:
        rows = flags_db.list_flags(db)
        assert len(rows) == 1
        assert rows[0]["status"] == "flagged"
        assert rows[0]["source"] == "analyst"
    finally:
        db.close()
