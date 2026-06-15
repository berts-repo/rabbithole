"""HTTP surface for crawl intake — ``routes/crawl_queue.py``.

After the schema-reset Phase 6 dead-code sweep this route is enqueue-only:
``POST /api/crawl/queue`` writes a pending ``jobs`` row with ``kind='crawl'``
whose crawl config lives in ``payload``. Listing, editing, cancelling and
retrying crawl jobs moved to the unified jobs API (``routes/jobs.py``) and the
Activity tab, so those endpoints — and their tests — were removed here.

Each test runs with ``crawl.queue_paused = true`` so the runner's
``try_advance`` no-ops at the end of every POST and the surface stays
deterministic — dispatch behaviour lives in the queue-runner tests.
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

# Mirrors routes/crawl_queue.py::DEFAULT_MAX_DEPTH.
DEFAULT_MAX_DEPTH = 3


@pytest.fixture
def active_db(app, tmp_path: Path):
    """Attach a fresh ``CrawlDB`` with the queue paused so route tests can
    observe enqueue behaviour without the runner racing them to claim."""
    db = CrawlDB(tmp_path / "queue_routes.db")
    settings_db.put_setting(db, "crawl.queue_paused", "true")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


def _enqueue(auth_client, url: str = SEED_URL, **over) -> int:
    """POST one URL and return the created crawl job id."""
    body = {"url": url, "mode": "Cross-site", "source": "manual", **over}
    r = auth_client.post("/api/crawl/queue", json=body)
    assert r.status_code == 200, r.text
    return r.json()["results"][0]["job_id"]


# ---------------------------------------------------------------------------
# POST /api/crawl/queue
# ---------------------------------------------------------------------------


def test_post_queue_single_url_enqueues(auth_client, active_db):
    r = auth_client.post(
        "/api/crawl/queue",
        json={"url": SEED_URL, "mode": "Cross-site", "source": "manual"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["results"]) == 1
    row = body["results"][0]
    assert row["inserted"] is True
    assert row["url"] == SEED_URL
    assert row["state"] == "unknown"
    assert isinstance(row["job_id"], int)
    # The enqueued job is a pending crawl job.
    job = jobs_db.get_job(active_db, row["job_id"])
    assert job["kind"] == "crawl"
    assert job["status"] == "pending"


def test_post_queue_batch_returns_per_row_outcomes(auth_client, active_db):
    r = auth_client.post(
        "/api/crawl/queue",
        json={
            "urls": [SEED_URL, OTHER_URL, SEED_URL],
            "mode": "Cross-site",
            "source": "bulk",
        },
    )
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert len(results) == 3
    assert [r["inserted"] for r in results] == [True, True, False]
    assert results[2]["reason"] == "duplicate_in_batch"


def test_post_queue_validates_mixed_url_shape(auth_client, active_db):
    """Sending both ``url`` and ``urls`` is ambiguous — the route refuses
    it rather than guessing which field wins."""
    r = auth_client.post(
        "/api/crawl/queue",
        json={
            "url": SEED_URL,
            "urls": [OTHER_URL],
            "mode": "Cross-site",
            "source": "manual",
        },
    )
    assert r.status_code == 400
    assert r.json()["error"] == "bad_field"


def test_post_queue_rejects_unknown_mode(auth_client, active_db):
    r = auth_client.post(
        "/api/crawl/queue",
        json={"url": SEED_URL, "mode": "Magic", "source": "manual"},
    )
    assert r.status_code == 400


def test_post_queue_rejects_clearnet_per_url(auth_client, active_db):
    """Bad URLs collapse to a per-row ``bad_url`` outcome rather than
    failing the whole batch — matches the spec's "duplicate within a
    paste is silent" tolerance for noisy inputs."""
    r = auth_client.post(
        "/api/crawl/queue",
        json={
            "urls": ["http://example.com/", SEED_URL],
            "mode": "Cross-site",
            "source": "bulk",
        },
    )
    assert r.status_code == 200
    results = r.json()["results"]
    inserted = [r for r in results if r.get("inserted") is True]
    errors = [r for r in results if r.get("reason") == "bad_url"]
    assert len(inserted) == 1
    assert inserted[0]["url"] == SEED_URL
    assert len(errors) == 1
    assert errors[0]["url"] == "http://example.com/"


def test_post_queue_applies_default_max_depth(auth_client, active_db):
    """``use_default_max_depth=true`` lets a frontend post without knowing
    the constant — the route applies it into the job payload."""
    job_id = _enqueue(auth_client, use_default_max_depth=True)
    job = jobs_db.get_job(active_db, job_id)
    assert job["payload"]["max_depth"] == DEFAULT_MAX_DEPTH


def test_post_queue_accepts_explicit_unlimited(auth_client, active_db):
    job_id = _enqueue(auth_client, max_depth=None)
    job = jobs_db.get_job(active_db, job_id)
    assert job["payload"]["max_depth"] is None


# ---------------------------------------------------------------------------
# Pause flag blocks dispatch but not enqueue
# ---------------------------------------------------------------------------


def test_pause_blocks_dispatch_but_not_enqueue(auth_client, active_db):
    """Active-db fixture pauses the queue. POSTing must still write a
    ``pending`` crawl job; the runner's ``try_advance`` no-ops behind the
    gate."""
    job_id = _enqueue(auth_client)
    assert jobs_db.get_job(active_db, job_id)["status"] == "pending"
