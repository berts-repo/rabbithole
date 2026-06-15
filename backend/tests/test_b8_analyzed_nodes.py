"""Phase B8 — Analyzed-nodes list (bottom-pane "Analyzed" tab).

``llm_db.list_analyzed_nodes`` + ``GET /api/analyzed-nodes``: one row per node
with ≥1 *successful* completed analysis, dropped-result jobs excluded.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import llm as llm_db
from backend.db import page_versions as versions_db
from backend.db.core import CrawlDB


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "b8_analyzed.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


def _insert_node(db: CrawlDB, *, url: str, title: str = "t") -> int:
    host = url.split("//", 1)[1].split("/", 1)[0]
    rid, _vid = versions_db.record_fetch(
        db,
        url=url,
        host=host,
        status_code=200,
        title=title,
        body_text="body",
        body_text_clean="body",
        response_headers={},
        when="2026-05-12T00:00:00+00:00",
    )
    return rid


def _job_id(db: CrawlDB, analysis_id: int) -> int:
    """job_id for an analysis, via the public queue listing."""
    for row in llm_db.list_queue(db):
        if int(row["id"]) == analysis_id:
            return int(row["job_id"])
    raise AssertionError(f"no job row for analysis {analysis_id}")


def _complete(db: CrawlDB, *, node_id: int, analysis_type: str, result: str) -> None:
    aid = llm_db.enqueue(
        db, resource_id=node_id, analysis_type=analysis_type, model="qwen2.5:3b"
    )
    llm_db.mark_done(
        db, job_id=_job_id(db, aid), analysis_id=aid, result_text=result
    )


# --- db layer --------------------------------------------------------------


def test_lists_node_with_successful_analyses(active_db: CrawlDB):
    a = _insert_node(active_db, url="http://a.onion/", title="Alpha")
    _complete(active_db, node_id=a, analysis_type="Summary", result="a summary")
    _complete(active_db, node_id=a, analysis_type="Category", result="market")

    rows = llm_db.list_analyzed_nodes(active_db)
    assert len(rows) == 1
    row = rows[0]
    assert row["node_id"] == a
    assert row["url"] == "http://a.onion/"
    assert row["title"] == "Alpha"
    # GROUP_CONCAT(DISTINCT …) — both types, deduped, comma-joined.
    assert set(str(row["analysis_types"]).split(",")) == {"Summary", "Category"}
    assert row["last_analyzed"]


def test_excludes_node_whose_analyses_all_dropped(active_db: CrawlDB):
    a = _insert_node(active_db, url="http://a.onion/")
    _complete(active_db, node_id=a, analysis_type="Summary", result="real")
    b = _insert_node(active_db, url="http://b.onion/")
    _complete(
        active_db, node_id=b, analysis_type="Summary", result="<dropped:no_content>"
    )

    rows = llm_db.list_analyzed_nodes(active_db)
    assert [r["node_id"] for r in rows] == [a]


def test_pending_only_node_absent(active_db: CrawlDB):
    a = _insert_node(active_db, url="http://a.onion/")
    llm_db.enqueue(
        active_db, resource_id=a, analysis_type="Summary", model="qwen2.5:3b"
    )  # left pending — never completed
    assert llm_db.list_analyzed_nodes(active_db) == []


# --- route -----------------------------------------------------------------


def test_route_returns_split_types(auth_client, active_db: CrawlDB):
    a = _insert_node(active_db, url="http://a.onion/", title="Alpha")
    _complete(active_db, node_id=a, analysis_type="Summary", result="s")
    _complete(active_db, node_id=a, analysis_type="Category", result="c")

    r = auth_client.get("/api/analyzed-nodes")
    assert r.status_code == 200, r.text
    nodes = r.json()["nodes"]
    assert len(nodes) == 1
    node = nodes[0]
    assert node["node_id"] == a
    assert isinstance(node["analysis_types"], list)
    assert set(node["analysis_types"]) == {"Summary", "Category"}


def test_route_empty_when_nothing_done(auth_client, active_db: CrawlDB):
    _insert_node(active_db, url="http://a.onion/")
    r = auth_client.get("/api/analyzed-nodes")
    assert r.status_code == 200, r.text
    assert r.json()["nodes"] == []
