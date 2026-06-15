"""Phase B8 — LLM routes (analyses CRUD + collection synthesis)."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import collections as collections_db
from backend.db import llm as llm_db
from backend.db import page_versions as versions_db
from backend.db import resources as resources_db
from backend.db.core import CrawlDB


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "b8_llm.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


def _host(url: str) -> str:
    return url.split("//", 1)[1].split("/", 1)[0]


def _insert_node(db: CrawlDB, *, url: str, stub: bool = False) -> int:
    """Return the resource id. ``stub=True`` leaves it uncrawled (``known``)."""
    host = _host(url)
    if stub:
        return resources_db.upsert_resource(db, url, host, state="known")
    rid, _vid = versions_db.record_fetch(
        db,
        url=url,
        host=host,
        status_code=200,
        title="t",
        body_text="body",
        body_text_clean="body",
        response_headers={},
        when="2026-05-12T00:00:00+00:00",
    )
    return rid


# --- analyses CRUD --------------------------------------------------------


def test_create_and_list_analysis(auth_client, active_db: CrawlDB):
    node_id = _insert_node(active_db, url="http://x.onion/")
    r = auth_client.post(
        "/api/analyses",
        json={"node_id": node_id, "analysis_type": "Summary"},
    )
    assert r.status_code == 200, r.text
    new_id = r.json()["id"]
    r2 = auth_client.get("/api/analyses")
    rows = r2.json()["analyses"]
    assert any(row["id"] == new_id and row["status"] == "pending" for row in rows)


def test_create_unknown_type_400(auth_client, active_db: CrawlDB):
    node_id = _insert_node(active_db, url="http://x.onion/")
    r = auth_client.post(
        "/api/analyses",
        json={"node_id": node_id, "analysis_type": "BogusType"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "unknown_type"


def test_create_collection_only_type_on_node_400(auth_client, active_db: CrawlDB):
    node_id = _insert_node(active_db, url="http://x.onion/")
    r = auth_client.post(
        "/api/analyses",
        json={"node_id": node_id, "analysis_type": "Cluster Summary"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "collection_only"


def test_qa_requires_question(auth_client, active_db: CrawlDB):
    node_id = _insert_node(active_db, url="http://x.onion/")
    r = auth_client.post(
        "/api/analyses",
        json={"node_id": node_id, "analysis_type": "Q&A"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "question_required"


def test_create_for_uncrawled_returns_pending(auth_client, active_db: CrawlDB):
    # The stub/waiting split is gone: an uncrawled (``known``) resource still
    # enqueues a plain ``pending`` job — the worker drops it (``no_content``)
    # if it's still uncrawled when claimed.
    node_id = _insert_node(active_db, url="http://x.onion/", stub=True)
    r = auth_client.post(
        "/api/analyses",
        json={"node_id": node_id, "analysis_type": "Summary"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "pending"


def test_patch_priority(auth_client, active_db: CrawlDB):
    node_id = _insert_node(active_db, url="http://x.onion/")
    aid = llm_db.enqueue(
        active_db, resource_id=node_id, analysis_type="Summary", model="qwen2.5:3b"
    )
    r = auth_client.patch(f"/api/analyses/{aid}", json={"priority": 7})
    assert r.status_code == 200
    row = llm_db.get(active_db, aid)
    assert row is not None and row["priority"] == 7


def test_delete_pending_then_running(auth_client, active_db: CrawlDB):
    node_id = _insert_node(active_db, url="http://x.onion/")
    aid = llm_db.enqueue(
        active_db, resource_id=node_id, analysis_type="Summary", model="qwen2.5:3b"
    )
    r = auth_client.delete(f"/api/analyses/{aid}")
    assert r.status_code == 200
    assert llm_db.get(active_db, aid) is None
    # Now insert + flip the linked job to running, ensure plain delete fails,
    # force succeeds. Status lives on the job, not the analyses row.
    aid2 = llm_db.enqueue(
        active_db, resource_id=node_id, analysis_type="Summary", model="qwen2.5:3b"
    )
    with active_db.transaction(immediate=True) as c:
        c.execute(
            "UPDATE jobs SET status='running' WHERE kind='analysis' "
            "AND json_extract(payload, '$.analysis_id')=?",
            (aid2,),
        )
    r2 = auth_client.delete(f"/api/analyses/{aid2}")
    assert r2.status_code == 404
    r3 = auth_client.delete(f"/api/analyses/{aid2}", params={"force": True})
    assert r3.status_code == 200
    assert llm_db.get(active_db, aid2) is None


def test_rerun_done_resets_to_pending(auth_client, active_db: CrawlDB):
    node_id = _insert_node(active_db, url="http://x.onion/")
    aid = llm_db.enqueue(
        active_db, resource_id=node_id, analysis_type="Summary", model="qwen2.5:3b"
    )
    job_id = llm_db.get(active_db, aid)["job_id"]
    llm_db.mark_done(active_db, job_id=job_id, analysis_id=aid, result_text="result text")
    r = auth_client.post(f"/api/analyses/{aid}/rerun")
    assert r.status_code == 200
    row = llm_db.get(active_db, aid)
    assert row is not None and row["status"] == "pending" and row["result"] is None


def test_rerun_pending_404(auth_client, active_db: CrawlDB):
    node_id = _insert_node(active_db, url="http://x.onion/")
    aid = llm_db.enqueue(
        active_db, resource_id=node_id, analysis_type="Summary", model="qwen2.5:3b"
    )
    r = auth_client.post(f"/api/analyses/{aid}/rerun")
    assert r.status_code == 404


# --- batch analyses -------------------------------------------------------


def test_batch_queues_crawled_and_uncrawled(auth_client, active_db: CrawlDB):
    a = _insert_node(active_db, url="http://a.onion/")
    b = _insert_node(active_db, url="http://b.onion/")
    uncrawled = _insert_node(active_db, url="http://s.onion/", stub=True)
    r = auth_client.post(
        "/api/analyses/batch",
        json={"node_ids": [a, b, uncrawled], "analysis_type": "Summary"},
    )
    assert r.status_code == 200, r.text
    # Every known resource queues ``pending`` — no more waiting split.
    assert r.json() == {"queued": 3, "skipped": 0, "unknown": 0}
    uncrawled_rows = llm_db.list_queue(active_db, resource_id=uncrawled)
    assert [row["status"] for row in uncrawled_rows] == ["pending"]


def test_batch_skip_existing(auth_client, active_db: CrawlDB):
    a = _insert_node(active_db, url="http://a.onion/")
    b = _insert_node(active_db, url="http://b.onion/")
    llm_db.enqueue(
        active_db, resource_id=a, analysis_type="Summary", model="qwen2.5:3b"
    )
    r = auth_client.post(
        "/api/analyses/batch",
        json={"node_ids": [a, b], "analysis_type": "Summary"},
    )
    assert r.status_code == 200
    # ``a`` already has a pending Summary job → skipped; ``b`` is queued.
    assert r.json() == {"queued": 1, "skipped": 1, "unknown": 0}


def test_batch_skip_existing_off_double_queues(auth_client, active_db: CrawlDB):
    a = _insert_node(active_db, url="http://a.onion/")
    llm_db.enqueue(
        active_db, resource_id=a, analysis_type="Summary", model="qwen2.5:3b"
    )
    r = auth_client.post(
        "/api/analyses/batch",
        json={
            "node_ids": [a],
            "analysis_type": "Summary",
            "skip_existing": False,
        },
    )
    assert r.json() == {"queued": 1, "skipped": 0, "unknown": 0}
    assert len(llm_db.list_queue(active_db, resource_id=a)) == 2


def test_batch_unknown_node_counted(auth_client, active_db: CrawlDB):
    a = _insert_node(active_db, url="http://a.onion/")
    r = auth_client.post(
        "/api/analyses/batch",
        json={"node_ids": [a, 99999], "analysis_type": "Summary"},
    )
    assert r.status_code == 200
    assert r.json() == {"queued": 1, "skipped": 0, "unknown": 1}


def test_batch_unknown_type_400(auth_client, active_db: CrawlDB):
    a = _insert_node(active_db, url="http://a.onion/")
    r = auth_client.post(
        "/api/analyses/batch",
        json={"node_ids": [a], "analysis_type": "BogusType"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "unknown_type"


def test_batch_collection_only_type_400(auth_client, active_db: CrawlDB):
    a = _insert_node(active_db, url="http://a.onion/")
    r = auth_client.post(
        "/api/analyses/batch",
        json={"node_ids": [a], "analysis_type": "Cluster Summary"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "collection_only"


def test_batch_qa_requires_question(auth_client, active_db: CrawlDB):
    a = _insert_node(active_db, url="http://a.onion/")
    r = auth_client.post(
        "/api/analyses/batch",
        json={"node_ids": [a], "analysis_type": "Q&A"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "question_required"


# --- collection synthesis -------------------------------------------------


def test_create_collection_analysis_lifecycle(auth_client, active_db: CrawlDB):
    cid = collections_db.create_collection(
        active_db, name="probe", description=None
    )
    r = auth_client.post(
        f"/api/collections/{cid}/analyses",
        json={"analysis_type": "Cluster Summary"},
    )
    assert r.status_code == 200
    aid = r.json()["id"]
    r2 = auth_client.get(f"/api/collections/{cid}/analyses")
    assert r2.status_code == 200
    rows = r2.json()["analyses"]
    assert len(rows) == 1
    assert rows[0]["id"] == aid
    assert rows[0]["analysis_type"] == "Cluster Summary"
    assert rows[0]["status"] == "pending"


def test_create_collection_analysis_rejects_node_only_type(
    auth_client, active_db: CrawlDB
):
    cid = collections_db.create_collection(
        active_db, name="x", description=None
    )
    r = auth_client.post(
        f"/api/collections/{cid}/analyses",
        json={"analysis_type": "Summary"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "node_only"


def test_collection_analyses_unknown_collection_404(auth_client, active_db: CrawlDB):
    r = auth_client.get("/api/collections/9999/analyses")
    assert r.status_code == 404
