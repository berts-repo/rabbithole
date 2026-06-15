"""HTTP surface for page-version reads — ``routes/pages.py``.

Each crawl of a URL appends a ``page_versions`` row, so a page accumulates a
timeline. These endpoints back the Phase-5 versioning UI: pull one full
snapshot, and diff two snapshots of the same page on demand (stdlib difflib
over ``body_text_clean``).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import page_versions as versions_db
from backend.db.core import CrawlDB
from backend.routes.pages import build_diff_lines


ONION = "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad"
HOST = f"{ONION}.onion"
URL = f"http://{HOST}/"
OTHER = "abacus" * 9 + "22"
OTHER_HOST = f"{OTHER}.onion"
OTHER_URL = f"http://{OTHER_HOST}/"


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "pages_versions.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


def _crawl(db: CrawlDB, *, url: str, host: str, clean: str, when: str) -> int:
    """Append one page version; returns its version id."""
    return versions_db.record_fetch(
        db,
        url=url,
        host=host,
        status_code=200,
        title="t",
        body_text=clean,
        body_text_clean=clean,
        response_headers={},
        when=when,
    )[1]


# --- pure diff builder ------------------------------------------------------


def test_build_diff_lines_classifies_add_remove_context():
    lines, truncated = build_diff_lines(
        ["alpha", "beta", "gamma"],
        ["alpha", "delta", "gamma"],
    )
    assert truncated is False
    ops = [(line["op"], line["text"]) for line in lines]
    assert ("remove", "beta") in ops
    assert ("add", "delta") in ops
    assert ("context", "alpha") in ops
    assert ("context", "gamma") in ops


def test_build_diff_lines_identical_yields_nothing():
    lines, truncated = build_diff_lines(["a", "b"], ["a", "b"])
    assert lines == []
    assert truncated is False


# --- GET /api/pages/versions/{id} ------------------------------------------


def test_get_version_returns_full_body(auth_client, active_db):
    vid = _crawl(active_db, url=URL, host=HOST, clean="hello world", when="2026-05-01T00:00:00+00:00")
    r = auth_client.get(f"/api/pages/versions/{vid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == vid
    assert body["body_text_clean"] == "hello world"
    assert body["http_status"] == 200


def test_get_version_404(auth_client, active_db):
    r = auth_client.get("/api/pages/versions/9999")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_version"


# --- GET /api/pages/versions/{a}/diff/{b} ----------------------------------


def test_diff_orders_old_to_new_regardless_of_arg_order(auth_client, active_db):
    v1 = _crawl(active_db, url=URL, host=HOST, clean="line one\nline two", when="2026-05-01T00:00:00+00:00")
    v2 = _crawl(active_db, url=URL, host=HOST, clean="line one\nline three", when="2026-05-02T00:00:00+00:00")
    # Pass newest first — the route must still read old→new.
    r = auth_client.get(f"/api/pages/versions/{v2}/diff/{v1}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["a"]["id"] == v1
    assert body["b"]["id"] == v2
    assert body["identical"] is False
    assert body["added"] == 1
    assert body["removed"] == 1
    ops = [(line["op"], line["text"]) for line in body["lines"]]
    assert ("remove", "line two") in ops
    assert ("add", "line three") in ops


def test_diff_identical_versions(auth_client, active_db):
    v1 = _crawl(active_db, url=URL, host=HOST, clean="same", when="2026-05-01T00:00:00+00:00")
    v2 = _crawl(active_db, url=URL, host=HOST, clean="same", when="2026-05-02T00:00:00+00:00")
    r = auth_client.get(f"/api/pages/versions/{v1}/diff/{v2}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["identical"] is True
    assert body["added"] == 0 and body["removed"] == 0
    assert body["lines"] == []


def test_diff_rejects_cross_page(auth_client, active_db):
    v1 = _crawl(active_db, url=URL, host=HOST, clean="a", when="2026-05-01T00:00:00+00:00")
    v2 = _crawl(active_db, url=OTHER_URL, host=OTHER_HOST, clean="b", when="2026-05-01T00:00:00+00:00")
    r = auth_client.get(f"/api/pages/versions/{v1}/diff/{v2}")
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "cross_page_diff"


def test_diff_404_on_unknown_version(auth_client, active_db):
    v1 = _crawl(active_db, url=URL, host=HOST, clean="a", when="2026-05-01T00:00:00+00:00")
    r = auth_client.get(f"/api/pages/versions/{v1}/diff/9999")
    assert r.status_code == 404
    assert r.json()["detail"]["id"] == 9999
