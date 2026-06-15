"""Analysis / Intel pane (item 7, decision D3) — prompt_templates.

Covers the ``db/prompt_templates.py`` CRUD layer and the ``routes/prompt_templates.py``
surface. Built-in presets are seeded at DB init (``builtin=1``): they can be
hidden/un-hidden and cloned, but never edited or deleted.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import prompt_templates as prompts_db
from backend.db.core import PRESET_PROMPTS, CrawlDB


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "intel_prompts.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


# --- db layer --------------------------------------------------------------


def test_presets_seeded_as_builtins(db: CrawlDB) -> None:
    rows = prompts_db.list_templates(db)
    assert len(rows) == len(PRESET_PROMPTS)
    assert all(r["builtin"] == 1 for r in rows)
    assert all(r["hidden"] == 0 for r in rows)
    # builtins-first, then name asc — names match the seed set.
    assert {r["name"] for r in rows} == {p[0] for p in PRESET_PROMPTS}


def test_create_and_get_analyst_template(db: CrawlDB) -> None:
    tid = prompts_db.create(
        db, name="Mine", analysis_type="Summary", body="do the thing"
    )
    row = prompts_db.get(db, tid)
    assert row is not None
    assert row["builtin"] == 0
    assert row["hidden"] == 0
    assert row["body"] == "do the thing"


def test_update_text_on_builtin_refused(db: CrawlDB) -> None:
    builtin = prompts_db.list_templates(db)[0]
    ok = prompts_db.update(db, builtin["id"], body="rewritten")
    assert ok is False
    assert prompts_db.get(db, builtin["id"])["body"] == builtin["body"]


def test_update_text_on_analyst_template(db: CrawlDB) -> None:
    tid = prompts_db.create(db, name="Mine", analysis_type="Summary", body="a")
    assert prompts_db.update(db, tid, name="Renamed", body="b") is True
    row = prompts_db.get(db, tid)
    assert row["name"] == "Renamed"
    assert row["body"] == "b"


def test_update_no_fields_is_noop(db: CrawlDB) -> None:
    tid = prompts_db.create(db, name="Mine", analysis_type="Summary", body="a")
    assert prompts_db.update(db, tid) is False


def test_set_hidden_round_trips_on_builtin(db: CrawlDB) -> None:
    builtin = prompts_db.list_templates(db)[0]
    assert prompts_db.set_hidden(db, builtin["id"], True) is True
    # Hidden builtins drop out of the default listing, return with include_hidden.
    visible_ids = {r["id"] for r in prompts_db.list_templates(db)}
    assert builtin["id"] not in visible_ids
    all_ids = {r["id"] for r in prompts_db.list_templates(db, include_hidden=True)}
    assert builtin["id"] in all_ids
    assert prompts_db.set_hidden(db, builtin["id"], False) is True
    assert builtin["id"] in {r["id"] for r in prompts_db.list_templates(db)}


def test_clone_builtin_makes_editable_copy(db: CrawlDB) -> None:
    builtin = prompts_db.list_templates(db)[0]
    new_id = prompts_db.clone(db, builtin["id"], name="My copy")
    assert new_id is not None
    copy = prompts_db.get(db, new_id)
    assert copy["builtin"] == 0
    assert copy["body"] == builtin["body"]
    assert copy["analysis_type"] == builtin["analysis_type"]
    # The copy is editable where the source was not.
    assert prompts_db.update(db, new_id, body="changed") is True


def test_clone_unknown_returns_none(db: CrawlDB) -> None:
    assert prompts_db.clone(db, 9999, name="x") is None


def test_delete_builtin_refused_analyst_ok(db: CrawlDB) -> None:
    builtin = prompts_db.list_templates(db)[0]
    assert prompts_db.delete(db, builtin["id"]) is False
    tid = prompts_db.create(db, name="Mine", analysis_type="Summary", body="a")
    assert prompts_db.delete(db, tid) is True
    assert prompts_db.get(db, tid) is None


# --- routes ----------------------------------------------------------------


def test_route_list_excludes_hidden_by_default(auth_client, active_db: CrawlDB) -> None:
    seeded = active_db._conn.execute(
        "SELECT id FROM prompt_templates ORDER BY id LIMIT 1"
    ).fetchone()[0]
    prompts_db.set_hidden(active_db, seeded, True)
    body = auth_client.get("/api/prompts").json()
    assert seeded not in {p["id"] for p in body["prompts"]}
    body_all = auth_client.get("/api/prompts?include_hidden=true").json()
    assert seeded in {p["id"] for p in body_all["prompts"]}


def test_route_create_and_get(auth_client, active_db: CrawlDB) -> None:
    new_id = auth_client.post(
        "/api/prompts",
        json={"name": "Custom", "analysis_type": "Summary", "body": "go"},
    ).json()["id"]
    r = auth_client.get(f"/api/prompts/{new_id}")
    assert r.status_code == 200
    assert r.json()["name"] == "Custom"


def test_route_get_unknown_404(auth_client, active_db: CrawlDB) -> None:
    r = auth_client.get("/api/prompts/9999")
    assert r.status_code == 404
    assert r.json()["error"] == "unknown_prompt"


def test_route_patch_hidden_on_builtin_ok(auth_client, active_db: CrawlDB) -> None:
    builtin = auth_client.get("/api/prompts").json()["prompts"][0]
    r = auth_client.patch(f"/api/prompts/{builtin['id']}", json={"hidden": True})
    assert r.status_code == 200
    assert r.json()["hidden"] == 1


def test_route_patch_text_on_builtin_409(auth_client, active_db: CrawlDB) -> None:
    builtin = auth_client.get("/api/prompts").json()["prompts"][0]
    r = auth_client.patch(f"/api/prompts/{builtin['id']}", json={"body": "nope"})
    assert r.status_code == 409
    assert r.json()["error"] == "builtin_readonly"


def test_route_delete_builtin_409_analyst_ok(auth_client, active_db: CrawlDB) -> None:
    builtin = auth_client.get("/api/prompts").json()["prompts"][0]
    r = auth_client.delete(f"/api/prompts/{builtin['id']}")
    assert r.status_code == 409
    assert r.json()["error"] == "builtin_undeletable"

    new_id = auth_client.post(
        "/api/prompts",
        json={"name": "Custom", "analysis_type": "Summary", "body": "go"},
    ).json()["id"]
    r2 = auth_client.delete(f"/api/prompts/{new_id}")
    assert r2.status_code == 200
    assert r2.json()["deleted"] == new_id


def test_route_clone_via_endpoint(auth_client, active_db: CrawlDB) -> None:
    builtin = auth_client.get("/api/prompts").json()["prompts"][0]
    r = auth_client.post(f"/api/prompts/{builtin['id']}/clone")
    assert r.status_code == 200
    clone_id = r.json()["id"]
    cloned = auth_client.get(f"/api/prompts/{clone_id}").json()
    assert cloned["builtin"] == 0
    assert cloned["name"] == f"{builtin['name']} (copy)"
