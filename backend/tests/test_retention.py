"""Job-history retention — validator, DB prune/count, and the HTTP surface.

Retention deletes terminal job rows finished more than ``retention.jobs_days``
days ago and touches nothing else. These tests pin: the setting validator's
range, that active and recent rows survive a prune, that 0 days is a no-op, and
that the route reports/executes against the stored window.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.db import jobs as jobs_db
from backend.db import settings as settings_db
from backend.db.core import CrawlDB


def _old_iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(
        timespec="seconds"
    )


def _backdate(db: CrawlDB, job_id: int, days_ago: int) -> None:
    with db.transaction(immediate=True) as c:
        c.execute(
            "UPDATE jobs SET finished_at=? WHERE id=?", (_old_iso(days_ago), job_id)
        )


@pytest.fixture
def db(tmp_path: Path):
    d = CrawlDB(tmp_path / "retention.db")
    try:
        yield d
    finally:
        d.close()


# --- validator --------------------------------------------------------------


def test_validator_accepts_range(db: CrawlDB):
    assert settings_db.put_setting(db, "retention.jobs_days", 0) == "0"
    assert settings_db.put_setting(db, "retention.jobs_days", 30) == "30"
    assert settings_db.put_setting(db, "retention.jobs_days", 3650) == "3650"


def test_validator_rejects_out_of_range(db: CrawlDB):
    for bad in (-1, 3651):
        with pytest.raises(ValueError):
            settings_db.put_setting(db, "retention.jobs_days", bad)


# --- prune / count ----------------------------------------------------------


def test_prune_removes_only_old_terminal_jobs(db: CrawlDB):
    old_done = jobs_db.create_job(
        db, kind="crawl", target_type="url", target_id=1, status="done"
    )
    old_failed = jobs_db.create_job(
        db, kind="analysis", target_type="url", target_id=2, status="failed"
    )
    recent_done = jobs_db.create_job(
        db, kind="crawl", target_type="url", target_id=3, status="done"
    )
    active = jobs_db.create_job(
        db, kind="crawl", target_type="url", target_id=4, status="pending"
    )
    _backdate(db, old_done, 40)
    _backdate(db, old_failed, 40)
    _backdate(db, recent_done, 5)

    assert jobs_db.count_prunable_terminal_jobs(db, older_than_days=30) == 2
    assert jobs_db.prune_terminal_jobs(db, older_than_days=30) == 2

    surviving = {j["id"] for j in jobs_db.list_jobs(db, limit=100)}
    assert surviving == {recent_done, active}
    # idempotent: a second run with nothing eligible removes nothing.
    assert jobs_db.prune_terminal_jobs(db, older_than_days=30) == 0


def test_zero_days_is_a_noop(db: CrawlDB):
    old_done = jobs_db.create_job(
        db, kind="crawl", target_type="url", target_id=1, status="done"
    )
    _backdate(db, old_done, 999)
    assert jobs_db.count_prunable_terminal_jobs(db, older_than_days=0) == 0
    assert jobs_db.prune_terminal_jobs(db, older_than_days=0) == 0
    assert len(jobs_db.list_jobs(db, limit=100)) == 1


# --- route ------------------------------------------------------------------


@pytest.fixture
def active_db(app, tmp_path: Path):
    d = CrawlDB(tmp_path / "retention_route.db")
    app.state.project_state.active_db = d
    app.state.project_state.active_id = "test"
    try:
        yield d
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        d.close()


def test_route_status_and_run(auth_client, active_db: CrawlDB):
    settings_db.put_setting(active_db, "retention.jobs_days", 30)
    old_done = jobs_db.create_job(
        active_db, kind="crawl", target_type="url", target_id=1, status="done"
    )
    _backdate(active_db, old_done, 40)

    status = auth_client.get("/api/retention/status").json()
    assert status == {"jobs_days": 30, "eligible_jobs": 1}

    run = auth_client.post("/api/retention/run").json()
    assert run == {"jobs_days": 30, "deleted_jobs": 1}
    assert jobs_db.list_jobs(active_db, limit=100) == []
