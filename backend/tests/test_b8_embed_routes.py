"""Phase B8 — embed routes (status, lifecycle, progress, models)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.db import embed as embed_db
from backend.db import page_versions as versions_db
from backend.db.core import CrawlDB
from backend.services.event_bus import EventBus
from backend.services.embed_worker import EmbedWorker
from backend.services.graph_cache import GraphCache


_EMBED_DIM = 384


class _FakeKillSwitch:
    import asyncio as _aio

    def __init__(self) -> None:
        self.engaged = self._aio.Event()


class _FakeModel:
    def embed(self, texts):
        for _ in texts:
            yield [0.0] * _EMBED_DIM


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "b8_embed.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    # Replace the real worker so we don't pull onnxruntime mid-suite.
    app.state.embed_worker = EmbedWorker(
        project_state=app.state.project_state,
        kill_switch=_FakeKillSwitch(),  # type: ignore[arg-type]
        event_bus=EventBus(),
        model_loader=lambda _name: _FakeModel(),
    )
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


def _insert_node(db: CrawlDB, *, seed: str) -> int:
    """Crawl a URL once → its resource id. The current version's clean text
    makes the page eligible for embedding (one page per crawled resource)."""
    host = (seed * 56)[:56] + ".onion"
    url = "http://" + host + "/"
    resource_id, _vid = versions_db.record_fetch(
        db,
        url=url,
        host=host,
        status_code=200,
        title="t",
        body_text="body",
        body_text_clean="body",
        response_headers={},
        when="2026-05-15T00:00:00+00:00",
    )
    return resource_id


# --- status ---------------------------------------------------------------


def test_embed_status_shape(auth_client, active_db):
    r = auth_client.get("/api/embed/status")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "status",
        "paused",
        "circuit_open",
        "model",
        "processed",
        "embedded",
        "eligible",
        "queue_size",
    ):
        assert key in body


def test_embed_progress_shape(auth_client, active_db):
    _insert_node(active_db, seed="a")
    _insert_node(active_db, seed="b")
    r = auth_client.get("/api/embed/progress")
    body = r.json()
    assert body["eligible"] == 2
    assert body["embedded"] == 0
    assert body["queue_size"] == 2
    assert body["percent"] == 0.0


def test_embed_pause_resume(auth_client, active_db):
    r = auth_client.post("/api/embed/pause")
    assert r.json()["paused"] is True
    r = auth_client.post("/api/embed/resume")
    assert r.json()["paused"] is False


# --- model registry -------------------------------------------------------


def test_embed_models_filters_to_dim_384(auth_client):
    r = auth_client.get("/api/embed/models")
    assert r.status_code == 200
    body = r.json()
    assert "models" in body
    for entry in body["models"]:
        assert entry["dim"] == 384
