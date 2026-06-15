"""Phase B5c — route-level coverage for the crawl/seeds/nodes/edges/
watchlist/schedules endpoints.

Tests use ``TestClient`` (FastAPI's sync client over httpx) and attach a
fresh ``CrawlDB`` to the app's ``project_state`` so the ``get_active_db``
dependency resolves without going through ``POST /api/projects``. The
authenticated ``auth_client`` fixture (in conftest.py) handles the
Origin / session-cookie boilerplate.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import crawl as crawl_db
from backend.db import jobs as jobs_db
from backend.db.core import CrawlDB


ONION = "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad"
SEED_URL = f"http://{ONION}.onion/"
# 56 chars of base32 — a valid v3 onion host.
OTHER_ONION = "abacus" * 9 + "22"
OTHER_URL = f"http://{OTHER_ONION}.onion/"


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    """Attach a fresh ``CrawlDB`` to ``project_state`` for the test's lifetime."""
    db = CrawlDB(tmp_path / "routes.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


# ---------------------------------------------------------------------------
# /api/seeds
# ---------------------------------------------------------------------------


def test_seeds_create_list_delete(auth_client, active_db):
    r = auth_client.post("/api/seeds", json={"url": SEED_URL, "label": "hi"})
    assert r.status_code == 200, r.text
    assert r.json()["added"] is True

    r = auth_client.get("/api/seeds")
    assert r.status_code == 200
    urls = [s["url"] for s in r.json()["seeds"]]
    assert SEED_URL in urls

    r = auth_client.request("DELETE", "/api/seeds", params={"url": SEED_URL})
    assert r.status_code == 200
    r = auth_client.request("DELETE", "/api/seeds", params={"url": SEED_URL})
    assert r.status_code == 404


def test_seeds_rejects_clearnet(auth_client, active_db):
    r = auth_client.post(
        "/api/seeds", json={"url": "http://example.com/", "label": "no"}
    )
    assert r.status_code == 400
    assert r.json()["error"] == "bad_url"


def test_seeds_patch_label(auth_client, active_db):
    auth_client.post("/api/seeds", json={"url": SEED_URL, "label": "old"})

    r = auth_client.patch(
        "/api/seeds", params={"url": SEED_URL}, json={"label": "renamed"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["label"] == "renamed"

    r = auth_client.get("/api/seeds")
    seed = next(s for s in r.json()["seeds"] if s["url"] == SEED_URL)
    assert seed["label"] == "renamed"

    # Clearing the label round-trips as null.
    r = auth_client.patch(
        "/api/seeds", params={"url": SEED_URL}, json={"label": None}
    )
    assert r.status_code == 200
    r = auth_client.get("/api/seeds")
    seed = next(s for s in r.json()["seeds"] if s["url"] == SEED_URL)
    assert seed["label"] is None

    # Unknown URL → 404.
    r = auth_client.patch(
        "/api/seeds",
        params={"url": "http://ghostxxx.onion/"},
        json={"label": "x"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_seed"


# ---------------------------------------------------------------------------
# /api/watchlist
# ---------------------------------------------------------------------------


def test_watchlist_add_list_delete(auth_client, active_db):
    r = auth_client.post("/api/watchlist", json={"term": "ransomware"})
    assert r.status_code == 200
    term_id = r.json()["id"]

    r = auth_client.get("/api/watchlist")
    assert r.status_code == 200
    assert any(t["term"] == "ransomware" for t in r.json()["terms"])

    r = auth_client.delete(f"/api/watchlist/{term_id}")
    assert r.status_code == 200
    r = auth_client.delete(f"/api/watchlist/{term_id}")
    assert r.status_code == 404


def test_watchlist_rejects_oversized_term(auth_client, active_db):
    r = auth_client.post("/api/watchlist", json={"term": "x" * 1000})
    assert r.status_code == 400
    assert r.json()["error"] == "bad_term"


def test_watchlist_dedupes(auth_client, active_db):
    auth_client.post("/api/watchlist", json={"term": "dup"})
    r = auth_client.post("/api/watchlist", json={"term": "dup"})
    assert r.status_code == 400
    assert "duplicate" in r.json()["message"]


def test_watchlist_update_renames_term(auth_client, active_db):
    term_id = auth_client.post(
        "/api/watchlist", json={"term": "before"}
    ).json()["id"]

    r = auth_client.patch(f"/api/watchlist/{term_id}", json={"term": "  after  "})
    assert r.status_code == 200
    assert r.json()["term"] == "after"

    terms = auth_client.get("/api/watchlist").json()["terms"]
    assert any(t["term"] == "after" for t in terms)
    assert all(t["term"] != "before" for t in terms)


def test_watchlist_update_404_on_unknown(auth_client, active_db):
    r = auth_client.patch("/api/watchlist/9999", json={"term": "ghost"})
    assert r.status_code == 404


def test_watchlist_update_rejects_empty(auth_client, active_db):
    term_id = auth_client.post(
        "/api/watchlist", json={"term": "keep"}
    ).json()["id"]
    r = auth_client.patch(f"/api/watchlist/{term_id}", json={"term": "   "})
    assert r.status_code == 400
    assert r.json()["error"] == "bad_term"


def test_watchlist_update_rejects_duplicate(auth_client, active_db):
    auth_client.post("/api/watchlist", json={"term": "alpha"})
    beta_id = auth_client.post("/api/watchlist", json={"term": "beta"}).json()["id"]
    r = auth_client.patch(f"/api/watchlist/{beta_id}", json={"term": "alpha"})
    assert r.status_code == 400
    assert "duplicate" in r.json()["message"]


# ---------------------------------------------------------------------------
# /api/nodes
# ---------------------------------------------------------------------------


def test_nodes_create_get_and_toggles(auth_client, active_db):
    r = auth_client.post("/api/nodes", json={"url": SEED_URL})
    assert r.status_code == 200
    node_id = r.json()["id"]

    r = auth_client.get(f"/api/nodes/{node_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["url"] == SEED_URL
    assert body["state"] == "known"

    assert auth_client.patch(f"/api/nodes/{node_id}/reviewed", json={"reviewed": True}).status_code == 200
    assert auth_client.patch(f"/api/nodes/{node_id}/opened").status_code == 200
    assert auth_client.patch(f"/api/nodes/{node_id}/analysis_excluded", json={"excluded": True}).status_code == 200

    r = auth_client.get(f"/api/nodes/{node_id}")
    body = r.json()
    assert body["reviewed"] is True
    assert body["analysis_excluded"] is True
    assert body["opened_at"] is not None


def test_nodes_404_on_unknown(auth_client, active_db):
    assert auth_client.get("/api/nodes/9999").status_code == 404
    assert auth_client.patch("/api/nodes/9999/opened").status_code == 404


def test_create_node_invalidates_graph_cache(auth_client, active_db, monkeypatch):
    # Regression: POST /api/nodes adds a node to the /api/graph payload, so it
    # must bust the cached build. Without this the next poll returns the stale
    # graph and the node never reaches the canvas (it's only counted via the
    # DB-backed /api/stats) — the "Add to Graph shows nothing" bug.
    from backend.db import graph as graph_db
    from backend.routes import graph as graph_routes

    calls = {"n": 0}
    real = graph_db.build_payload

    def counting(db):
        calls["n"] += 1
        return real(db)

    monkeypatch.setattr(graph_routes, "build_payload", counting)

    auth_client.get("/api/graph")  # build 1 (cold)
    node_id = auth_client.post("/api/nodes", json={"url": SEED_URL}).json()["id"]
    payload = auth_client.get("/api/graph").json()  # build 2 (post-invalidate)

    assert calls["n"] == 2
    assert any(n["id"] == node_id for n in payload["nodes"])


def test_create_nodes_batch_materializes_and_reports_invalid(auth_client, active_db):
    # "Add all to Graph" — valid onions land as known nodes; a clearnet URL is
    # reported in `invalid` rather than sinking the batch.
    r = auth_client.post(
        "/api/nodes/batch",
        json={"urls": [SEED_URL, OTHER_URL, "http://example.com/"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert {n["url"] for n in body["nodes"]} == {SEED_URL, OTHER_URL}
    assert [bad["url"] for bad in body["invalid"]] == ["http://example.com/"]
    # The new nodes reach the graph payload.
    ids = {n["id"] for n in body["nodes"]}
    payload = auth_client.get("/api/graph").json()
    assert ids <= {n["id"] for n in payload["nodes"]}


def test_create_nodes_batch_invalidates_graph_cache(auth_client, active_db, monkeypatch):
    from backend.db import graph as graph_db
    from backend.routes import graph as graph_routes

    calls = {"n": 0}
    real = graph_db.build_payload

    def counting(db):
        calls["n"] += 1
        return real(db)

    monkeypatch.setattr(graph_routes, "build_payload", counting)

    auth_client.get("/api/graph")  # build 1 (cold)
    auth_client.post("/api/nodes/batch", json={"urls": [SEED_URL, OTHER_URL]})
    auth_client.get("/api/graph")  # build 2 (post-invalidate)
    assert calls["n"] == 2


def test_create_nodes_batch_all_invalid_skips_cache_bust(auth_client, active_db, monkeypatch):
    # No valid URL → nothing upserted → the cache must NOT be invalidated
    # (a needless rebuild on a no-op write).
    from backend.db import graph as graph_db
    from backend.routes import graph as graph_routes

    calls = {"n": 0}
    real = graph_db.build_payload

    def counting(db):
        calls["n"] += 1
        return real(db)

    monkeypatch.setattr(graph_routes, "build_payload", counting)

    auth_client.get("/api/graph")  # build 1 (cold)
    r = auth_client.post("/api/nodes/batch", json={"urls": ["http://example.com/"]})
    assert r.json()["nodes"] == []
    auth_client.get("/api/graph")  # served from cache — no rebuild
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# /api/nodes/:id/open  — F4b right-click slice 4 (Open in Tor Browser)
# ---------------------------------------------------------------------------


def _patch_launcher(monkeypatch, calls: list[tuple[str, str]], path: Path):
    """Stub ``security.paths.launch_browser`` + ``discover_browser_path``
    so tests never spawn a real process or touch the filesystem allowlist.

    ``calls`` accumulates ``(browser_path, url)`` tuples per launch so
    assertions can verify both the path and the URL passed through. The
    fake ``discover_browser_path`` returns ``path`` (a tmp file the
    caller has already chmod'd executable) so the route's unset-setting
    fallback resolves.
    """
    from backend.routes import nodes as nodes_route

    monkeypatch.setattr(
        nodes_route,
        "launch_browser",
        lambda p, url: calls.append((str(p), url)),
    )
    monkeypatch.setattr(
        nodes_route, "discover_browser_path", lambda: path
    )


def test_open_node_launches_when_armed(
    auth_client, active_db, app, monkeypatch, tmp_path
):
    node_id = auth_client.post("/api/nodes", json={"url": SEED_URL}).json()["id"]

    fake_browser = tmp_path / "start-tor-browser"
    fake_browser.write_text("#!/bin/sh\n")
    fake_browser.chmod(0o755)
    calls: list[tuple[str, str]] = []
    _patch_launcher(monkeypatch, calls, fake_browser)
    app.state.kill_switch.engaged.clear()

    r = auth_client.post(f"/api/nodes/{node_id}/open")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["browser"] == "start-tor-browser"
    assert body["opened_at"]
    assert calls == [(str(fake_browser), SEED_URL)]

    # opened_at propagated to the row.
    row = auth_client.get(f"/api/nodes/{node_id}").json()
    assert row["opened_at"] == body["opened_at"]


def test_open_node_refuses_when_kill_switch_engaged(
    auth_client, active_db, app, monkeypatch, tmp_path
):
    node_id = auth_client.post("/api/nodes", json={"url": SEED_URL}).json()["id"]

    fake_browser = tmp_path / "start-tor-browser"
    fake_browser.write_text("#!/bin/sh\n")
    fake_browser.chmod(0o755)
    calls: list[tuple[str, str]] = []
    _patch_launcher(monkeypatch, calls, fake_browser)
    app.state.kill_switch.engaged.set()
    try:
        r = auth_client.post(f"/api/nodes/{node_id}/open")
    finally:
        app.state.kill_switch.engaged.clear()

    assert r.status_code == 409
    assert r.json() == {"error": "tor_unavailable", "reason": "tripped"}
    assert calls == []
    # opened_at must NOT have been written.
    assert auth_client.get(f"/api/nodes/{node_id}").json()["opened_at"] is None


def test_open_node_412_when_browser_unconfigured(
    auth_client, active_db, app, monkeypatch
):
    node_id = auth_client.post("/api/nodes", json={"url": SEED_URL}).json()["id"]

    from backend.routes import nodes as nodes_route

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        nodes_route,
        "launch_browser",
        lambda p, url: calls.append((str(p), url)),
    )
    monkeypatch.setattr(nodes_route, "discover_browser_path", lambda: None)
    app.state.kill_switch.engaged.clear()

    r = auth_client.post(f"/api/nodes/{node_id}/open")
    assert r.status_code == 412
    assert r.json() == {"error": "browser_unconfigured"}
    assert calls == []


def test_open_node_404_on_unknown_node(auth_client, active_db, app):
    app.state.kill_switch.engaged.clear()
    r = auth_client.post("/api/nodes/9999/open")
    assert r.status_code == 404


def test_open_node_422_when_validator_rejects_path(
    auth_client, active_db, app, monkeypatch
):
    """An explicit ``browser.path`` setting that fails ``validate_browser_path``
    surfaces as 422 ``browser_invalid`` — covers the symlink-swap /
    out-of-allowlist case. We bypass ``put_setting`` (which would itself
    refuse a non-allowlisted path) by patching the route's ``get_setting``
    import and forcing the validator to refuse, isolating the surfacing
    behaviour from the validator's own test coverage in test_b3_security."""
    node_id = auth_client.post("/api/nodes", json={"url": SEED_URL}).json()["id"]

    from backend.routes import nodes as nodes_route
    from backend.security.paths import PathError

    monkeypatch.setattr(
        nodes_route, "get_setting", lambda db, key: "/opt/tor-browser/Browser/firefox"
    )

    def _refuse(value: object):
        raise PathError("not allowlisted (test)")

    monkeypatch.setattr(nodes_route, "validate_browser_path", _refuse)
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        nodes_route,
        "launch_browser",
        lambda p, url: calls.append((str(p), url)),
    )
    app.state.kill_switch.engaged.clear()

    r = auth_client.post(f"/api/nodes/{node_id}/open")
    assert r.status_code == 422
    assert r.json()["error"] == "browser_invalid"
    assert "not allowlisted" in r.json()["message"]
    assert calls == []


# ---------------------------------------------------------------------------
# /api/edges
# ---------------------------------------------------------------------------


def test_edges_create_analyst_then_delete(auth_client, active_db):
    a = auth_client.post("/api/nodes", json={"url": SEED_URL}).json()["id"]
    b = auth_client.post("/api/nodes", json={"url": OTHER_URL}).json()["id"]
    r = auth_client.post("/api/edges", json={"from_id": a, "to_id": b, "label": "rel"})
    assert r.status_code == 200

    # Self-loop rejected.
    assert auth_client.post(
        "/api/edges", json={"from_id": a, "to_id": a}
    ).status_code == 400

    r = auth_client.request("DELETE", "/api/edges", params={"from_id": a, "to_id": b})
    assert r.status_code == 200
    r = auth_client.request("DELETE", "/api/edges", params={"from_id": a, "to_id": b})
    assert r.status_code == 404


def test_edges_cannot_delete_crawl_source(auth_client, active_db):
    a = auth_client.post("/api/nodes", json={"url": SEED_URL}).json()["id"]
    b = auth_client.post("/api/nodes", json={"url": OTHER_URL}).json()["id"]
    with active_db.transaction(immediate=True) as c:
        c.execute(
            "INSERT INTO edges(from_id, to_id, source) VALUES (?, ?, 'crawl')",
            (a, b),
        )
    r = auth_client.request("DELETE", "/api/edges", params={"from_id": a, "to_id": b})
    assert r.status_code == 400
    assert r.json()["error"] == "not_analyst_edge"


# ---------------------------------------------------------------------------
# /api/schedules
# ---------------------------------------------------------------------------


def test_schedules_crud(auth_client, active_db):
    body = {
        "url": SEED_URL,
        "interval_hours": 4,
        "mode": "BFS",
        "label": "daily",
    }
    r = auth_client.post("/api/schedules", json=body)
    assert r.status_code == 200

    r = auth_client.get("/api/schedules")
    rows = r.json()["schedules"]
    assert any(s["url"] == SEED_URL and s["active"] for s in rows)

    r = auth_client.patch(
        "/api/schedules", params={"url": SEED_URL}, json={"active": False}
    )
    assert r.status_code == 200
    r = auth_client.get("/api/schedules")
    rows = r.json()["schedules"]
    assert any(s["url"] == SEED_URL and s["active"] is False for s in rows)

    r = auth_client.request("DELETE", "/api/schedules", params={"url": SEED_URL})
    assert r.status_code == 200
    r = auth_client.request("DELETE", "/api/schedules", params={"url": SEED_URL})
    assert r.status_code == 404


def test_schedules_rejects_bad_mode(auth_client, active_db):
    r = auth_client.post(
        "/api/schedules",
        json={"url": SEED_URL, "interval_hours": 1, "mode": "NotAMode"},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# /api/crawl
# ---------------------------------------------------------------------------
#
# Intake validation (clearnet seed, bad mode, dedupe against a running
# crawl) lives on ``POST /api/crawl/queue`` now — see
# ``test_crawl_queue_routes.py``. This module only covers the runtime
# control surface (``stop`` / ``status`` / ``history``).


def test_crawl_status_and_history(auth_client, active_db):
    crawl_db.create_crawl(
        active_db, seed_url=SEED_URL, mode="BFS", collection_id=None, max_depth=None
    )
    r = auth_client.get("/api/crawl/status")
    assert r.status_code == 200
    body = r.json()
    assert body["running"] is False
    r = auth_client.get("/api/crawl/history")
    assert r.status_code == 200
    assert len(r.json()["crawls"]) >= 1


def test_crawl_stop_idempotent_when_nothing_active(auth_client, active_db):
    # Stop is idempotent: nothing to stop is success, not a 404. Lets the
    # UI fire Stop on a crawl that already ended (kill-switch teardown,
    # natural completion) without surfacing an error toast.
    r = auth_client.post("/api/crawl/stop", json={})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "already_stopped": True}


def test_crawl_stop_reaps_half_state(auth_client, active_db):
    # Half state: a crawls row + a linked 'running' crawl job but no in-process
    # runner (e.g. a process crash). Work-status lives on the job after the
    # schema reset, so find_active reads it via payload.crawl_id.
    crawl_id = crawl_db.create_crawl(
        active_db, seed_url=SEED_URL, mode="BFS", collection_id=None, max_depth=None
    )
    jobs_db.create_job(
        active_db,
        kind="crawl",
        target_type="url",
        target_id=crawl_id,
        status="running",
        payload={"crawl_id": crawl_id, "url": SEED_URL},
    )
    r = auth_client.post("/api/crawl/stop", json={})
    assert r.status_code == 200
    assert "reaped" in r.json()
    row = crawl_db.find_active(active_db)
    assert row is None


# ---------------------------------------------------------------------------
# Auth on SSE
# ---------------------------------------------------------------------------


def test_crawl_log_requires_auth(client):
    # No cookie → middleware rejects before the stream opens. SSE is GET
    # (a safe method), so Origin is not required; the cookie is the gate.
    r = client.get("/api/crawl/log")
    assert r.status_code == 401


def test_kill_switch_events_requires_auth(client):
    # Same gate as the crawl SSE — middleware rejects an unauthenticated
    # caller before the stream opens.
    r = client.get("/api/kill_switch/events")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Kill-switch SSE channel separation
#
# Regression coverage for the bug that motivated the dedicated control-plane
# route: when ``/api/crawl/events`` carried the ``kill_switch.*`` channels,
# the frontend's ``sse.pauseAll()`` on trip closed the only stream capable
# of delivering ``kill_switch.clear`` — leaving the operator unable to
# recover. The two streams are now physically separate.
# ---------------------------------------------------------------------------


import asyncio  # noqa: E402
import json  # noqa: E402

from backend.services.event_bus import EventBus  # noqa: E402
from backend.services.sse import sse_stream  # noqa: E402


_KILL_SWITCH_CHANNELS = [
    "kill_switch.engaged",
    "kill_switch.banner",
    "kill_switch.clear",
]
_CRAWL_EVENTS_CHANNELS = ["crawl.status", "crawl.page", "crawl.alert"]


def _parse(chunk: bytes) -> dict:
    text = chunk.decode("utf-8")
    assert text.startswith("data: "), text
    return json.loads(text[len("data: ") :].strip())


async def _collect_n(stream, n: int) -> list[dict]:
    out: list[dict] = []
    async for chunk in stream:
        out.append(_parse(chunk))
        if len(out) >= n:
            return out
    return out


async def test_kill_switch_sse_delivers_all_three_channels():
    bus = EventBus()
    stream = sse_stream(bus, _KILL_SWITCH_CHANNELS)
    consumer = asyncio.create_task(_collect_n(stream, 3))

    # Let _pump tasks register with the bus before we publish — mirrors
    # the established pattern in test_b5a_kill_switch.py::_collect.
    await asyncio.sleep(0.01)

    bus.publish("kill_switch.engaged", {"reason": "tor_down"})
    bus.publish("kill_switch.banner", {"reason": "tor_down"})
    bus.publish("kill_switch.clear", {})

    events = await asyncio.wait_for(consumer, timeout=1.0)
    assert sorted(e["channel"] for e in events) == sorted(_KILL_SWITCH_CHANNELS)

    await stream.aclose()


async def test_crawl_events_does_not_carry_kill_switch_channels():
    """``/api/crawl/events`` must not deliver ``kill_switch.*`` envelopes.

    Verified at the ``sse_stream`` layer with the same channel list the
    route handler uses. Publishing a ``kill_switch.engaged`` event with
    only ``crawl.*`` subscribers should be a no-op; publishing
    ``crawl.status`` should arrive immediately.
    """
    bus = EventBus()
    stream = sse_stream(bus, _CRAWL_EVENTS_CHANNELS)
    consumer = asyncio.create_task(_collect_n(stream, 1))

    await asyncio.sleep(0.01)

    bus.publish("kill_switch.engaged", {"reason": "tor_down"})
    bus.publish("crawl.status", {"status": "running"})

    events = await asyncio.wait_for(consumer, timeout=1.0)
    assert [e["channel"] for e in events] == ["crawl.status"]

    # And nothing further is waiting — the kill_switch event was never
    # subscribed and so was never queued.
    follow_up = asyncio.create_task(stream.__anext__())
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(asyncio.shield(follow_up), timeout=0.1)
    follow_up.cancel()
    try:
        await follow_up
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        pass

    await stream.aclose()
