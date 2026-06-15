"""HTTP surface for batch intake — ``routes/jobs.py`` stage + run.

A batch stages as one ``pending`` ``kind='batch'`` job holding the URL list;
Run spawns one ``kind='crawl'`` child per URL and marks the batch ``done``;
Discard is the existing cancel path. The queue is paused on the test DB so the
runner's ``try_advance`` no-ops and spawned children stay ``pending`` for us to
observe.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import jobs as jobs_db
from backend.db import settings as settings_db
from backend.db.core import CrawlDB


SEED = "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad"
SEED_URL = f"http://{SEED}.onion/"
OTHER = "abacus" * 9 + "22"
OTHER_URL = f"http://{OTHER}.onion/"
THIRD_URL = f"http://{'z' * 56}.onion/"


@pytest.fixture
def active_db(app, tmp_path: Path):
    db = CrawlDB(tmp_path / "jobs_batch_routes.db")
    settings_db.put_setting(db, "crawl.queue_paused", "true")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


# --- POST /api/jobs/batch (stage) ------------------------------------------


def test_stage_creates_pending_batch_with_cleaned_urls(auth_client, active_db):
    r = auth_client.post(
        "/api/jobs/batch",
        json={"urls": [SEED_URL, OTHER_URL], "mode": "Cross-site"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["staged"] == 2
    assert body["rejected"] == []
    job = body["job"]
    assert job["kind"] == "batch"
    assert job["status"] == "pending"
    assert job["payload"]["urls"] == [SEED_URL, OTHER_URL]
    assert job["payload"]["count"] == 2
    # No crawl children spawned at stage time.
    crawls = jobs_db.list_jobs(active_db, kind="crawl")
    assert crawls == []


def test_stage_dedupes_within_paste_and_rejects_clearnet(auth_client, active_db):
    r = auth_client.post(
        "/api/jobs/batch",
        json={
            "urls": [SEED_URL, SEED_URL, "http://example.com/", OTHER_URL],
            "mode": "BFS",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job"]["payload"]["urls"] == [SEED_URL, OTHER_URL]
    assert body["staged"] == 2
    assert len(body["rejected"]) == 1
    assert body["rejected"][0]["reason"] == "bad_url"


def test_stage_with_no_valid_urls_is_bad_field(auth_client, active_db):
    r = auth_client.post(
        "/api/jobs/batch",
        json={"urls": ["http://example.com/"], "mode": "Cross-site"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "bad_field"


def test_stage_rejects_unknown_mode(auth_client, active_db):
    r = auth_client.post(
        "/api/jobs/batch", json={"urls": [SEED_URL], "mode": "Magic"}
    )
    assert r.status_code == 400
    assert r.json()["error"] == "bad_field"


# --- POST /api/jobs/:id/run (spawn children) -------------------------------


def test_run_spawns_crawl_children_and_completes_batch(auth_client, active_db):
    staged = auth_client.post(
        "/api/jobs/batch",
        json={"urls": [SEED_URL, OTHER_URL], "mode": "Cross-site", "priority": 2},
    ).json()["job"]

    r = auth_client.post(f"/api/jobs/{staged['id']}/run")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["spawned"] == 2
    assert body["skipped"] == 0
    assert body["job"]["status"] == "done"
    child_ids = body["job"]["result"]["child_job_ids"]
    assert len(child_ids) == 2

    crawls = jobs_db.list_jobs(active_db, kind="crawl")
    assert {c["id"] for c in crawls} == set(child_ids)
    assert all(c["status"] == "pending" for c in crawls)
    # Children inherit the batch's crawl config.
    assert all(c["payload"]["mode"] == "Cross-site" for c in crawls)
    assert all(c["payload"]["priority"] == 2 for c in crawls)


def test_run_skips_urls_with_an_active_crawl_job(auth_client, active_db):
    # Pre-seed an in-flight crawl for SEED_URL.
    jobs_db.create_job(
        active_db,
        kind="crawl",
        target_type="url",
        target_id=0,
        status="pending",
        payload={"url": SEED_URL, "mode": "BFS"},
    )
    staged = auth_client.post(
        "/api/jobs/batch",
        json={"urls": [SEED_URL, OTHER_URL], "mode": "BFS"},
    ).json()["job"]

    body = auth_client.post(f"/api/jobs/{staged['id']}/run").json()
    assert body["spawned"] == 1
    assert body["skipped"] == 1


def test_run_is_batch_only(auth_client, active_db):
    crawl_id = jobs_db.create_job(
        active_db,
        kind="crawl",
        target_type="url",
        target_id=0,
        status="pending",
        payload={"url": SEED_URL, "mode": "BFS"},
    )
    r = auth_client.post(f"/api/jobs/{crawl_id}/run")
    assert r.status_code == 409
    assert r.json()["error"] == "not_runnable"


def test_run_is_one_shot(auth_client, active_db):
    staged = auth_client.post(
        "/api/jobs/batch", json={"urls": [SEED_URL], "mode": "BFS"}
    ).json()["job"]
    assert auth_client.post(f"/api/jobs/{staged['id']}/run").status_code == 200
    # Second run is refused — the batch is no longer pending.
    again = auth_client.post(f"/api/jobs/{staged['id']}/run")
    assert again.status_code == 409
    assert again.json()["error"] == "not_runnable"


def test_run_missing_batch_is_404(auth_client, active_db):
    r = auth_client.post("/api/jobs/999999/run")
    assert r.status_code == 404


def test_discard_via_cancel_marks_batch_cancelled(auth_client, active_db):
    """A pending batch is non-terminal, so the existing cancel path discards
    it (no crawl children were ever created)."""
    staged = auth_client.post(
        "/api/jobs/batch", json={"urls": [SEED_URL], "mode": "BFS"}
    ).json()["job"]
    r = auth_client.post(f"/api/jobs/{staged['id']}/cancel")
    assert r.status_code == 200, r.text
    assert jobs_db.get_job(active_db, staged["id"])["status"] == "cancelled"
    assert jobs_db.list_jobs(active_db, kind="crawl") == []
