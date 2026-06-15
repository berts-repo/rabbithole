"""Phase B4 — ``GET/PUT /api/settings/{key}`` + validator coverage."""
from __future__ import annotations

import json

import pytest

from backend.db import settings as settings_module
from backend.db.settings import (
    SETTING_VALIDATORS,
    UnknownSettingError,
    get_setting,
    put_setting,
    validators_for_key,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _put(client, key: str, value):
    return client.put(f"/api/settings/{key}", json={"value": value})


def _get(client, key: str):
    return client.get(f"/api/settings/{key}")


@pytest.fixture
def active_client(auth_client):
    """Auth client with one active project for the settings routes to hit."""
    r = auth_client.post(
        "/api/projects", json={"name": "Settings-Case", "path": "settings/case.db"}
    )
    project_id = r.json()["id"]
    auth_client.post("/api/project/switch", json={"id": project_id})
    return auth_client


# Patches the fastembed registry lookup with a deterministic fixture so the
# tests don't have to import fastembed for real (which takes ~hundreds of ms).
@pytest.fixture(autouse=True)
def _stub_fastembed_models(monkeypatch):
    monkeypatch.setattr(
        settings_module,
        "_fastembed_models",
        frozenset({"BAAI/bge-small-en-v1.5", "BAAI/bge-base-en-v1.5"}),
    )


# ---------------------------------------------------------------------------
# Static validators
# ---------------------------------------------------------------------------


def test_put_tor_proxy_accepts_loopback(active_client):
    r = _put(active_client, "tor.proxy", "socks5h://127.0.0.1:9150")
    assert r.status_code == 200
    assert r.json() == {"key": "tor.proxy", "value": "socks5h://127.0.0.1:9150"}


def test_put_tor_proxy_rejects_socks5_without_h(active_client):
    r = _put(active_client, "tor.proxy", "socks5://127.0.0.1:9050")
    assert r.status_code == 400
    assert r.json()["error"] == "bad_value"


@pytest.mark.parametrize("value,stored", [
    (True, "true"),
    (False, "false"),
    ("true", "true"),
    ("False", "false"),
    (1, "true"),
    (0, "false"),
    ("yes", "true"),
    ("NO", "false"),
])
def test_put_kill_switch_coerces_bools(active_client, value, stored):
    r = _put(active_client, "tor.kill_switch", value)
    assert r.status_code == 200
    assert r.json()["value"] == stored


def test_put_kill_switch_rejects_garbage(active_client):
    r = _put(active_client, "tor.kill_switch", "maybe")
    assert r.status_code == 400
    assert r.json()["error"] == "bad_value"


@pytest.mark.parametrize("mode", ["fresh", "reuse"])
def test_put_browser_launch_mode_accepts_enum(active_client, mode):
    r = _put(active_client, "browser.launch_mode", mode)
    assert r.status_code == 200
    assert r.json()["value"] == mode


def test_put_browser_launch_mode_rejects_other(active_client):
    r = _put(active_client, "browser.launch_mode", "incognito")
    assert r.status_code == 400


@pytest.mark.parametrize("pacing", ["fast", "polite", "stealth"])
def test_put_crawl_pacing_accepts_enum(active_client, pacing):
    r = _put(active_client, "crawl.pacing", pacing)
    assert r.status_code == 200
    assert r.json()["value"] == pacing


def test_put_crawl_pacing_rejects_other(active_client):
    r = _put(active_client, "crawl.pacing", "turbo")
    assert r.status_code == 400


@pytest.mark.parametrize(
    "color", ["domain", "cluster", "depth", "category", "infra", "label"]
)
def test_put_graph_color_accepts_enum(active_client, color):
    r = _put(active_client, "graph.color", color)
    assert r.status_code == 200
    assert r.json()["value"] == color


def test_put_graph_color_rejects_other(active_client):
    r = _put(active_client, "graph.color", "banana")
    assert r.status_code == 400


@pytest.mark.parametrize(
    "layout", ["force", "radial", "hierarchical", "concentric", "timeline"]
)
def test_put_graph_layout_accepts_enum(active_client, layout):
    r = _put(active_client, "graph.layout", layout)
    assert r.status_code == 200
    assert r.json()["value"] == layout


def test_put_graph_layout_rejects_other(active_client):
    r = _put(active_client, "graph.layout", "spiral")
    assert r.status_code == 400


@pytest.mark.parametrize("n", [0, 1, 3, 10])
def test_put_graph_max_hops_accepts_in_range(active_client, n):
    r = _put(active_client, "graph.max_hops", n)
    assert r.status_code == 200
    assert r.json()["value"] == str(n)


@pytest.mark.parametrize("n", [-1, 11, 99, True])
def test_put_graph_max_hops_rejects_out_of_range_or_bool(active_client, n):
    r = _put(active_client, "graph.max_hops", n)
    assert r.status_code == 400


@pytest.mark.parametrize("v", [0.0, 0.1, 0.5, 1.0])
def test_put_graph_bridge_betweenness_min_accepts(active_client, v):
    r = _put(active_client, "graph.bridge_betweenness_min", v)
    assert r.status_code == 200
    assert float(r.json()["value"]) == v


@pytest.mark.parametrize("v", [-0.01, 1.01, "nope"])
def test_put_graph_bridge_betweenness_min_rejects(active_client, v):
    r = _put(active_client, "graph.bridge_betweenness_min", v)
    assert r.status_code == 400


def test_put_graph_bridge_in_degree_min_accepts(active_client):
    r = _put(active_client, "graph.bridge_in_degree_min", 5)
    assert r.status_code == 200
    assert r.json()["value"] == "5"


@pytest.mark.parametrize("value,stored", [
    ([3, 1, 2, 1], "1,2,3"),       # list → de-duped, ascending CSV
    ("5, 3, 5", "3,5"),            # CSV string → same normalization
    ([], ""),                       # empty is allowed (no pins)
])
def test_put_graph_pinned_ids_normalizes(active_client, value, stored):
    r = _put(active_client, "graph.pinned_ids", value)
    assert r.status_code == 200
    assert r.json()["value"] == stored


@pytest.mark.parametrize("value", [0, -1, "abc", [True], [1.5]])
def test_put_graph_pinned_ids_rejects_bad(active_client, value):
    r = _put(active_client, "graph.pinned_ids", value)
    assert r.status_code == 400
    assert r.json()["error"] == "bad_value"


@pytest.mark.parametrize("key", ["graph.label_include", "graph.label_exclude"])
@pytest.mark.parametrize("value,stored", [
    ([3, 1, 2, 1], "1,2,3"),
    ("5, 3, 5", "3,5"),
    ([], ""),
])
def test_put_graph_label_filter_normalizes(active_client, key, value, stored):
    r = _put(active_client, key, value)
    assert r.status_code == 200
    assert r.json()["value"] == stored


@pytest.mark.parametrize("key", ["graph.label_include", "graph.label_exclude"])
@pytest.mark.parametrize("value", [0, -1, "abc", [True]])
def test_put_graph_label_filter_rejects_bad(active_client, key, value):
    r = _put(active_client, key, value)
    assert r.status_code == 400
    assert r.json()["error"] == "bad_value"


def test_put_graph_collapse_normalizes(active_client):
    # De-dupes domains, sorts + de-dupes label ids, drops empty tab entries.
    value = {
        "global": {"domains": ["b.onion", "a.onion", "a.onion"], "labels": [3, 1, 3]},
        "ns:empty": {"domains": [], "labels": []},
    }
    r = _put(active_client, "graph.collapse", value)
    assert r.status_code == 200
    stored = json.loads(r.json()["value"])
    assert stored == {"global": {"domains": ["b.onion", "a.onion"], "labels": [1, 3]}}


def test_put_graph_collapse_round_trips_json_string(active_client):
    # A JSON string input round-trips (idempotent normalize).
    r = _put(active_client, "graph.collapse", '{"global":{"domains":["x.onion"],"labels":[2]}}')
    assert r.status_code == 200
    assert json.loads(r.json()["value"]) == {"global": {"domains": ["x.onion"], "labels": [2]}}


@pytest.mark.parametrize("value", [
    [],                                              # not an object
    {"global": {"domains": "x.onion", "labels": []}},  # domains not a list
    {"global": {"domains": [], "labels": [0]}},         # non-positive id
    {"global": {"domains": [], "labels": [True]}},      # bool id
    {"": {"domains": [], "labels": [1]}},               # blank tab id
])
def test_put_graph_collapse_rejects_bad(active_client, value):
    r = _put(active_client, "graph.collapse", value)
    assert r.status_code == 400
    assert r.json()["error"] == "bad_value"


def test_put_embedding_model_accepts_known(active_client):
    r = _put(active_client, "embedding.model", "BAAI/bge-base-en-v1.5")
    assert r.status_code == 200
    assert r.json()["value"] == "BAAI/bge-base-en-v1.5"


def test_put_embedding_model_rejects_unknown(active_client):
    r = _put(active_client, "embedding.model", "not-a-real-model")
    assert r.status_code == 400
    assert r.json()["error"] == "bad_value"


def test_put_embedding_auto_start_coerces(active_client):
    r = _put(active_client, "embedding.auto_start", False)
    assert r.status_code == 200
    assert r.json()["value"] == "false"


# ---------------------------------------------------------------------------
# Unknown keys / templated search.engine.{id}.enabled
# ---------------------------------------------------------------------------


def test_put_unknown_key_400(active_client):
    r = _put(active_client, "totally.made.up", "x")
    assert r.status_code == 400
    assert r.json()["error"] == "unknown_setting"


def test_put_search_engine_enabled_without_engine(active_client):
    r = _put(active_client, "search.engine.42.enabled", True)
    assert r.status_code == 400
    assert r.json()["error"] == "bad_value"
    assert "unknown search engine id" in r.json()["message"]


def test_put_search_engine_enabled_after_engine_insert(
    active_client, projects_dir, monkeypatch
):
    # Reach into the live ProjectState to insert an engine row directly.
    # This sidesteps the (still-unbuilt) search-engines CRUD route.
    from backend.main import create_app  # noqa: F401 — ensures import side-effects
    # The active DB is held by the request app's project_state; pull it
    # out via the test client.
    app = active_client.app
    state = app.state.project_state
    db = state.active_db
    with db.transaction(immediate=True) as c:
        c.execute(
            "INSERT INTO search_engines(id, label, url) VALUES (?,?,?)",
            (
                7,
                "test",
                "http://abcdefghijabcdefghijabcdefghijabcdefghijabcdefghij2345.onion/",
            ),
        )
    r = _put(active_client, "search.engine.7.enabled", True)
    assert r.status_code == 200, r.text
    assert r.json()["value"] == "true"


# ---------------------------------------------------------------------------
# GET semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tab",
    [
        "live_crawl",
        "activity",
        "scheduled_crawls",
        "monitors",
        "inventory",
        "domains",
        "flags",
        "fingerprints",
        "collection",
        "bookmarks",
    ],
)
def test_put_workspace_bottom_tab_accepts_enum(active_client, tab):
    r = _put(active_client, "workspace.bottomTab", tab)
    assert r.status_code == 200
    assert r.json()["value"] == tab


def test_put_workspace_bottom_tab_rejects_other(active_client):
    r = _put(active_client, "workspace.bottomTab", "junk")
    assert r.status_code == 400
    assert r.json()["error"] == "bad_value"


def test_put_workspace_bottom_tabs_accepts_list_and_normalizes(active_client):
    # Out-of-order, duplicated input normalizes to canonical-order CSV.
    r = _put(
        active_client,
        "workspace.bottomTabs",
        ["collection", "live_crawl", "collection"],
    )
    assert r.status_code == 200
    assert r.json()["value"] == "live_crawl,collection"


def test_put_workspace_bottom_tabs_accepts_csv_string(active_client):
    r = _put(active_client, "workspace.bottomTabs", "live_crawl, flags")
    assert r.status_code == 200
    assert r.json()["value"] == "live_crawl,flags"


def test_put_workspace_bottom_tabs_round_trips(active_client):
    _put(active_client, "workspace.bottomTabs", ["activity", "domains"])
    r = _get(active_client, "workspace.bottomTabs")
    assert r.status_code == 200
    assert r.json() == {"key": "workspace.bottomTabs", "value": "activity,domains"}


def test_put_workspace_bottom_tabs_rejects_unknown(active_client):
    r = _put(active_client, "workspace.bottomTabs", ["live_crawl", "junk"])
    assert r.status_code == 400
    assert r.json()["error"] == "bad_value"


def test_put_workspace_bottom_tabs_rejects_empty(active_client):
    r = _put(active_client, "workspace.bottomTabs", [])
    assert r.status_code == 400
    assert r.json()["error"] == "bad_value"


@pytest.mark.parametrize("tab", ["search", "intel", "crawl"])
def test_put_nav_left_tab_accepts_enum(active_client, tab):
    r = _put(active_client, "nav.leftTab", tab)
    assert r.status_code == 200
    assert r.json()["value"] == tab


def test_put_nav_left_tab_rejects_other(active_client):
    r = _put(active_client, "nav.leftTab", "elsewhere")
    assert r.status_code == 400
    assert r.json()["error"] == "bad_value"


def test_get_after_put_returns_normalized_value(active_client):
    _put(active_client, "tor.kill_switch", "True")
    r = _get(active_client, "tor.kill_switch")
    assert r.status_code == 200
    assert r.json() == {"key": "tor.kill_switch", "value": "true"}


def test_get_missing_key_returns_null(active_client):
    r = _get(active_client, "totally.absent")
    assert r.status_code == 200
    assert r.json() == {"key": "totally.absent", "value": None}


# ---------------------------------------------------------------------------
# Library-level smoke (no HTTP)
# ---------------------------------------------------------------------------


def test_validators_for_key_unknown_raises_sentinel(db):
    with pytest.raises(UnknownSettingError):
        validators_for_key("nope.nope", db)


def test_put_setting_unknown_raises_sentinel(db):
    with pytest.raises(UnknownSettingError):
        put_setting(db, "nope.nope", "x")
    # UnknownSettingError is a ValueError subclass — B3 contract intact.
    with pytest.raises(ValueError):
        put_setting(db, "nope.nope", "x")


def test_get_setting_default_seeded(db):
    # B2 seeds defaults at init; B4 leaves that contract intact.
    assert get_setting(db, "tor.proxy") == "socks5h://127.0.0.1:9050"
    assert get_setting(db, "tor.kill_switch") == "true"


def test_setting_validators_table_includes_required_keys():
    required = {
        "tor.proxy",
        "tor.kill_switch",
        "crawl.pacing",
        "browser.path",
        "browser.launch_mode",
        "embedding.model",
        "embedding.auto_start",
        "graph.color",
        "graph.edges",
    }
    assert required <= SETTING_VALIDATORS.keys()
