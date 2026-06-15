"""Phase B8 — embed worker poison-pill, model swap, circuit breaker."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from backend.db import embed as embed_db
from backend.db import page_versions as versions_db
from backend.db import pages as pages_db
from backend.db.core import CrawlDB
from backend.services.embed_worker import EmbedNotReady, EmbedWorker
from backend.services.event_bus import EventBus
from backend.services.graph_cache import GraphCache


_EMBED_DIM = 384
MODEL = "BAAI/bge-small-en-v1.5"


class _FakeKillSwitch:
    def __init__(self) -> None:
        self.engaged = asyncio.Event()


class _FakeProjectState:
    def __init__(self, db: CrawlDB | None) -> None:
        self.active_db = db
        self.graph_cache = GraphCache()


class _FakeModel:
    """Returns a deterministic vector (the same for every input)."""

    def __init__(self, value: float = 0.5) -> None:
        self._value = value

    def embed(self, texts):
        for _ in texts:
            yield [self._value] * _EMBED_DIM


class _ExplodingModel:
    def __init__(self, *, fail_count: int) -> None:
        self.fail_count = fail_count
        self._calls = 0

    def embed(self, texts):
        self._calls += 1
        if self._calls <= self.fail_count:
            raise RuntimeError("synthetic encode failure")
        for _ in texts:
            yield [0.1] * _EMBED_DIM


@pytest.fixture
def db(tmp_path: Path):
    instance = CrawlDB(tmp_path / "embed.db")
    try:
        yield instance
    finally:
        instance.close()


def _crawl_page(db: CrawlDB, *, seed: str, body: str = "body text") -> int:
    """Crawl one URL with non-empty clean text; returns its resource id."""
    host = (seed * 56)[:56] + ".onion"
    url = f"http://{host}/"
    rid, _ = versions_db.record_fetch(
        db,
        url=url,
        host=host,
        status_code=200,
        title="t",
        body_text=body,
        body_text_clean=body,
        response_headers={},
        when="2026-05-15T00:00:00+00:00",
    )
    return rid


def _page_id(db: CrawlDB, resource_id: int) -> int:
    """The page id for a resource (1:1; idempotent)."""
    return pages_db.ensure_page(db, resource_id)


def _pending_page_ids(db: CrawlDB, *, model: str = MODEL) -> set[int]:
    return {p["page_id"] for p in embed_db.pending(db, model=model, limit=1000)}


def _make_worker(db: CrawlDB, *, model: Any) -> tuple[EmbedWorker, EventBus]:
    bus = EventBus()
    worker = EmbedWorker(
        project_state=_FakeProjectState(db),  # type: ignore[arg-type]
        kill_switch=_FakeKillSwitch(),  # type: ignore[arg-type]
        event_bus=bus,
        model_loader=lambda _name: model,
    )
    return worker, bus


# --- happy path -----------------------------------------------------------


def test_first_tick_loads_model_and_writes_embedding(db: CrawlDB):
    _crawl_page(db, seed="a")
    model = _FakeModel(value=0.42)
    worker, _bus = _make_worker(db, model=model)
    written = asyncio.run(worker._tick())
    assert written == 1
    assert embed_db.count_embeddings(db) == 1
    snap = worker.snapshot()
    assert snap["embedded"] == 1
    assert snap["model"] == MODEL


def test_pending_query_skips_already_embedded(db: CrawlDB):
    rid = _crawl_page(db, seed="a")
    page_id = _page_id(db, rid)
    embed_db.upsert_embedding(
        db,
        page_id=page_id,
        vector=embed_db.serialize_vector([0.0] * _EMBED_DIM),
        model=MODEL,
    )
    assert page_id not in _pending_page_ids(db)


def test_pending_query_includes_node_with_different_model(db: CrawlDB):
    rid = _crawl_page(db, seed="a")
    page_id = _page_id(db, rid)
    embed_db.upsert_embedding(
        db,
        page_id=page_id,
        vector=embed_db.serialize_vector([0.0] * _EMBED_DIM),
        model="some-other-model",
    )
    assert page_id in _pending_page_ids(db)


# --- poison pill ----------------------------------------------------------


def test_three_failures_set_embed_excluded(db: CrawlDB):
    rid = _crawl_page(db, seed="a")
    page_id = _page_id(db, rid)
    bad = _ExplodingModel(fail_count=10)  # never succeeds
    worker, _bus = _make_worker(db, model=bad)
    for _ in range(3):
        asyncio.run(worker._tick())
    # The poison-pill flag (on pages) drops the page out of the pending set.
    assert page_id not in _pending_page_ids(db)


# --- model swap -----------------------------------------------------------


def test_model_swap_wipes_existing_embeddings(db: CrawlDB):
    rid = _crawl_page(db, seed="a")
    page_id = _page_id(db, rid)
    embed_db.upsert_embedding(
        db,
        page_id=page_id,
        vector=embed_db.serialize_vector([0.1] * _EMBED_DIM),
        model="OLD-MODEL",
    )
    assert embed_db.count_embeddings(db) == 1
    # Force the worker to load a new model than what's in the DB.
    worker, _bus = _make_worker(db, model=_FakeModel(value=0.7))
    worker._loaded_model_name = "OLD-MODEL"  # simulate prior tick's state
    worker._model = _FakeModel(value=0.0)
    asyncio.run(worker._ensure_model(MODEL))
    assert worker._loaded_model_name == MODEL
    # The wipe ran: stale rows are gone (next tick will re-embed).
    assert embed_db.count_embeddings(db) == 0


# --- encode helper --------------------------------------------------------


def test_encode_raises_when_no_model_loaded(db: CrawlDB):
    worker, _bus = _make_worker(db, model=_FakeModel())
    with pytest.raises(EmbedNotReady):
        worker.encode("query")


def test_encode_returns_serialized_bytes_after_load(db: CrawlDB):
    worker, _bus = _make_worker(db, model=_FakeModel(value=0.3))
    asyncio.run(worker._ensure_model(MODEL))
    out = worker.encode("query")
    assert isinstance(out, bytes)
    # 384 floats × 4 bytes each.
    assert len(out) == _EMBED_DIM * 4


# --- snapshot / count helpers --------------------------------------------


def test_snapshot_reports_progress(db: CrawlDB):
    _crawl_page(db, seed="a")
    _crawl_page(db, seed="b")
    worker, _bus = _make_worker(db, model=_FakeModel())
    asyncio.run(worker._tick())
    snap = worker.snapshot()
    assert snap["eligible"] == 2
    assert snap["embedded"] == 2
    assert snap["queue_size"] == 0
