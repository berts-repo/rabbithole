"""Phase B7b — graph_filters Hidden sub-tab CRUD."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import graph as graph_db
from backend.db import graph_filters as graph_filters_db
from backend.db import page_versions as versions_db
from backend.db.core import CrawlDB


def _insert_node(db: CrawlDB, url: str, *, title: str | None = None) -> int:
    """Crawl a URL once → its resource id; ``title`` lands on the page version."""
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


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "b7b.db")
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
    r = auth_client.get("/api/graph-filters")
    assert r.status_code == 200
    assert r.json() == {"terms": []}


def test_add_and_remove_roundtrip(auth_client, active_db):
    r = auth_client.post("/api/graph-filters", json={"term": "noise"})
    assert r.status_code == 200, r.text
    assert r.json() == {"term": "noise"}

    rows = auth_client.get("/api/graph-filters").json()["terms"]
    assert rows == ["noise"]

    r = auth_client.delete("/api/graph-filters/noise")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert auth_client.get("/api/graph-filters").json() == {"terms": []}


def test_add_trims_whitespace(auth_client, active_db):
    r = auth_client.post("/api/graph-filters", json={"term": "  spaced  "})
    assert r.status_code == 200
    assert r.json() == {"term": "spaced"}


def test_add_rejects_empty_400(auth_client, active_db):
    r = auth_client.post("/api/graph-filters", json={"term": "   "})
    assert r.status_code == 400
    assert r.json()["error"] == "term_required"


def test_add_rejects_too_long_400(auth_client, active_db):
    r = auth_client.post("/api/graph-filters", json={"term": "x" * 300})
    assert r.status_code == 400
    assert r.json()["error"] == "term_too_long"


def test_add_rejects_duplicate_409(auth_client, active_db):
    auth_client.post("/api/graph-filters", json={"term": "dup"})
    r = auth_client.post("/api/graph-filters", json={"term": "dup"})
    assert r.status_code == 409
    assert r.json()["error"] == "duplicate_term"


def test_add_rejects_at_cap_400(active_db):
    # Drive the DB module directly — 500 inserts via the route would be slow.
    with active_db.transaction(immediate=True) as c:
        for i in range(graph_filters_db.MAX_TERMS):
            c.execute(
                "INSERT INTO graph_filters(term) VALUES (?)", (f"term_{i}",)
            )
    with pytest.raises(ValueError, match="too_many_terms"):
        graph_filters_db.add_term(active_db, "one_too_many")


def test_remove_unknown_404(auth_client, active_db):
    r = auth_client.delete("/api/graph-filters/ghost")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_term"


def test_add_invalidates_graph_cache(auth_client, active_db, monkeypatch):
    _insert_node(active_db, "http://a.onion/")
    calls = {"n": 0}
    real = graph_db.build_payload

    def counting(db):
        calls["n"] += 1
        return real(db)

    from backend.routes import graph as graph_routes
    monkeypatch.setattr(graph_routes, "build_payload", counting)

    auth_client.get("/api/graph")
    auth_client.post("/api/graph-filters", json={"term": "anything"})
    auth_client.get("/api/graph")
    assert calls["n"] == 2


def test_remove_invalidates_graph_cache(auth_client, active_db, monkeypatch):
    _insert_node(active_db, "http://a.onion/")
    auth_client.post("/api/graph-filters", json={"term": "anything"})
    calls = {"n": 0}
    real = graph_db.build_payload

    def counting(db):
        calls["n"] += 1
        return real(db)

    from backend.routes import graph as graph_routes
    monkeypatch.setattr(graph_routes, "build_payload", counting)

    auth_client.get("/api/graph")
    auth_client.delete("/api/graph-filters/anything")
    auth_client.get("/api/graph")
    assert calls["n"] == 2


def test_excluded_node_ids_url_substring_case_insensitive(active_db):
    a = _insert_node(active_db, "http://Spam-Site.onion/")
    b = _insert_node(active_db, "http://clean.onion/")
    graph_filters_db.add_term(active_db, "spam")
    excluded = graph_filters_db.excluded_node_ids(active_db)
    assert a in excluded
    assert b not in excluded


def test_excluded_node_ids_matches_title(active_db):
    a = _insert_node(active_db, "http://a.onion/", title="Welcome To Casino Land")
    b = _insert_node(active_db, "http://b.onion/", title="Library")
    graph_filters_db.add_term(active_db, "casino")
    excluded = graph_filters_db.excluded_node_ids(active_db)
    assert a in excluded
    assert b not in excluded


def test_excluded_node_ids_empty_when_no_terms(active_db):
    _insert_node(active_db, "http://a.onion/")
    assert graph_filters_db.excluded_node_ids(active_db) == set()


def test_filter_hides_node_from_graph_payload(auth_client, active_db):
    """The existing graph filter logic should respect new terms added via the route."""
    a = _insert_node(active_db, "http://noise.onion/", title="a")
    b = _insert_node(active_db, "http://keep.onion/", title="b")
    auth_client.post("/api/graph-filters", json={"term": "noise"})
    payload = auth_client.get("/api/graph").json()
    ids = {n["id"] for n in payload["nodes"]}
    assert a not in ids
    assert b in ids
