"""Phase B8 — keyword (FTS5) + semantic (sqlite-vec) search routes."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.db import embed as embed_db
from backend.db import findings as findings_db
from backend.db import page_versions as versions_db
from backend.db.core import CrawlDB
from backend.services.embed_worker import EmbedNotReady, EmbedWorker
from backend.services.event_bus import EventBus
from backend.services.graph_cache import GraphCache


_EMBED_DIM = 384


class _FakeKillSwitch:
    import asyncio as _aio

    def __init__(self) -> None:
        self.engaged = self._aio.Event()


class _FakeModel:
    def __init__(self, value: float = 0.5) -> None:
        self._value = value

    def embed(self, texts):
        for _ in texts:
            yield [self._value] * _EMBED_DIM


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "b8_search.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


def _insert_node(
    db: CrawlDB, *, seed: str, body: str, title: str | None = None
) -> int:
    """Crawl a URL once → its resource id (search reports ``node_id`` = resource).

    ``body`` becomes the current version's clean text, which the manual
    ``pages_fts`` maintenance in the crawl write indexes for keyword search.
    """
    host = (seed * 56)[:56] + ".onion"
    url = "http://" + host + "/"
    rid, _vid = versions_db.record_fetch(
        db,
        url=url,
        host=host,
        status_code=200,
        title=title,
        body_text=body,
        body_text_clean=body,
        response_headers={},
        when="2026-05-15T00:00:00+00:00",
    )
    return rid


def _page_id(db: CrawlDB, resource_id: int) -> int:
    with db.read() as c:
        return int(
            c.execute(
                "SELECT id FROM pages WHERE resource_id=?", (resource_id,)
            ).fetchone()["id"]
        )


# --- keyword --------------------------------------------------------------


def test_keyword_search_returns_snippet(auth_client, active_db):
    _insert_node(
        active_db,
        seed="a",
        body="A page about marketplaces and bitcoin trades.",
        title="Page A",
    )
    r = auth_client.get("/api/search/keyword", params={"q": "marketplaces"})
    assert r.status_code == 200
    rows = r.json()["results"]
    assert len(rows) == 1
    assert "<mark>marketplaces</mark>" in rows[0]["snippet"]


def test_keyword_search_sanitizes_fts_operators(auth_client, active_db):
    _insert_node(
        active_db,
        seed="a",
        body="text with foo bar baz quoted content",
        title=None,
    )
    # An unsanitized FTS query like `foo*bar"baz` would explode FTS5;
    # we wrap it as a single phrase. Still returns valid results (or empty)
    # without raising a 400 from the DB.
    r = auth_client.get(
        "/api/search/keyword", params={"q": 'foo*bar"baz'}
    )
    assert r.status_code == 200
    assert "results" in r.json()


def test_keyword_search_empty_query_returns_empty(auth_client, active_db):
    r = auth_client.get("/api/search/keyword", params={"q": ""})
    assert r.status_code == 200
    assert r.json()["results"] == []


def test_keyword_limit_honored_and_capped(auth_client, active_db):
    """Default cap is the route's _KEYWORD_LIMIT_MAX (200); honors smaller limits."""
    for i in range(20):
        _insert_node(
            active_db, seed=chr(ord("a") + (i % 24)) + str(i),
            body=f"unique content {i}",
        )
    r = auth_client.get(
        "/api/search/keyword", params={"q": "unique", "limit": 5}
    )
    assert r.status_code == 200
    assert len(r.json()["results"]) == 5


# --- keyword: page + entity + note (item 9) -------------------------------


def test_keyword_page_results_tagged_type_page(auth_client, active_db):
    _insert_node(active_db, seed="a", body="ransomware leak site", title="A")
    r = auth_client.get("/api/search/keyword", params={"q": "ransomware"})
    rows = r.json()["results"]
    assert rows and rows[0]["type"] == "page"


def test_keyword_includes_entity_matches(auth_client, active_db):
    rid = _insert_node(active_db, seed="a", body="plain page text", title="A")
    findings_db.insert_entities(
        active_db,
        rid,
        [("btc", "bc1qexampleaddress0001")],
        now="2026-05-15T00:00:00+00:00",
    )
    r = auth_client.get("/api/search/keyword", params={"q": "exampleaddress"})
    assert r.status_code == 200
    entity_rows = [x for x in r.json()["results"] if x["type"] == "entity"]
    assert len(entity_rows) == 1
    row = entity_rows[0]
    assert row["node_id"] == rid
    assert row["entity_type"] == "btc"
    assert row["value"] == "bc1qexampleaddress0001"


def test_keyword_includes_note_matches(auth_client, active_db):
    rid = _insert_node(active_db, seed="a", body="plain page text", title="A")
    findings_db.create_note(
        active_db, rid, "follow up on the courier handoff", now="2026-05-15T00:00:00+00:00"
    )
    r = auth_client.get("/api/search/keyword", params={"q": "courier"})
    assert r.status_code == 200
    note_rows = [x for x in r.json()["results"] if x["type"] == "note"]
    assert len(note_rows) == 1
    assert note_rows[0]["node_id"] == rid
    assert "courier" in note_rows[0]["snippet"]


def test_keyword_note_snippet_truncated(auth_client, active_db):
    rid = _insert_node(active_db, seed="a", body="plain page text", title="A")
    long_body = "needle " + ("x" * 400)
    findings_db.create_note(active_db, rid, long_body, now="2026-05-15T00:00:00+00:00")
    r = auth_client.get("/api/search/keyword", params={"q": "needle"})
    note_rows = [x for x in r.json()["results"] if x["type"] == "note"]
    assert len(note_rows) == 1
    snippet = note_rows[0]["snippet"]
    assert snippet.endswith("…")
    assert len(snippet) <= findings_db.NOTE_SNIPPET_CHARS + 1


def test_keyword_like_wildcards_matched_literally(auth_client, active_db):
    # A query containing % must not act as a LIKE wildcard.
    rid = _insert_node(active_db, seed="a", body="plain", title="A")
    findings_db.create_note(active_db, rid, "literal 100% match here", now="2026-05-15T00:00:00+00:00")
    hit = auth_client.get("/api/search/keyword", params={"q": "100%"})
    assert any(x["type"] == "note" for x in hit.json()["results"])
    # A different literal that the wildcard interpretation would have matched
    # must NOT come back for an unrelated note.
    miss = auth_client.get("/api/search/keyword", params={"q": "zz%zz"})
    assert [x for x in miss.json()["results"] if x["type"] == "note"] == []


# --- semantic -------------------------------------------------------------


def test_semantic_503_when_no_worker(auth_client, active_db):
    # Don't attach an embed worker to app.state.
    if hasattr(auth_client.app.state, "embed_worker"):
        # Use the worker but force it into "not loaded" state.
        worker = auth_client.app.state.embed_worker
        worker._model = None
        worker._loaded_model_name = None
    r = auth_client.get("/api/search/semantic", params={"q": "test"})
    assert r.status_code == 503
    assert r.json()["error"] == "embed_unavailable"


def test_semantic_returns_results_when_worker_loaded(
    auth_client, active_db
):
    # Replace worker with a deterministic stub.
    fake_worker = EmbedWorker(
        project_state=auth_client.app.state.project_state,
        kill_switch=_FakeKillSwitch(),  # type: ignore[arg-type]
        event_bus=EventBus(),
        model_loader=lambda _name: _FakeModel(value=0.5),
    )
    auth_client.app.state.embed_worker = fake_worker
    # Force the model to load via _ensure_model so .encode works.
    import asyncio

    asyncio.run(fake_worker._ensure_model("BAAI/bge-small-en-v1.5"))
    # Insert a node + an embedding under the active model.
    node_id = _insert_node(
        active_db, seed="a", body="content", title="A"
    )
    embed_db.upsert_embedding(
        active_db,
        page_id=_page_id(active_db, node_id),
        vector=embed_db.serialize_vector([0.5] * _EMBED_DIM),
        model="BAAI/bge-small-en-v1.5",
    )
    r = auth_client.get("/api/search/semantic", params={"q": "anything"})
    assert r.status_code == 200, r.text
    rows = r.json()["results"]
    assert len(rows) == 1
    assert rows[0]["node_id"] == node_id


def test_semantic_limit_caps_at_50(auth_client, active_db):
    fake_worker = EmbedWorker(
        project_state=auth_client.app.state.project_state,
        kill_switch=_FakeKillSwitch(),  # type: ignore[arg-type]
        event_bus=EventBus(),
        model_loader=lambda _name: _FakeModel(value=0.5),
    )
    auth_client.app.state.embed_worker = fake_worker
    import asyncio

    asyncio.run(fake_worker._ensure_model("BAAI/bge-small-en-v1.5"))
    for i in range(60):
        node_id = _insert_node(
            active_db, seed=chr(ord("a") + (i % 24)) + str(i),
            body=f"body {i}",
        )
        embed_db.upsert_embedding(
            active_db,
            page_id=_page_id(active_db, node_id),
            vector=embed_db.serialize_vector([0.5] * _EMBED_DIM),
            model="BAAI/bge-small-en-v1.5",
        )
    r = auth_client.get(
        "/api/search/semantic", params={"q": "x", "limit": 100}
    )
    assert r.status_code == 200
    assert len(r.json()["results"]) <= 50
