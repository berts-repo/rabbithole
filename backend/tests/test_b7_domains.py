"""Phase B7f — domain profile, pages, entities, alias rename."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import findings as findings_db
from backend.db import page_versions as versions_db
from backend.db import resources as resources_db
from backend.db.core import CrawlDB


def _insert_node(
    db: CrawlDB,
    url: str,
    *,
    title: str | None = None,
    domain: str | None = None,
    first_seen: str | None = "2026-05-14T00:00:00+00:00",
    status_code: int | None = 200,
    stub: bool = False,
) -> int:
    """Create a resource → its id. ``stub=True`` leaves it ``known`` (uncrawled)."""
    if domain is None:
        domain = url.split("/")[2] if "//" in url else url
    if stub:
        return resources_db.upsert_resource(db, url, domain, state="known", when=first_seen)
    rid, _vid = versions_db.record_fetch(
        db,
        url=url,
        host=domain,
        status_code=status_code or 200,
        title=title,
        body_text=None,
        body_text_clean=None,
        response_headers={},
        when=first_seen,
    )
    return rid


def _insert_entity(db: CrawlDB, node_id: int, etype: str, value: str) -> None:
    findings_db.insert_entities(db, node_id, [(etype, value)], source="crawl")


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "b7f_domains.db")
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


def test_list_domains_shape(auth_client, active_db):
    _insert_node(active_db, "http://a.onion/a1", domain="a.onion")
    _insert_node(active_db, "http://a.onion/a2", domain="a.onion")
    _insert_node(active_db, "http://b.onion/", domain="b.onion")
    rows = auth_client.get("/api/domains").json()["domains"]
    hosts = {r["host"]: r for r in rows}
    assert hosts["a.onion"]["page_count"] == 2
    assert hosts["b.onion"]["page_count"] == 1


def test_list_domains_orders_by_page_count(auth_client, active_db):
    for i in range(3):
        _insert_node(active_db, f"http://busy.onion/{i}", domain="busy.onion")
    _insert_node(active_db, "http://quiet.onion/", domain="quiet.onion")
    rows = auth_client.get("/api/domains").json()["domains"]
    assert rows[0]["host"] == "busy.onion"
    assert rows[1]["host"] == "quiet.onion"


def test_get_profile_full(auth_client, active_db):
    nid = _insert_node(active_db, "http://a.onion/x", domain="a.onion", title="X")
    _insert_entity(active_db, nid, "email", "user@a.onion")
    _insert_entity(active_db, nid, "btc", "1A")
    # Add a flag → flag_count should be 1
    auth_client.post(
        "/api/flags", json={"node_id": nid, "status": "pending", "priority": 1}
    )
    body = auth_client.get("/api/domains/a.onion").json()
    assert body["host"] == "a.onion"
    assert body["page_count"] == 1
    assert body["flag_count"] == 1
    assert body["entity_count"] == 2
    assert body["activity"] == [{"date": "2026-05-14", "count": 1}]
    type_counts = {row["type"]: row["count"] for row in body["entity_types"]}
    assert type_counts == {"email": 1, "btc": 1}


def test_get_profile_unknown_404(auth_client, active_db):
    r = auth_client.get("/api/domains/nope.onion")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_host"


def test_list_pages_caps_at_200(auth_client, active_db):
    for i in range(220):
        _insert_node(
            active_db,
            f"http://big.onion/p{i}",
            domain="big.onion",
            first_seen=f"2026-05-{(i % 28) + 1:02d}T00:00:00+00:00",
        )
    r = auth_client.get("/api/domains/big.onion/pages")
    assert r.status_code == 200
    assert len(r.json()["pages"]) == 200


def test_list_pages_excludes_filtered_nodes(auth_client, active_db):
    _insert_node(active_db, "http://a.onion/keep", domain="a.onion", title="keep")
    _insert_node(active_db, "http://a.onion/hide", domain="a.onion", title="hide")
    auth_client.post("/api/graph-filters", json={"term": "hide"})
    pages = auth_client.get("/api/domains/a.onion/pages").json()["pages"]
    urls = {p["url"] for p in pages}
    assert "http://a.onion/keep" in urls
    assert "http://a.onion/hide" not in urls


def test_list_entities_excludes_stubs(auth_client, active_db):
    crawled = _insert_node(active_db, "http://a.onion/", domain="a.onion")
    stub = _insert_node(
        active_db, "http://a.onion/stub", domain="a.onion", stub=True
    )
    _insert_entity(active_db, crawled, "email", "real@a.onion")
    _insert_entity(active_db, stub, "email", "phantom@a.onion")
    rows = auth_client.get("/api/domains/a.onion/entities").json()["entities"]
    values = {r["value"] for r in rows}
    assert "real@a.onion" in values
    assert "phantom@a.onion" not in values


def test_patch_alias_set(auth_client, active_db):
    _insert_node(active_db, "http://a.onion/", domain="a.onion")
    r = auth_client.patch("/api/domains/a.onion", json={"alias": "Alpha Site"})
    assert r.status_code == 200
    assert r.json() == {"host": "a.onion", "alias": "Alpha Site"}
    profile = auth_client.get("/api/domains/a.onion").json()
    assert profile["alias"] == "Alpha Site"


def test_patch_alias_clear_via_null(auth_client, active_db):
    _insert_node(active_db, "http://a.onion/", domain="a.onion")
    auth_client.patch("/api/domains/a.onion", json={"alias": "Alpha"})
    r = auth_client.patch("/api/domains/a.onion", json={"alias": None})
    assert r.status_code == 200
    assert r.json() == {"host": "a.onion", "alias": None}


def test_patch_alias_whitespace_clears(auth_client, active_db):
    _insert_node(active_db, "http://a.onion/", domain="a.onion")
    auth_client.patch("/api/domains/a.onion", json={"alias": "Alpha"})
    r = auth_client.patch("/api/domains/a.onion", json={"alias": "   "})
    assert r.status_code == 200
    assert r.json()["alias"] is None


def test_patch_alias_duplicate_409(auth_client, active_db):
    _insert_node(active_db, "http://a.onion/", domain="a.onion")
    _insert_node(active_db, "http://b.onion/", domain="b.onion")
    auth_client.patch("/api/domains/a.onion", json={"alias": "shared"})
    r = auth_client.patch("/api/domains/b.onion", json={"alias": "shared"})
    assert r.status_code == 409
    assert r.json()["error"] == "duplicate_alias"


def test_patch_alias_unknown_404(auth_client, active_db):
    r = auth_client.patch("/api/domains/nope.onion", json={"alias": "x"})
    assert r.status_code == 404


def test_patch_alias_same_host_idempotent(auth_client, active_db):
    """Re-setting the same alias on the same host should not 409."""
    _insert_node(active_db, "http://a.onion/", domain="a.onion")
    auth_client.patch("/api/domains/a.onion", json={"alias": "Alpha"})
    r = auth_client.patch("/api/domains/a.onion", json={"alias": "Alpha"})
    assert r.status_code == 200


def test_patch_alias_invalidates_graph_cache(auth_client, active_db, monkeypatch):
    _insert_node(active_db, "http://a.onion/", domain="a.onion")

    from backend.db import graph as graph_db
    from backend.routes import graph as graph_routes

    calls = {"n": 0}
    real = graph_db.build_payload

    def counting(db):
        calls["n"] += 1
        return real(db)

    monkeypatch.setattr(graph_routes, "build_payload", counting)

    auth_client.get("/api/graph")
    auth_client.patch("/api/domains/a.onion", json={"alias": "Renamed"})
    auth_client.get("/api/graph")
    assert calls["n"] == 2
