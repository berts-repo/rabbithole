"""Analysis / Intel pane (item 7) — worker load/capacity surface.

Covers the additions to ``LlmWorker.snapshot`` (the ``capacity`` /
``in_flight`` / ``queue_depth`` load block the Intel worker controls render) and
``_effective_batch_limit`` (the single concurrency number, read from the
``llm.batch_size`` setting with a safe fallback so a bad value can never stall
the worker).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.db import llm as llm_db
from backend.db import page_versions as versions_db
from backend.db.core import CrawlDB
from backend.db.settings import put_setting
from backend.services.event_bus import EventBus
from backend.services.graph_cache import GraphCache
from backend.services.llm_worker import LlmWorker, _BATCH_LIMIT


class _FakeKillSwitch:
    def register_task(self, task: asyncio.Task) -> None:  # pragma: no cover
        pass


class _FakeProjectState:
    def __init__(self, db: CrawlDB | None) -> None:
        self.active_db = db
        self.graph_cache = GraphCache()


def _worker(db: CrawlDB | None) -> LlmWorker:
    return LlmWorker(
        project_state=_FakeProjectState(db),
        kill_switch=_FakeKillSwitch(),
        event_bus=EventBus(),
    )


def _corrupt_setting(db: CrawlDB, key: str, value: str) -> None:
    """Write a value straight to the settings table, bypassing validation.

    ``put_setting`` would reject a non-int / out-of-range ``llm.batch_size``, so
    to exercise the worker's *defensive* fallback (which guards against a
    legacy or hand-corrupted DB value) we have to plant the bad value directly.
    """
    with db.transaction(immediate=True) as c:
        c.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
            (key, value),
        )


def _insert_node(db: CrawlDB, url: str) -> int:
    host = url.split("//", 1)[1].split("/", 1)[0]
    rid, _vid = versions_db.record_fetch(
        db, url=url, host=host, status_code=200, title="t",
        body_text="b", body_text_clean="b", response_headers={},
        when="2026-05-12T00:00:00+00:00",
    )
    return rid


# --- _effective_batch_limit ------------------------------------------------


def test_batch_limit_defaults_when_unset(db: CrawlDB) -> None:
    assert _worker(db)._effective_batch_limit(db) == _BATCH_LIMIT


def test_batch_limit_reads_setting(db: CrawlDB) -> None:
    put_setting(db, "llm.batch_size", "3")
    assert _worker(db)._effective_batch_limit(db) == 3


def test_batch_limit_falls_back_on_garbage(db: CrawlDB) -> None:
    _corrupt_setting(db, "llm.batch_size", "not-a-number")
    assert _worker(db)._effective_batch_limit(db) == _BATCH_LIMIT


def test_batch_limit_falls_back_on_non_positive(db: CrawlDB) -> None:
    _corrupt_setting(db, "llm.batch_size", "0")
    assert _worker(db)._effective_batch_limit(db) == _BATCH_LIMIT


def test_batch_size_setting_rejects_bad_values(db: CrawlDB) -> None:
    """The registered validator refuses non-int / out-of-range through put_setting."""
    for bad in ("not-a-number", "0", "9999"):
        with pytest.raises(ValueError):
            put_setting(db, "llm.batch_size", bad)


def test_batch_limit_no_db_uses_dataclass_default() -> None:
    assert _worker(None)._effective_batch_limit(None) == _BATCH_LIMIT


# --- snapshot load block ---------------------------------------------------


def test_snapshot_reports_capacity_and_load(db: CrawlDB) -> None:
    put_setting(db, "llm.batch_size", "4")
    a = _insert_node(db, "http://a.onion/")
    b = _insert_node(db, "http://b.onion/")
    llm_db.enqueue(db, resource_id=a, analysis_type="Summary", model="m")
    llm_db.enqueue(db, resource_id=b, analysis_type="Summary", model="m")
    # Claim one → it flips to running; the other stays pending.
    llm_db.claim_next_batch(db, model="m", limit=1)

    snap = _worker(db).snapshot()
    assert snap["capacity"] == 4
    assert snap["in_flight"] == 1
    assert snap["queue_depth"] == 1


def test_snapshot_load_block_present_with_empty_queue(db: CrawlDB) -> None:
    snap = _worker(db).snapshot()
    assert snap["capacity"] == _BATCH_LIMIT
    assert snap["in_flight"] == 0
    assert snap["queue_depth"] == 0
