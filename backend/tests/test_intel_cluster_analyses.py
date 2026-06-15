"""Analysis / Intel pane (item 7, decision D1) — cluster_analyses.

Covers the cluster additions in ``db/llm.py`` (fingerprint helper, enqueue /
get / list / claim / mark-done / cancel) and the cluster routes in
``routes/llm.py``. Clusters are keyed by a membership *fingerprint*, not a
numeric id, so a re-clustered group with the same membership re-attaches its
analyses automatically.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import llm as llm_db
from backend.db.core import CrawlDB


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "intel_clusters.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


# --- fingerprint -----------------------------------------------------------


def test_fingerprint_order_independent_and_deduped() -> None:
    a = llm_db.compute_fingerprint([3, 1, 2])
    b = llm_db.compute_fingerprint([2, 3, 1, 1])  # reordered + duplicate
    assert a == b
    assert len(a) == 16
    # Different membership → different key.
    assert llm_db.compute_fingerprint([1, 2]) != a


# --- db layer --------------------------------------------------------------


def test_enqueue_get_and_status(db: CrawlDB) -> None:
    fp = llm_db.compute_fingerprint([1, 2, 3])
    aid = llm_db.enqueue_cluster(
        db, fingerprint=fp, resource_ids=[1, 2, 3],
        analysis_type="Cluster Q&A", model="m",
        label="My cluster", question="what is this?",
    )
    row = llm_db.get_cluster_analysis(db, aid)
    assert row is not None
    assert row["fingerprint"] == fp
    assert row["label"] == "My cluster"
    assert row["question"] == "what is this?"
    assert row["status"] == "pending"
    assert row["job_id"] is not None


def test_enqueue_stores_membership_snapshot(db: CrawlDB) -> None:
    # The fingerprint is one-way; the worker reads the membership back off the
    # claimed job to fetch page bodies. Order/dupes are normalised on store.
    fp = llm_db.compute_fingerprint([5, 1, 5, 2])
    llm_db.enqueue_cluster(
        db, fingerprint=fp, resource_ids=[5, 1, 5, 2],
        analysis_type="Cluster Summary", model="m",
    )
    claimed = llm_db.claim_next_cluster(db, model="m")
    assert claimed is not None
    assert claimed["resource_ids"] == [1, 2, 5]


def test_list_by_fingerprint_newest_first(db: CrawlDB) -> None:
    fp = llm_db.compute_fingerprint([1, 2])
    first = llm_db.enqueue_cluster(
        db, fingerprint=fp, resource_ids=[1, 2], analysis_type="Cluster Summary", model="m"
    )
    second = llm_db.enqueue_cluster(
        db, fingerprint=fp, resource_ids=[1, 2], analysis_type="Cluster Summary", model="m"
    )
    other = llm_db.enqueue_cluster(
        db, fingerprint=llm_db.compute_fingerprint([9]), resource_ids=[9],
        analysis_type="Cluster Summary", model="m",
    )
    ids = [r["id"] for r in llm_db.list_cluster_analyses(db, fp)]
    assert ids == [second, first]
    assert other not in ids


def test_claim_and_mark_done(db: CrawlDB) -> None:
    fp = llm_db.compute_fingerprint([1, 2])
    aid = llm_db.enqueue_cluster(
        db, fingerprint=fp, resource_ids=[1, 2], analysis_type="Cluster Summary", model="m"
    )
    claimed = llm_db.claim_next_cluster(db, model="m")
    assert claimed is not None
    assert claimed["analysis_id"] == aid
    assert llm_db.get_cluster_analysis(db, aid)["status"] == "running"

    assert llm_db.mark_cluster_done(
        db, job_id=claimed["job_id"], analysis_id=aid, result_text="answer"
    ) is True
    done = llm_db.get_cluster_analysis(db, aid)
    assert done["status"] == "done"
    assert done["result"] == "answer"
    # Nothing left to claim.
    assert llm_db.claim_next_cluster(db, model="m") is None


def test_cancel_non_running_deletes_running_refused(db: CrawlDB) -> None:
    fp = llm_db.compute_fingerprint([1])
    aid = llm_db.enqueue_cluster(
        db, fingerprint=fp, resource_ids=[1], analysis_type="Cluster Summary", model="m"
    )
    assert llm_db.cancel_cluster(db, aid) is True
    assert llm_db.get_cluster_analysis(db, aid) is None

    aid2 = llm_db.enqueue_cluster(
        db, fingerprint=fp, resource_ids=[1], analysis_type="Cluster Summary", model="m"
    )
    llm_db.claim_next_cluster(db, model="m")  # → running
    assert llm_db.cancel_cluster(db, aid2) is False
    assert llm_db.get_cluster_analysis(db, aid2) is not None


# --- routes ----------------------------------------------------------------


def test_route_create_derives_fingerprint(auth_client, active_db: CrawlDB) -> None:
    r = auth_client.post(
        "/api/clusters/analyses",
        json={"resource_ids": [3, 1, 2], "analysis_type": "Cluster Summary"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending"
    # Server derives the same fingerprint the helper would.
    assert body["fingerprint"] == llm_db.compute_fingerprint([1, 2, 3])


def test_route_create_unknown_type_400(auth_client, active_db: CrawlDB) -> None:
    r = auth_client.post(
        "/api/clusters/analyses",
        json={"resource_ids": [1], "analysis_type": "Nope"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "unknown_type"


def test_route_create_rejects_single_page_type(auth_client, active_db: CrawlDB) -> None:
    # A single-page type on a cluster would enqueue a job the worker can only
    # drop, so the route refuses it up front.
    r = auth_client.post(
        "/api/clusters/analyses",
        json={"resource_ids": [1, 2], "analysis_type": "Summary"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "not_cluster_type"


def test_route_list_and_get(auth_client, active_db: CrawlDB) -> None:
    created = auth_client.post(
        "/api/clusters/analyses",
        json={"resource_ids": [1, 2], "analysis_type": "Cluster Summary", "label": "L"},
    ).json()
    fp, aid = created["fingerprint"], created["id"]

    listed = auth_client.get(f"/api/clusters/{fp}/analyses").json()
    assert [a["id"] for a in listed["analyses"]] == [aid]

    got = auth_client.get(f"/api/cluster-analyses/{aid}")
    assert got.status_code == 200
    assert got.json()["label"] == "L"


def test_route_get_unknown_404(auth_client, active_db: CrawlDB) -> None:
    r = auth_client.get("/api/cluster-analyses/9999")
    assert r.status_code == 404
    assert r.json()["error"] == "unknown_analysis"


def test_route_delete_non_running(auth_client, active_db: CrawlDB) -> None:
    aid = auth_client.post(
        "/api/clusters/analyses",
        json={"resource_ids": [1], "analysis_type": "Cluster Summary"},
    ).json()["id"]
    r = auth_client.delete(f"/api/cluster-analyses/{aid}")
    assert r.status_code == 200
    assert r.json()["deleted"] == aid


def test_route_delete_running_409(auth_client, active_db: CrawlDB) -> None:
    aid = auth_client.post(
        "/api/clusters/analyses",
        json={"resource_ids": [1], "analysis_type": "Cluster Summary"},
    ).json()["id"]
    llm_db.claim_next_cluster(active_db, model="m")  # → running
    r = auth_client.delete(f"/api/cluster-analyses/{aid}")
    assert r.status_code == 409
    assert r.json()["error"] == "not_deletable"
