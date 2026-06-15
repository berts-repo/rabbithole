"""Schedule-producer step of the crawl queue runner (``produce_scheduled_rows``).

Post schema-reset, the producer's only job is "compute next fire, push a
``jobs`` row (``kind='crawl'``, ``status='pending'``, ``payload.source=
'schedule'``), return." Dispatch (one-at-a-time runner, kill-switch hold,
pause gate) is owned by the runner's other half (``try_advance``), so the
producer ignores both — schedules keep enqueuing during a Tor outage and drain
FIFO when the switch clears.

These tests drive ``produce_scheduled_rows`` directly with a deterministic
``clock`` (so they never sleep) and assert against the schedule-sourced crawl
``jobs`` rows — the unified ``jobs`` table replaced the old ``crawl_queue``
table. "Last fire" is the most recent schedule-sourced crawl job's
``created_at``; since ``jobs_db.create_job`` always stamps the current time, a
simulated prior fire is backdated with a direct ``UPDATE``.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.crawler.runtime import CrawlRunnerRegistry
from backend.db import crawl as crawl_db
from backend.db import jobs as jobs_db
from backend.db.core import CrawlDB
from backend.services.crawl_queue_runner import CrawlQueueRunner
from backend.services.event_bus import EventBus
from backend.services.graph_cache import GraphCache


SEED = "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad"
SEED_URL = f"http://{SEED}.onion/"


class _FakeKillSwitch:
    def __init__(self) -> None:
        self.engaged = asyncio.Event()


class _FakeProjectState:
    def __init__(self, db: CrawlDB) -> None:
        self.active_db = db
        self.graph_cache = GraphCache()


@pytest.fixture
def db(tmp_path: Path):
    instance = CrawlDB(tmp_path / "sched.db")
    try:
        yield instance
    finally:
        instance.close()


def _runner(db, *, clock_value: datetime) -> CrawlQueueRunner:
    return CrawlQueueRunner(
        project_state=_FakeProjectState(db),  # type: ignore[arg-type]
        kill_switch=_FakeKillSwitch(),  # type: ignore[arg-type]
        event_bus=EventBus(),
        registry=CrawlRunnerRegistry(),
        clock=lambda: clock_value,
    )


def _schedule_jobs(db) -> list[dict]:
    """Schedule-sourced crawl jobs — the producer's output rows."""
    return [
        j
        for j in jobs_db.list_jobs(db, kind="crawl", limit=1000)
        if (j.get("payload") or {}).get("source") == "schedule"
    ]


def _seed_prior_fire(db, *, url: str, when: datetime, status: str = "done") -> int:
    """Insert a schedule-sourced crawl job and backdate its ``created_at`` to
    ``when`` so the producer's "last fire" interval maths sees a prior fire."""
    job_id = jobs_db.create_job(
        db,
        kind="crawl",
        target_type="url",
        target_id=0,
        status=status,
        payload={"url": url, "mode": "BFS", "source": "schedule", "max_depth": None},
    )
    with db.transaction(immediate=True) as c:
        c.execute(
            "UPDATE jobs SET created_at=? WHERE id=?",
            (when.isoformat(timespec="seconds"), job_id),
        )
    return job_id


def test_produce_enqueues_when_interval_elapsed(db):
    crawl_db.upsert_schedule(
        db, url=SEED_URL, label=None, interval_hours=1.0, mode="BFS",
        collection_id=None, active=True,
    )
    now = datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc)
    runner = _runner(db, clock_value=now)

    fired = runner.produce_scheduled_rows()
    assert fired == 1

    # The fire landed as a pending schedule-sourced crawl job.
    jobs = _schedule_jobs(db)
    assert len(jobs) == 1
    payload = jobs[0]["payload"]
    assert payload["url"] == SEED_URL
    assert payload["mode"] == "BFS"
    assert payload["source"] == "schedule"
    assert jobs[0]["status"] == "pending"
    # ``crawls`` history stays empty until the dispatcher picks the job up.
    assert crawl_db.list_crawls(db) == []


def test_produce_skips_when_interval_not_elapsed(db):
    crawl_db.upsert_schedule(
        db, url=SEED_URL, label=None, interval_hours=4.0, mode="BFS",
        collection_id=None, active=True,
    )
    # A prior fire that already completed 30 min ago (terminal, so only the
    # interval gate — not the active-job guard — can cause the skip).
    last_fire = datetime(2026, 5, 12, 11, 30, tzinfo=timezone.utc)
    _seed_prior_fire(db, url=SEED_URL, when=last_fire, status="done")

    now = last_fire + timedelta(hours=1)  # only 1 of the 4-hour interval
    runner = _runner(db, clock_value=now)

    fired = runner.produce_scheduled_rows()
    assert fired == 0
    # No new fire created.
    assert len(_schedule_jobs(db)) == 1


def test_produce_enqueues_even_when_kill_switch_engaged(db):
    """The kill switch is a dispatch gate, not an intake gate. Schedules still
    produce jobs during a Tor outage; the dispatcher blocks ``try_advance``
    until the switch clears."""
    crawl_db.upsert_schedule(
        db, url=SEED_URL, label=None, interval_hours=0.001, mode="BFS",
        collection_id=None, active=True,
    )
    runner = _runner(db, clock_value=datetime.now(timezone.utc))
    runner.kill_switch.engaged.set()  # type: ignore[attr-defined]
    fired = runner.produce_scheduled_rows()
    assert fired == 1
    assert len(_schedule_jobs(db)) == 1


def test_produce_skips_inactive_schedules(db):
    crawl_db.upsert_schedule(
        db, url=SEED_URL, label=None, interval_hours=0.001, mode="BFS",
        collection_id=None, active=False,
    )
    runner = _runner(db, clock_value=datetime.now(timezone.utc))
    fired = runner.produce_scheduled_rows()
    assert fired == 0
    assert _schedule_jobs(db) == []


def test_produce_does_not_double_enqueue_while_prior_job_pending(db):
    """If the previous fire's crawl job is still active (e.g. the runner is
    paused), the next pass must not enqueue a duplicate — the active-job guard
    skips silently rather than logging a spurious error every tick."""
    crawl_db.upsert_schedule(
        db, url=SEED_URL, label=None, interval_hours=0.001, mode="BFS",
        collection_id=None, active=True,
    )
    runner = _runner(
        db, clock_value=datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc)
    )

    first = runner.produce_scheduled_rows()
    assert first == 1
    assert len(_schedule_jobs(db)) == 1

    # Advance past the interval. The first job is still pending; the new pass
    # must see the outstanding job and skip, not error out.
    runner.clock = lambda: datetime(2026, 5, 12, 13, 0, tzinfo=timezone.utc)
    second = runner.produce_scheduled_rows()
    assert second == 0
    assert len(_schedule_jobs(db)) == 1
