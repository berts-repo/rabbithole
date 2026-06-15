"""Phase B4 — project registry, switch, and force-flag flow."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from backend.db import crawl as crawl_db
from backend.db import jobs as jobs_db
from backend.db.core import CrawlDB
from backend.services import registry
from backend.services.project_state import ProjectState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create(client, name: str, path: str):
    return client.post("/api/projects", json={"name": name, "path": path})


def _switch(client, project_id: str, force: bool = False):
    suffix = "?force=true" if force else ""
    return client.post(
        f"/api/project/switch{suffix}", json={"id": project_id}
    )


def _registry_state(projects_dir: Path) -> dict:
    return registry.load(projects_dir / "projects.json")


# ---------------------------------------------------------------------------
# Listing / creation
# ---------------------------------------------------------------------------


def test_list_empty_registry(auth_client):
    r = auth_client.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == {"projects": [], "active_id": None}


def test_create_persists_to_registry(auth_client, projects_dir):
    r = _create(auth_client, "Case-A", "case-a/case.db")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "id" in body and len(body["id"]) == 32

    state = _registry_state(projects_dir)
    assert len(state["projects"]) == 1
    assert state["projects"][0]["name"] == "Case-A"
    assert state["projects"][0]["path"] == "case-a/case.db"


def test_create_sets_file_modes(auth_client, projects_dir):
    _create(auth_client, "Case-Modes", "modes/case.db")
    db_path = projects_dir / "modes" / "case.db"
    assert db_path.is_file()
    db_mode = stat.S_IMODE(os.stat(db_path).st_mode)
    parent_mode = stat.S_IMODE(os.stat(db_path.parent).st_mode)
    assert db_mode == 0o600
    assert parent_mode == 0o700


def test_create_schema_initialized(auth_client, projects_dir):
    _create(auth_client, "Case-Schema", "schema/case.db")
    db_path = projects_dir / "schema" / "case.db"
    db = CrawlDB(db_path)
    try:
        names = {
            row[0]
            for row in db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        db.close()
    # Sample a few — full coverage lives in test_b2_schema.
    assert {"resources", "pages", "crawls", "settings", "schema_version"} <= names


def test_duplicate_name_rejected_case_insensitive(auth_client):
    assert _create(auth_client, "case-X", "x/case.db").status_code == 200
    r = _create(auth_client, "CASE-x", "x2/case.db")
    assert r.status_code == 400
    assert r.json()["error"] == "duplicate_name"


def test_duplicate_path_rejected(auth_client):
    # Two registered projects must not share a DB file — that bleeds one
    # project's nodes into the other's supposedly-isolated workspace.
    assert _create(auth_client, "Case-P1", "shared/case.db").status_code == 200
    r = _create(auth_client, "Case-P2", "shared/case.db")
    assert r.status_code == 400
    assert r.json()["error"] == "duplicate_path"


def test_recreate_at_orphaned_db_with_data_rejected(auth_client, projects_dir):
    # A deleted project leaves its DB on disk; the create form auto-derives the
    # path from the name, so recreating "Case" lands on the same file. A new
    # project must refuse to silently adopt that leftover data.
    from backend.db import resources as resources_db

    body = _create(auth_client, "Case-Orphan", "orphan/case.db").json()
    db = CrawlDB(projects_dir / "orphan" / "case.db")
    try:
        host = "a" * 56 + ".onion"
        resources_db.upsert_resource(db, f"http://{host}/", host, state="known")
    finally:
        db.close()
    assert auth_client.delete(f"/api/projects/{body['id']}").status_code == 200

    r = _create(auth_client, "Case-Fresh", "orphan/case.db")
    assert r.status_code == 409
    assert r.json()["error"] == "path_in_use"
    assert r.json()["resources"] == 1


def test_recreate_at_empty_orphaned_db_ok(auth_client, projects_dir):
    # The guard targets *data*, not mere file existence — an empty leftover DB
    # (schema only, no resources) is fresh enough to reuse.
    body = _create(auth_client, "Case-Empty", "empty/case.db").json()
    assert auth_client.delete(f"/api/projects/{body['id']}").status_code == 200
    r = _create(auth_client, "Case-EmptyAgain", "empty/case.db")
    assert r.status_code == 200


def test_bad_name_rejected(auth_client):
    r = _create(auth_client, "../escape", "ok/case.db")
    assert r.status_code == 400
    assert r.json()["error"] == "bad_name"


def test_bad_path_traversal_rejected(auth_client):
    r = _create(auth_client, "Case-T", "../escape.db")
    assert r.status_code == 400
    assert r.json()["error"] == "bad_path"


def test_absolute_path_outside_home_rejected(auth_client, tmp_path):
    outside = tmp_path / "outside.db"
    r = _create(auth_client, "Case-Abs", str(outside))
    assert r.status_code == 400
    assert r.json()["error"] == "bad_path"


def test_non_db_suffix_rejected(auth_client):
    r = _create(auth_client, "Case-Suffix", "case-a/case.sqlite")
    assert r.status_code == 400
    assert r.json()["error"] == "bad_path"


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------


def test_switch_unknown_project(auth_client):
    r = _switch(auth_client, "deadbeef" * 4)
    assert r.status_code == 404
    assert r.json()["error"] == "unknown_project"


def test_switch_attaches_active_db(auth_client, projects_dir):
    body = _create(auth_client, "Case-Sw", "sw/case.db").json()
    r = _switch(auth_client, body["id"])
    assert r.status_code == 200
    assert r.json() == {"ok": True, "active_id": body["id"]}

    listed = auth_client.get("/api/projects").json()
    assert listed["active_id"] == body["id"]

    # Stats is reachable now that a DB is attached.
    stats = auth_client.get("/api/stats")
    assert stats.status_code == 200
    assert stats.json() == {"domains": 0, "pages": 0, "flags": 0, "monitors": 0}

    # Registry file reflects active_id on disk.
    state = _registry_state(projects_dir)
    assert state["active_id"] == body["id"]


def test_stats_returns_409_without_active_project(auth_client):
    r = auth_client.get("/api/stats")
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "no_active_project"


def _seed_running_crawl(projects_dir: Path, project_path: str) -> dict:
    """Open the DB directly and insert a crawl detail row + linked running job.

    After the schema reset crawl work-status lives on the linked
    ``kind='crawl'`` job (``payload.crawl_id``), not a ``crawls.status`` column,
    so an in-flight crawl is a ``crawls`` row plus a ``running`` crawl job.
    """
    url = "http://abcdefghijabcdefghijabcdefghijabcdefghijabcdefghij2345.onion"
    db_path = (projects_dir / project_path).resolve()
    db = CrawlDB(db_path)
    try:
        crawl_id = crawl_db.create_crawl(
            db, seed_url=url, mode="BFS", collection_id=None, max_depth=None
        )
        with db.transaction(immediate=True) as c:
            c.execute(
                "UPDATE crawls SET pages_crawled=17 WHERE id=?", (crawl_id,)
            )
        jobs_db.create_job(
            db,
            kind="crawl",
            target_type="url",
            target_id=crawl_id,
            status="running",
            payload={"crawl_id": crawl_id, "url": url},
        )
    finally:
        db.close()
    return {"crawl_id": crawl_id}


def test_switch_blocked_by_running_crawl(auth_client, projects_dir):
    a = _create(auth_client, "Case-A", "a/case.db").json()
    b = _create(auth_client, "Case-B", "b/case.db").json()
    _switch(auth_client, a["id"])
    crawl = _seed_running_crawl(projects_dir, "a/case.db")
    # The DB the test opened is separate from the active handle; force the
    # active handle to see the inserted row by reopening via switch->same.
    # Easier: just reach into project_state and run the crawl insert against it.

    # The above creates a `crawls` row using a fresh CrawlDB handle; the
    # server's active handle queries its own connection so should see the
    # committed row (same SQLite file, WAL mode).

    r = _switch(auth_client, b["id"])
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "crawl_running"
    assert body["crawl_id"] == crawl["crawl_id"]
    assert body["pages_crawled"] == 17

    # active_id unchanged on registry
    state = _registry_state(projects_dir)
    assert state["active_id"] == a["id"]


def test_switch_force_marks_crawl_stopped(auth_client, projects_dir):
    a = _create(auth_client, "Case-A", "a/case.db").json()
    b = _create(auth_client, "Case-B", "b/case.db").json()
    _switch(auth_client, a["id"])
    _seed_running_crawl(projects_dir, "a/case.db")

    r = _switch(auth_client, b["id"], force=True)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "active_id": b["id"]}

    # Re-open the original project's DB and verify the crawl's linked job is
    # now cancelled (work-status lives on the job, not a crawls.status column).
    db = CrawlDB((projects_dir / "a/case.db").resolve())
    try:
        rows = db._conn.execute(
            "SELECT status FROM jobs WHERE kind='crawl'"
        ).fetchall()
    finally:
        db.close()
    assert [r[0] for r in rows] == ["cancelled"]


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_removes_from_registry_keeps_db(auth_client, projects_dir):
    body = _create(auth_client, "Case-Del", "del/case.db").json()
    db_path = projects_dir / "del" / "case.db"
    assert db_path.is_file()

    r = auth_client.delete(f"/api/projects/{body['id']}")
    assert r.status_code == 200

    assert db_path.is_file(), "DB file must survive registry deletion"
    state = _registry_state(projects_dir)
    assert state["projects"] == []


def test_delete_active_project_clears_active_db(auth_client, projects_dir):
    body = _create(auth_client, "Case-DelActive", "dela/case.db").json()
    _switch(auth_client, body["id"])
    assert auth_client.get("/api/stats").status_code == 200

    r = auth_client.delete(f"/api/projects/{body['id']}")
    assert r.status_code == 200

    # Active DB cleared → stats now 409.
    r = auth_client.get("/api/stats")
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "no_active_project"


def test_delete_unknown_id(auth_client):
    r = auth_client.delete("/api/projects/deadbeefdeadbeefdeadbeefdeadbeef")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Registry atomicity
# ---------------------------------------------------------------------------


def test_registry_save_atomic_rollback_on_replace_failure(
    auth_client, projects_dir, monkeypatch
):
    # Land one project so the registry has a baseline state on disk.
    _create(auth_client, "Case-First", "first/case.db")
    original = (projects_dir / "projects.json").read_bytes()

    # Now make os.replace fail; a second create attempt must not corrupt the
    # existing registry file.
    real_replace = os.replace

    def _boom(*args, **kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", _boom)
    r = _create(auth_client, "Case-Second", "second/case.db")
    # The save raised → 500 path. Restore replace + check disk state.
    monkeypatch.setattr(os, "replace", real_replace)
    assert r.status_code >= 500 or r.status_code == 400

    on_disk = (projects_dir / "projects.json").read_bytes()
    assert on_disk == original, "registry file must survive a failed save"


def test_registry_corrupt_file_treated_as_empty(projects_dir):
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / "projects.json").write_text("{not json")
    loaded = registry.load(projects_dir / "projects.json")
    assert loaded == {"projects": [], "active_id": None}


# ---------------------------------------------------------------------------
# Cross-route interaction
# ---------------------------------------------------------------------------


def test_settings_get_after_switch(auth_client):
    body = _create(auth_client, "Case-Set", "set/case.db").json()
    _switch(auth_client, body["id"])
    # Seeded default
    r = auth_client.get("/api/settings/tor.proxy")
    assert r.status_code == 200
    assert r.json() == {"key": "tor.proxy", "value": "socks5h://127.0.0.1:9050"}
