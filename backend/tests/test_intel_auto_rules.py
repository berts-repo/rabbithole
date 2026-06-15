"""Analysis / Intel pane (item 7, decision D4) — auto_analysis_rules.

Covers ``db/auto_rules.py`` CRUD + the trigger_kind CHECK + the
``rules_for_collection_add`` query, the ``routes/auto_rules.py`` surface, and
the end-to-end collection-add trigger: adding a genuinely new member to a
collection that has an enabled ``collection_add`` rule enqueues the rule's
analyzer (and re-adding an existing member does not).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import auto_rules as rules_db
from backend.db import llm as llm_db
from backend.db import page_versions as versions_db
from backend.db.core import CrawlDB


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "intel_auto_rules.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


def _insert_node(db: CrawlDB, url: str) -> int:
    host = url.split("//", 1)[1].split("/", 1)[0]
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


# --- db layer --------------------------------------------------------------


def test_create_and_get(db: CrawlDB) -> None:
    rid = rules_db.create(
        db,
        trigger_kind="collection_add",
        analysis_type="Summary",
        target_filter={"collection_id": 7},
    )
    row = rules_db.get(db, rid)
    assert row is not None
    assert row["trigger_kind"] == "collection_add"
    assert row["enabled"] == 1
    # target_filter is surfaced as a dict, not raw JSON text.
    assert row["target_filter"] == {"collection_id": 7}


def test_bad_trigger_kind_raises_value_error(db: CrawlDB) -> None:
    with pytest.raises(ValueError):
        rules_db.create(db, trigger_kind="bogus", analysis_type="Summary")


def test_list_filters_by_trigger_and_enabled(db: CrawlDB) -> None:
    # A fresh DB already carries the 5 seeded crawl rules (D4), so this asserts
    # on membership rather than exact sets.
    coll = rules_db.create(
        db, trigger_kind="collection_add", analysis_type="Summary",
        target_filter={"collection_id": 1}, enabled=False,
    )
    crawl_ids = {r["id"] for r in rules_db.list_rules(db, trigger_kind="crawl")}
    assert coll not in crawl_ids  # the collection rule is not a crawl rule
    all_ids = {r["id"] for r in rules_db.list_rules(db)}
    assert coll in all_ids and crawl_ids <= all_ids
    # The disabled collection rule is excluded from the enabled-only view.
    assert coll not in {r["id"] for r in rules_db.list_rules(db, enabled_only=True)}


def test_seed_crawl_rules_idempotent_and_default_summary_on(db: CrawlDB) -> None:
    # The seed runs at DB open; re-running it adds nothing and the default-on
    # set matches the legacy llm.auto_enqueue.* defaults (Summary only).
    before = rules_db.list_rules(db, trigger_kind="crawl")
    assert {r["analysis_type"] for r in before} == {
        "Summary", "Category", "Domain Label", "Entities (LLM)", "Risk Score",
    }
    enabled = {r["analysis_type"] for r in before if r["enabled"]}
    assert enabled == {"Summary"}
    rules_db.seed_crawl_rules(db)  # idempotent
    after = rules_db.list_rules(db, trigger_kind="crawl")
    assert len(after) == len(before)


def test_update_and_delete(db: CrawlDB) -> None:
    rid = rules_db.create(db, trigger_kind="crawl", analysis_type="Summary")
    assert rules_db.update(db, rid, enabled=False, model="qwen2.5:3b") is True
    row = rules_db.get(db, rid)
    assert row["enabled"] == 0
    assert row["model"] == "qwen2.5:3b"
    assert rules_db.update(db, rid) is False  # no fields → no-op
    assert rules_db.delete(db, rid) is True
    assert rules_db.get(db, rid) is None


def test_rules_for_collection_add_matches_only_target(db: CrawlDB) -> None:
    match = rules_db.create(
        db, trigger_kind="collection_add", analysis_type="Summary",
        target_filter={"collection_id": 5},
    )
    # Different collection, disabled, and wrong trigger kind must all be excluded.
    rules_db.create(
        db, trigger_kind="collection_add", analysis_type="Summary",
        target_filter={"collection_id": 6},
    )
    rules_db.create(
        db, trigger_kind="collection_add", analysis_type="Summary",
        target_filter={"collection_id": 5}, enabled=False,
    )
    rules_db.create(db, trigger_kind="crawl", analysis_type="Summary")
    matched = rules_db.rules_for_collection_add(db, 5)
    assert [r["id"] for r in matched] == [match]


# --- routes ----------------------------------------------------------------


def test_route_create_unknown_trigger_400(auth_client, active_db: CrawlDB) -> None:
    r = auth_client.post(
        "/api/auto-analysis-rules",
        json={"trigger_kind": "bogus", "analysis_type": "Summary"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "unknown_trigger"


def test_route_create_unknown_type_400(auth_client, active_db: CrawlDB) -> None:
    r = auth_client.post(
        "/api/auto-analysis-rules",
        json={"trigger_kind": "crawl", "analysis_type": "NotAType"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "unknown_type"


def test_route_crud_round_trip(auth_client, active_db: CrawlDB) -> None:
    new_id = auth_client.post(
        "/api/auto-analysis-rules",
        json={
            "trigger_kind": "collection_add",
            "analysis_type": "Summary",
            "target_filter": {"collection_id": 3},
        },
    ).json()["id"]

    listed = auth_client.get("/api/auto-analysis-rules").json()["rules"]
    assert any(r["id"] == new_id for r in listed)

    patched = auth_client.patch(
        f"/api/auto-analysis-rules/{new_id}", json={"enabled": False}
    )
    assert patched.status_code == 200
    assert patched.json()["enabled"] == 0

    deleted = auth_client.delete(f"/api/auto-analysis-rules/{new_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] == new_id
    assert auth_client.delete(f"/api/auto-analysis-rules/{new_id}").status_code == 404


# --- collection-add trigger (end-to-end through the route) -----------------


def test_collection_add_fires_matching_rule(auth_client, active_db: CrawlDB) -> None:
    cid = auth_client.post("/api/collections", json={"name": "c"}).json()["id"]
    nid = _insert_node(active_db, "http://a.onion/")
    rules_db.create(
        active_db,
        trigger_kind="collection_add",
        analysis_type="Summary",
        target_filter={"collection_id": cid},
    )

    r = auth_client.post(f"/api/collections/{cid}/items", json={"node_ids": [nid]})
    assert r.status_code == 200
    assert r.json()["added_ids"] == [nid]

    queue = llm_db.list_queue(active_db, resource_id=nid)
    assert len(queue) == 1
    assert queue[0]["analysis_type"] == "Summary"
    assert queue[0]["status"] == "pending"


def test_collection_add_no_rule_no_enqueue(auth_client, active_db: CrawlDB) -> None:
    cid = auth_client.post("/api/collections", json={"name": "c"}).json()["id"]
    nid = _insert_node(active_db, "http://a.onion/")
    auth_client.post(f"/api/collections/{cid}/items", json={"node_ids": [nid]})
    assert llm_db.list_queue(active_db, resource_id=nid) == []


def test_collection_add_only_fires_for_new_members(
    auth_client, active_db: CrawlDB
) -> None:
    cid = auth_client.post("/api/collections", json={"name": "c"}).json()["id"]
    nid = _insert_node(active_db, "http://a.onion/")
    rules_db.create(
        active_db,
        trigger_kind="collection_add",
        analysis_type="Summary",
        target_filter={"collection_id": cid},
    )
    auth_client.post(f"/api/collections/{cid}/items", json={"node_ids": [nid]})
    # Re-adding the same member is a no-op → no second analysis enqueued.
    r2 = auth_client.post(f"/api/collections/{cid}/items", json={"node_ids": [nid]})
    assert r2.json()["added_ids"] == []
    assert len(llm_db.list_queue(active_db, resource_id=nid)) == 1


def test_collection_add_disabled_rule_does_not_fire(
    auth_client, active_db: CrawlDB
) -> None:
    cid = auth_client.post("/api/collections", json={"name": "c"}).json()["id"]
    nid = _insert_node(active_db, "http://a.onion/")
    rules_db.create(
        active_db,
        trigger_kind="collection_add",
        analysis_type="Summary",
        target_filter={"collection_id": cid},
        enabled=False,
    )
    auth_client.post(f"/api/collections/{cid}/items", json={"node_ids": [nid]})
    assert llm_db.list_queue(active_db, resource_id=nid) == []
