"""Phase B8 — search-engine registry CRUD + project preseed."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import search_engines as search_engines_db
from backend.db.core import CrawlDB
from backend.db.settings import get_setting


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "b8_engines.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


# --- DB layer -------------------------------------------------------------


def test_seed_defaults_inserts_default_engines(tmp_path: Path):
    db = CrawlDB(tmp_path / "seed.db")
    try:
        expected = len(search_engines_db.DEFAULT_ENGINES)
        inserted = search_engines_db.seed_defaults(db)
        assert inserted == expected
        rows = search_engines_db.list_engines(db)
        labels = {r["label"] for r in rows}
        assert "Ahmia" in labels
        assert "OnionLand" in labels
        # Each gets enabled=true in settings.
        for row in rows:
            flag = get_setting(db, f"search.engine.{row['id']}.enabled")
            assert flag == "true"
    finally:
        db.close()


def test_seed_defaults_idempotent(tmp_path: Path):
    db = CrawlDB(tmp_path / "seed.db")
    try:
        search_engines_db.seed_defaults(db)
        added = search_engines_db.seed_defaults(db)
        assert added == 0
        assert len(search_engines_db.list_engines(db)) == len(
            search_engines_db.DEFAULT_ENGINES
        )
    finally:
        db.close()


# --- routes ---------------------------------------------------------------


def test_list_search_engines_empty_initially(auth_client, active_db):
    r = auth_client.get("/api/search-engines")
    assert r.status_code == 200
    assert r.json() == {"engines": []}


def test_create_engine_accepts_v3_onion(auth_client, active_db):
    url = "http://" + ("a" * 56) + ".onion/?q={q}"
    r = auth_client.post(
        "/api/search-engines",
        json={"label": "TestEngine", "url": url},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["label"] == "TestEngine"
    assert body["url"] == url


def test_create_engine_rejects_clearnet(auth_client, active_db):
    r = auth_client.post(
        "/api/search-engines",
        json={"label": "Bad", "url": "https://example.com/?q={q}"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "bad_url"


def test_create_engine_rejects_v2_onion(auth_client, active_db):
    # 16-char base32 = v2; v3 (56 chars) is the only allowed shape.
    r = auth_client.post(
        "/api/search-engines",
        json={"label": "OldStyle", "url": "http://aaaaaaaaaaaaaaaa.onion/?q={q}"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "bad_url"


def test_delete_engine(auth_client, active_db):
    url = "http://" + ("b" * 56) + ".onion/?q={q}"
    r = auth_client.post(
        "/api/search-engines",
        json={"label": "ToDelete", "url": url},
    )
    eid = r.json()["id"]
    r2 = auth_client.delete(f"/api/search-engines/{eid}")
    assert r2.status_code == 200
    r3 = auth_client.delete(f"/api/search-engines/{eid}")
    assert r3.status_code == 404


def test_duplicate_url_rejected(auth_client, active_db):
    url = "http://" + ("c" * 56) + ".onion/?q={q}"
    r = auth_client.post(
        "/api/search-engines", json={"label": "First", "url": url}
    )
    assert r.status_code == 200
    r2 = auth_client.post(
        "/api/search-engines", json={"label": "Second", "url": url}
    )
    assert r2.status_code == 400
    assert r2.json()["error"] == "duplicate_url"


def test_update_engine_edits_label_and_url(auth_client, active_db):
    url = "http://" + ("d" * 56) + ".onion/?q={q}"
    eid = auth_client.post(
        "/api/search-engines", json={"label": "Before", "url": url}
    ).json()["id"]

    new_url = "http://" + ("e" * 56) + ".onion/search?query={q}"
    r = auth_client.patch(
        f"/api/search-engines/{eid}",
        json={"label": "After", "url": new_url},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {
        "id": eid,
        "label": "After",
        "url": new_url,
        "network": "tor",
    }

    rows = auth_client.get("/api/search-engines").json()["engines"]
    row = next(e for e in rows if e["id"] == eid)
    assert row["label"] == "After"
    assert row["url"] == new_url


def test_update_engine_404_on_unknown(auth_client, active_db):
    url = "http://" + ("f" * 56) + ".onion/?q={q}"
    r = auth_client.patch(
        "/api/search-engines/9999", json={"label": "Ghost", "url": url}
    )
    assert r.status_code == 404
    assert r.json()["error"] == "unknown_engine"


def test_update_engine_rejects_clearnet(auth_client, active_db):
    url = "http://" + ("g" * 56) + ".onion/?q={q}"
    eid = auth_client.post(
        "/api/search-engines", json={"label": "Keep", "url": url}
    ).json()["id"]
    r = auth_client.patch(
        f"/api/search-engines/{eid}",
        json={"label": "Keep", "url": "https://example.com/?q={q}"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "bad_url"


def test_update_engine_rejects_duplicate_url(auth_client, active_db):
    url_a = "http://" + ("h" * 56) + ".onion/?q={q}"
    url_b = "http://" + ("i" * 56) + ".onion/?q={q}"
    auth_client.post("/api/search-engines", json={"label": "A", "url": url_a})
    b_id = auth_client.post(
        "/api/search-engines", json={"label": "B", "url": url_b}
    ).json()["id"]
    r = auth_client.patch(
        f"/api/search-engines/{b_id}", json={"label": "B", "url": url_a}
    )
    assert r.status_code == 400
    assert r.json()["error"] == "duplicate_url"
