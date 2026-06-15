"""HTTP surface for domain snapshot comparison — ``routes/domains.py``.

"As of date D" = each page's latest version with ``date(fetched_at) <= D``.
The comparison classifies each page added / removed / drifted / identical
between two such dates, reusing the accumulating ``page_versions`` history.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import page_versions as versions_db
from backend.db.core import CrawlDB


ONION = "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad"
HOST = f"{ONION}.onion"
P1 = f"http://{HOST}/one"
P2 = f"http://{HOST}/two"
P3 = f"http://{HOST}/three"


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "domain_compare.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


def _crawl(db: CrawlDB, url: str, clean: str, when: str) -> None:
    versions_db.record_fetch(
        db,
        url=url,
        host=HOST,
        status_code=200,
        title="t",
        body_text=clean,
        body_text_clean=clean,
        response_headers={},
        when=when,
    )


def _seed(db: CrawlDB) -> None:
    # Day 1: p1 + p2 exist.
    _crawl(db, P1, "p1 original", "2026-05-01T10:00:00+00:00")
    _crawl(db, P2, "p2 stable", "2026-05-01T10:01:00+00:00")
    # Day 2: p1 changes, p2 re-crawled unchanged, p3 appears.
    _crawl(db, P1, "p1 EDITED", "2026-05-02T10:00:00+00:00")
    _crawl(db, P2, "p2 stable", "2026-05-02T10:01:00+00:00")
    _crawl(db, P3, "p3 new page", "2026-05-02T10:02:00+00:00")


def test_snapshots_lists_distinct_dates_newest_first(auth_client, active_db):
    _seed(active_db)
    r = auth_client.get(f"/api/domains/{HOST}/snapshots")
    assert r.status_code == 200, r.text
    assert r.json()["dates"] == ["2026-05-02", "2026-05-01"]


def test_compare_classifies_added_drifted_identical(auth_client, active_db):
    _seed(active_db)
    r = auth_client.get(
        f"/api/domains/{HOST}/compare", params={"a": "2026-05-01", "b": "2026-05-02"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["a"] == "2026-05-01"
    assert body["b"] == "2026-05-02"
    assert body["added"] == 1  # p3
    assert body["drifted"] == 1  # p1
    assert body["identical"] == 1  # p2
    assert body["removed"] == 0
    by_url = {p["url"]: p for p in body["pages"]}
    # Identical pages are counted but not listed.
    assert P2 not in by_url
    assert by_url[P1]["status"] == "drifted"
    assert by_url[P1]["a_version_id"] is not None
    assert by_url[P1]["b_version_id"] is not None
    assert by_url[P3]["status"] == "added"
    assert by_url[P3]["a_version_id"] is None


def test_compare_orders_dates_so_a_is_earlier(auth_client, active_db):
    _seed(active_db)
    # Pass the dates reversed — the route normalizes A→earlier.
    r = auth_client.get(
        f"/api/domains/{HOST}/compare", params={"a": "2026-05-02", "b": "2026-05-01"}
    )
    body = r.json()
    assert body["a"] == "2026-05-01"
    assert body["b"] == "2026-05-02"
    assert body["added"] == 1  # p3 still "added" going forward in time


def test_compare_unknown_host_404(auth_client, active_db):
    r = auth_client.get(
        f"/api/domains/{'z' * 56}.onion/compare",
        params={"a": "2026-05-01", "b": "2026-05-02"},
    )
    assert r.status_code == 404


def test_snapshots_unknown_host_404(auth_client, active_db):
    r = auth_client.get(f"/api/domains/{'z' * 56}.onion/snapshots")
    assert r.status_code == 404
