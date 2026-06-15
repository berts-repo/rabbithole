"""Phase B7f — /api/entities/common."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import findings as findings_db
from backend.db import resources as resources_db
from backend.db.core import CrawlDB


def _insert_node(db: CrawlDB, url: str, *, stub: bool = False) -> int:
    """Return a resource id. ``stub`` → 'known' (uncrawled); else 'crawled'.

    Entities fold into ``findings`` and the common-entities reads count only
    crawled resources, so an uncrawled (``stub``) resource's entity is ignored.
    """
    host = url.split("/")[2] if "//" in url else url
    return resources_db.upsert_resource(
        db, url, host, state="known" if stub else "crawled"
    )


def _insert_entity(
    db: CrawlDB, node_id: int, etype: str, value: str, *, source: str = "crawl"
) -> None:
    findings_db.insert_entities(db, node_id, [(etype, value)], source=source)


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "b7f_entities.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


def test_common_returns_match_count(auth_client, active_db):
    a = _insert_node(active_db, "http://a.onion/")
    b = _insert_node(active_db, "http://b.onion/")
    c = _insert_node(active_db, "http://c.onion/")
    for nid in (a, b, c):
        _insert_entity(active_db, nid, "btc", "1A")
    _insert_entity(active_db, a, "email", "x@x")
    _insert_entity(active_db, b, "email", "x@x")

    r = auth_client.get(f"/api/entities/common?node_ids={a},{b},{c}")
    assert r.status_code == 200
    rows = r.json()["entities"]
    btc = next(e for e in rows if e["type"] == "btc")
    assert btc["matches"] == 3
    assert btc["total"] == 3
    email = next(e for e in rows if e["type"] == "email")
    assert email["matches"] == 2


def test_common_requires_two_matches(auth_client, active_db):
    a = _insert_node(active_db, "http://a.onion/")
    b = _insert_node(active_db, "http://b.onion/")
    _insert_entity(active_db, a, "btc", "lone")
    rows = auth_client.get(f"/api/entities/common?node_ids={a},{b}").json()["entities"]
    assert rows == []


def test_common_excludes_stubs(auth_client, active_db):
    a = _insert_node(active_db, "http://a.onion/")
    b_stub = _insert_node(active_db, "http://b.onion/", stub=True)
    _insert_entity(active_db, a, "btc", "shared")
    _insert_entity(active_db, b_stub, "btc", "shared")
    rows = auth_client.get(
        f"/api/entities/common?node_ids={a},{b_stub}"
    ).json()["entities"]
    # b is a stub → its entity row doesn't count → only 1 match → filtered out.
    assert rows == []


def test_common_empty_node_ids_400(auth_client, active_db):
    r = auth_client.get("/api/entities/common")
    assert r.status_code == 400
    assert r.json()["error"] == "bad_node_ids"


def test_common_blank_node_ids_400(auth_client, active_db):
    r = auth_client.get("/api/entities/common?node_ids=")
    assert r.status_code == 400


def test_common_non_numeric_400(auth_client, active_db):
    r = auth_client.get("/api/entities/common?node_ids=1,abc,3")
    assert r.status_code == 400
    assert r.json()["error"] == "bad_node_ids"


def test_common_too_many_ids_400(auth_client, active_db):
    ids = ",".join(str(i) for i in range(1, 250))
    r = auth_client.get(f"/api/entities/common?node_ids={ids}")
    assert r.status_code == 400
    assert r.json()["error"] == "too_many_ids"
