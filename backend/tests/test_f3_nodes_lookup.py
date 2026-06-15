"""F3 — POST /api/nodes/lookup batch URL state check.

Used by the bulk-import list in the Crawl sub-tab to badge each pasted
row as crawled / known / unknown / invalid.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import page_versions as versions_db
from backend.db import resources as resources_db
from backend.db.core import CrawlDB
from backend.routes.nodes import LOOKUP_MAX


ONION_A = "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad"
ONION_B = "abacus" * 9 + "22"
URL_A = f"http://{ONION_A}.onion/"
URL_B = f"http://{ONION_B}.onion/"
URL_UNKNOWN = f"http://{'z' * 50 + 'abcdef'}.onion/"


def _host(url: str) -> str:
    return url.split("//", 1)[1].split("/", 1)[0]


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "f3_lookup.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


def _make_crawled(db: CrawlDB, url: str) -> int:
    """Crawl a URL directly so the test doesn't depend on the crawler."""
    return versions_db.record_fetch(
        db,
        url=url,
        host=_host(url),
        status_code=200,
        title="t",
        body_text="x",
        body_text_clean="x",
        response_headers={},
        when="2026-05-12T00:00:00+00:00",
    )[0]


def test_lookup_classifies_states(auth_client, active_db):
    resources_db.upsert_resource(active_db, URL_A, _host(URL_A), state="known")
    _make_crawled(active_db, URL_B)

    r = auth_client.post(
        "/api/nodes/lookup",
        json={"urls": [URL_A, URL_B, URL_UNKNOWN, "not-a-url"]},
    )
    assert r.status_code == 200
    results = r.json()["results"]
    assert results[URL_A]["state"] == "known"
    assert "id" in results[URL_A]
    assert results[URL_B]["state"] == "crawled"
    assert results[URL_UNKNOWN]["state"] == "unknown"
    assert results["not-a-url"]["state"] == "invalid"


def test_lookup_returns_empty_for_empty_input(auth_client, active_db):
    r = auth_client.post("/api/nodes/lookup", json={"urls": []})
    assert r.status_code == 200
    assert r.json()["results"] == {}


def test_lookup_caps_at_max(auth_client, active_db):
    too_many = [URL_A] * (LOOKUP_MAX + 1)
    r = auth_client.post("/api/nodes/lookup", json={"urls": too_many})
    assert r.status_code == 400
    assert r.json()["error"] == "too_many_urls"


def test_lookup_preserves_input_keys(auth_client, active_db):
    """Whitespace in the input should not collide canonical results."""
    resources_db.upsert_resource(active_db, URL_A, _host(URL_A), state="known")
    r = auth_client.post(
        "/api/nodes/lookup",
        json={"urls": [f"  {URL_A}  ", URL_A]},
    )
    results = r.json()["results"]
    assert results[f"  {URL_A}  "]["state"] == "known"
    assert results[URL_A]["state"] == "known"
