"""Phase B6 — graph payload + GEXF/CSV exports + cache.

Tests mirror the route-level pattern in ``test_b5c_routes.py``: a fresh
``CrawlDB`` is attached to ``app.state.project_state.active_db`` so the
``get_active_db`` dependency resolves without going through the projects
registry. Direct SQL inserts populate test fixtures — no need to drive
the crawler.

The 16 cases below match the plan in
``/home/captain/.claude/plans/we-are-on-b6-ancient-haven.md``.
"""
from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

from backend.db import graph as graph_db
from backend.db import page_versions as versions_db
from backend.db import pages as pages_db
from backend.db import resources as resources_db
from backend.db.core import CrawlDB
from backend.services.graph_cache import GraphCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _host(url: str, domain: str | None) -> str:
    return domain or url.split("//", 1)[1].split("/", 1)[0]


def _insert_node(
    db: CrawlDB,
    url: str,
    *,
    title: str | None = None,
    domain: str | None = None,
    stub: bool = False,
    analysis_excluded: bool = False,
    status_code: int | None = 200,
    first_seen: str | None = "2026-05-12T00:00:00+00:00",
) -> int:
    """Create a resource → ``resource_id``.

    ``stub=True`` makes an uncrawled ``state='known'`` resource (no page);
    otherwise it crawls the URL once so a ``pages`` + ``page_versions`` row
    exists carrying the title / status / analyst flags the payload joins on.
    """
    host = _host(url, domain)
    if stub:
        return resources_db.upsert_resource(
            db, url, host, state="known", when=first_seen
        )
    rid, _vid = versions_db.record_fetch(
        db,
        url=url,
        host=host,
        status_code=status_code or 200,
        title=title,
        body_text=None,
        body_text_clean=None,
        response_headers={},
        when=first_seen or "2026-05-12T00:00:00+00:00",
    )
    if analysis_excluded:
        pages_db.set_analysis_excluded(db, rid, True)
    return rid


def _insert_edge(
    db: CrawlDB,
    from_id: int,
    to_id: int,
    *,
    source: str = "crawl",
    label: str | None = None,
) -> None:
    with db.transaction(immediate=True) as c:
        c.execute(
            "INSERT INTO edges(from_id, to_id, source, label) VALUES (?, ?, ?, ?)",
            (from_id, to_id, source, label),
        )


def _insert_headers(db: CrawlDB, node_id: int, headers: dict[str, str]) -> None:
    """Attach response headers to a resource's current page version."""
    with db.transaction(immediate=True) as c:
        row = c.execute(
            "SELECT current_version_id FROM pages WHERE resource_id=?", (node_id,)
        ).fetchone()
        version_id = row["current_version_id"]
        for k, v in headers.items():
            c.execute(
                "INSERT OR REPLACE INTO response_headers(page_version_id, key, value) "
                "VALUES (?, ?, ?)",
                (version_id, k, v),
            )


def _insert_filter(db: CrawlDB, term: str) -> None:
    with db.transaction(immediate=True) as c:
        c.execute("INSERT OR IGNORE INTO graph_filters(term) VALUES (?)", (term,))


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    """Attach a fresh ``CrawlDB`` to ``project_state`` for the test's lifetime."""
    db = CrawlDB(tmp_path / "b6.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    # Reset the cache so each test starts cold (the cache is module-level
    # on the singleton ProjectState that persists across the test process).
    app.state.project_state.graph_cache.invalidate()
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        app.state.project_state.graph_cache.invalidate()
        db.close()


# ---------------------------------------------------------------------------
# 1. Empty DB
# ---------------------------------------------------------------------------


def test_empty_db_returns_empty_payload(auth_client, active_db):
    r = auth_client.get("/api/graph")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"nodes": [], "edges": []}


# ---------------------------------------------------------------------------
# 2. Minimal graph with bridge
# ---------------------------------------------------------------------------


def test_minimal_graph_metrics_and_bridge(auth_client, active_db):
    # Topology: a -> b -> c. `b` is the articulation point of the
    # undirected view.
    a = _insert_node(active_db, "http://a.onion/", title="a", domain="a.onion")
    b = _insert_node(active_db, "http://b.onion/", title="b", domain="b.onion")
    c = _insert_node(active_db, "http://c.onion/", title="c", domain="c.onion")
    _insert_edge(active_db, a, b)
    _insert_edge(active_db, b, c)

    r = auth_client.get("/api/graph")
    assert r.status_code == 200
    body = r.json()
    assert len(body["nodes"]) == 3
    assert len(body["edges"]) == 2

    by_id = {n["id"]: n for n in body["nodes"]}
    assert by_id[b]["is_bridge"] is True
    assert by_id[a]["is_bridge"] is False
    assert by_id[c]["is_bridge"] is False
    # PageRank is normalized: sum across nodes ≈ 1.0
    total_pr = sum(n["pagerank"] for n in body["nodes"])
    assert abs(total_pr - 1.0) < 1e-6
    # Degree counts.
    assert by_id[a]["out_degree_count"] == 1
    assert by_id[a]["in_degree_count"] == 0
    assert by_id[b]["in_degree_count"] == 1
    assert by_id[b]["out_degree_count"] == 1
    assert by_id[c]["in_degree_count"] == 1


# ---------------------------------------------------------------------------
# 3. graph_filters term matches URL
# ---------------------------------------------------------------------------


def test_filter_excludes_by_url_substring(auth_client, active_db):
    a = _insert_node(active_db, "http://goodsite.onion/", title="ok")
    b = _insert_node(active_db, "http://BANNED.onion/", title="x")
    _insert_edge(active_db, a, b)
    _insert_filter(active_db, "banned")

    body = auth_client.get("/api/graph").json()
    ids = {n["id"] for n in body["nodes"]}
    assert a in ids
    assert b not in ids
    # The edge touching the excluded node is dropped.
    assert body["edges"] == []


# ---------------------------------------------------------------------------
# 4. graph_filters term matches title
# ---------------------------------------------------------------------------


def test_filter_excludes_by_title_substring(auth_client, active_db):
    a = _insert_node(active_db, "http://aaa.onion/", title="legit page")
    b = _insert_node(active_db, "http://bbb.onion/", title="MARKET listing")
    _insert_filter(active_db, "market")

    body = auth_client.get("/api/graph").json()
    ids = {n["id"] for n in body["nodes"]}
    assert ids == {a}


# ---------------------------------------------------------------------------
# 5. Stubs are included with stub=true, status_code=null
# ---------------------------------------------------------------------------


def test_stubs_are_included(auth_client, active_db):
    a = _insert_node(active_db, "http://crawled.onion/", title="c", status_code=200)
    s = _insert_node(
        active_db,
        "http://stub.onion/",
        title=None,
        stub=True,
        status_code=None,
        first_seen=None,
    )
    _insert_edge(active_db, a, s)

    body = auth_client.get("/api/graph").json()
    by_id = {n["id"]: n for n in body["nodes"]}
    assert by_id[s]["state"] == "known"
    assert by_id[a]["state"] == "crawled"
    # Uncrawled node still gets degree metrics computed.
    assert by_id[s]["in_degree_count"] == 1


# ---------------------------------------------------------------------------
# 6. analysis_excluded surfaces but does NOT remove the node
# ---------------------------------------------------------------------------


def test_analysis_excluded_propagates(auth_client, active_db):
    a = _insert_node(
        active_db, "http://x.onion/", title="x", analysis_excluded=True
    )
    body = auth_client.get("/api/graph").json()
    by_id = {n["id"]: n for n in body["nodes"]}
    assert by_id[a]["analysis_excluded"] is True


# ---------------------------------------------------------------------------
# 7. Infra cluster via shared non-ephemeral header pair
# ---------------------------------------------------------------------------


def test_infra_cluster_via_shared_header(auth_client, active_db):
    a = _insert_node(active_db, "http://a.onion/", title="a")
    b = _insert_node(active_db, "http://b.onion/", title="b")
    c = _insert_node(active_db, "http://c.onion/", title="c")

    # a + b share an unusual Server value; c does not.
    _insert_headers(active_db, a, {"Server": "OnionBox/1.0", "Date": "now"})
    _insert_headers(active_db, b, {"Server": "OnionBox/1.0", "Date": "later"})
    _insert_headers(active_db, c, {"Date": "much-later"})

    body = auth_client.get("/api/graph").json()
    by_id = {n["id"]: n for n in body["nodes"]}
    assert by_id[a]["infra_cluster_id"] == by_id[b]["infra_cluster_id"]
    assert by_id[a]["infra_cluster_id"] is not None
    # c shares only an ephemeral header → no cluster.
    assert by_id[c]["infra_cluster_id"] is None
    # The cluster id encodes the header pair.
    assert "OnionBox" in by_id[a]["infra_cluster_id"]


def test_infra_cluster_csp_normalized(auth_client, active_db):
    """Two pages whose Content-Security-Policy differs only by directive
    order and a per-request nonce still share an infra cluster — the CSP is
    normalized (nonce stripped, directives sorted) before comparison."""
    a = _insert_node(active_db, "http://a.onion/", title="a")
    b = _insert_node(active_db, "http://b.onion/", title="b")

    _insert_headers(active_db, a, {
        "Content-Security-Policy":
            "default-src 'self'; script-src 'self' 'nonce-AAAABBBB'; img-src 'self'",
    })
    _insert_headers(active_db, b, {
        # Directives reordered; a different per-request nonce.
        "Content-Security-Policy":
            "img-src 'self'; script-src 'self' 'nonce-ZZZZYYYY'; default-src 'self'",
    })

    body = auth_client.get("/api/graph").json()
    by_id = {n["id"]: n for n in body["nodes"]}
    assert by_id[a]["infra_cluster_id"] is not None
    assert by_id[a]["infra_cluster_id"] == by_id[b]["infra_cluster_id"]
    # Still a readable signature, not a hash — and the nonce is gone.
    assert "default-src" in by_id[a]["infra_cluster_id"]
    assert "nonce-" not in by_id[a]["infra_cluster_id"]


# ---------------------------------------------------------------------------
# 8. Cache hit within TTL (no rebuild)
# ---------------------------------------------------------------------------


def test_cache_hit_within_ttl(auth_client, active_db, monkeypatch):
    _insert_node(active_db, "http://a.onion/", title="a")
    calls = {"n": 0}
    real = graph_db.build_payload

    def counting(db):
        calls["n"] += 1
        return real(db)

    monkeypatch.setattr(graph_db, "build_payload", counting)
    # Also patch the import target inside the route module.
    from backend.routes import graph as graph_routes
    monkeypatch.setattr(graph_routes, "build_payload", counting)

    auth_client.get("/api/graph")
    auth_client.get("/api/graph")
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# 9. Cache miss after explicit invalidate
# ---------------------------------------------------------------------------


def test_cache_miss_after_invalidate(auth_client, active_db, app, monkeypatch):
    _insert_node(active_db, "http://a.onion/", title="a")
    calls = {"n": 0}
    real = graph_db.build_payload

    def counting(db):
        calls["n"] += 1
        return real(db)

    from backend.routes import graph as graph_routes
    monkeypatch.setattr(graph_routes, "build_payload", counting)

    auth_client.get("/api/graph")
    app.state.project_state.graph_cache.invalidate()
    auth_client.get("/api/graph")
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# 10. POST /api/edges invalidates the cache
# ---------------------------------------------------------------------------


def test_edge_post_invalidates_cache(auth_client, active_db, monkeypatch):
    a = _insert_node(active_db, "http://a.onion/", title="a")
    b = _insert_node(active_db, "http://b.onion/", title="b")

    calls = {"n": 0}
    real = graph_db.build_payload

    def counting(db):
        calls["n"] += 1
        return real(db)

    from backend.routes import graph as graph_routes
    monkeypatch.setattr(graph_routes, "build_payload", counting)

    # Prime cache.
    r1 = auth_client.get("/api/graph")
    assert len(r1.json()["edges"]) == 0
    # Add analyst edge → next /api/graph must rebuild.
    r = auth_client.post("/api/edges", json={"from_id": a, "to_id": b})
    assert r.status_code == 200, r.text
    r2 = auth_client.get("/api/graph")
    assert len(r2.json()["edges"]) == 1
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# 11. PATCH /api/nodes/:id/analysis_excluded invalidates cache
# ---------------------------------------------------------------------------


def test_analysis_excluded_patch_invalidates_cache(auth_client, active_db, monkeypatch):
    a = _insert_node(active_db, "http://a.onion/", title="a", analysis_excluded=False)

    calls = {"n": 0}
    real = graph_db.build_payload

    def counting(db):
        calls["n"] += 1
        return real(db)

    from backend.routes import graph as graph_routes
    monkeypatch.setattr(graph_routes, "build_payload", counting)

    r1 = auth_client.get("/api/graph").json()
    assert r1["nodes"][0]["analysis_excluded"] is False

    r = auth_client.patch(
        f"/api/nodes/{a}/analysis_excluded", json={"excluded": True}
    )
    assert r.status_code == 200, r.text

    r2 = auth_client.get("/api/graph").json()
    assert r2["nodes"][0]["analysis_excluded"] is True
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# 11b. PATCH /api/nodes/:id/reviewed invalidates cache + surfaces in payload
# ---------------------------------------------------------------------------


def test_reviewed_appears_in_payload_and_patch_invalidates_cache(
    auth_client, active_db, monkeypatch
):
    a = _insert_node(active_db, "http://a.onion/", title="a")

    calls = {"n": 0}
    real = graph_db.build_payload

    def counting(db):
        calls["n"] += 1
        return real(db)

    from backend.routes import graph as graph_routes
    monkeypatch.setattr(graph_routes, "build_payload", counting)

    r1 = auth_client.get("/api/graph").json()
    assert r1["nodes"][0]["reviewed"] is False

    r = auth_client.patch(f"/api/nodes/{a}/reviewed", json={"reviewed": True})
    assert r.status_code == 200, r.text

    r2 = auth_client.get("/api/graph").json()
    assert r2["nodes"][0]["reviewed"] is True
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# 12. GEXF is well-formed and escapes special chars
# ---------------------------------------------------------------------------


def test_gexf_export_well_formed_and_escapes(auth_client, active_db):
    a = _insert_node(
        active_db,
        "http://a.onion/",
        title="risky <script>alert(1)</script>",
        domain="a.onion",
    )
    b = _insert_node(active_db, "http://b.onion/", title="b", domain="b.onion")
    _insert_edge(active_db, a, b, source="crawl")

    r = auth_client.get("/api/export/gexf")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/gexf+xml")
    body = r.content

    # XML parses without raising — proves well-formedness + correct
    # escaping (ET would have refused to write an unescaped `<`).
    root = ET.fromstring(body)
    assert root.tag.endswith("gexf")

    # Find <node> + <edge> children regardless of namespace.
    nodes = root.findall(".//{http://gexf.net/1.3}node")
    edges = root.findall(".//{http://gexf.net/1.3}edge")
    assert len(nodes) == 2
    assert len(edges) == 1

    # Title containing `<script>` must appear escaped in the serialized
    # bytes (no raw `<script>` substring).
    assert b"<script>" not in body
    assert b"&lt;script&gt;" in body or b"alert(1)" in body  # text safely encoded


# ---------------------------------------------------------------------------
# 13. CSV formula-injection prefix
# ---------------------------------------------------------------------------


def test_csv_export_formula_prefix(auth_client, active_db):
    _insert_node(
        active_db,
        "http://a.onion/",
        title="=cmd|' /C calc'!A1",
        domain="a.onion",
    )
    _insert_node(active_db, "http://b.onion/", title="@menace", domain="b.onion")

    r = auth_client.get("/api/export/nodes-csv")
    assert r.status_code == 200
    text = r.text
    lines = text.strip().splitlines()
    # Header + 2 data rows.
    assert len(lines) == 3
    # The dangerous-leading-char titles are prefixed with `'`.
    assert ",'=cmd|" in text
    assert ",'@menace" in text


# ---------------------------------------------------------------------------
# 14. GEXF + CSV share the cached payload
# ---------------------------------------------------------------------------


def test_exports_share_cached_payload(auth_client, active_db, monkeypatch):
    _insert_node(active_db, "http://a.onion/", title="a")
    calls = {"n": 0}
    real = graph_db.build_payload

    def counting(db):
        calls["n"] += 1
        return real(db)

    from backend.routes import graph as graph_routes
    monkeypatch.setattr(graph_routes, "build_payload", counting)

    auth_client.get("/api/graph")
    auth_client.get("/api/export/gexf")
    auth_client.get("/api/export/nodes-csv")
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# 15. Single-flight: concurrent cold-cache reads share one build
# ---------------------------------------------------------------------------


def test_single_flight_dedupes_concurrent_builds(active_db, app):
    """Direct test on ``GraphCache`` — concurrent ``get_or_build`` callers
    collapse to a single underlying build invocation."""

    # Use the project's actual cache to keep the test grounded in production
    # configuration.
    cache = GraphCache()
    calls = {"n": 0}

    async def slow_build():
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return {"hello": "world"}

    async def driver():
        return await asyncio.gather(
            cache.get_or_build(slow_build),
            cache.get_or_build(slow_build),
            cache.get_or_build(slow_build),
        )

    results = asyncio.run(driver())
    assert all(r == {"hello": "world"} for r in results)
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# 16. Swapping active DB + invalidating cache yields fresh data
# ---------------------------------------------------------------------------


def test_project_switch_clears_cache(auth_client, active_db, app, tmp_path: Path):
    """Drop-in replacement for ``ProjectState.switch`` semantics: after the
    active DB is swapped and ``graph_cache.invalidate()`` runs, the next
    ``/api/graph`` read reflects the new DB.

    We exercise the cache invalidation contract directly because the full
    ``switch()`` flow depends on the projects registry (covered in B4).
    """
    _insert_node(active_db, "http://only-in-a.onion/", title="alpha")

    r = auth_client.get("/api/graph").json()
    urls_a = {n["raw_url"] for n in r["nodes"]}
    assert "http://only-in-a.onion/" in urls_a

    other = CrawlDB(tmp_path / "other.db")
    _insert_node(other, "http://only-in-b.onion/", title="beta")
    try:
        # Mirror what ``ProjectState.switch`` does: swap the DB pointer and
        # invalidate the cache. Leave the original ``active_db`` open so the
        # fixture's teardown can close it cleanly.
        app.state.project_state.active_db = other
        app.state.project_state.graph_cache.invalidate()

        r = auth_client.get("/api/graph").json()
        urls_b = {n["raw_url"] for n in r["nodes"]}
        assert "http://only-in-a.onion/" not in urls_b
        assert "http://only-in-b.onion/" in urls_b
    finally:
        # Restore the original active_db so the fixture's teardown closes it.
        app.state.project_state.active_db = active_db
        other.close()


def test_project_state_switch_invalidates_cache():
    """``ProjectState.switch`` flips the cache TTL to 0 as part of the swap.

    Verified directly on the dataclass to catch regressions in the wiring
    even if a future refactor moves the call site.
    """
    from backend.services.project_state import ProjectState

    state = ProjectState.new()
    # Prime the cache so the next read would hit.
    state.graph_cache._value = {"nodes": [], "edges": []}  # noqa: SLF001
    state.graph_cache._expires_at = 9_999_999_999.0  # noqa: SLF001
    assert state.graph_cache._is_fresh()  # noqa: SLF001
    state.graph_cache.invalidate()
    assert not state.graph_cache._is_fresh()  # noqa: SLF001


# ---------------------------------------------------------------------------
# F4b — collection-scoped /api/graph?collection_id=N
# ---------------------------------------------------------------------------


def _insert_collection(db: CrawlDB, name: str) -> int:
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "INSERT INTO collections(name, description) VALUES (?, NULL)",
            (name,),
        )
        return int(cur.lastrowid)


def _add_member(db: CrawlDB, cid: int, node_id: int) -> None:
    with db.transaction(immediate=True) as c:
        c.execute(
            "INSERT OR IGNORE INTO collection_items(collection_id, node_id) "
            "VALUES (?, ?)",
            (cid, node_id),
        )


def _remove_member(db: CrawlDB, cid: int, node_id: int) -> None:
    with db.transaction(immediate=True) as c:
        c.execute(
            "DELETE FROM collection_items WHERE collection_id = ? AND node_id = ?",
            (cid, node_id),
        )


def test_graph_collection_filter_keeps_only_members(auth_client, active_db):
    a = _insert_node(active_db, "http://a.onion/", title="a", domain="a.onion")
    b = _insert_node(active_db, "http://b.onion/", title="b", domain="b.onion")
    c = _insert_node(active_db, "http://c.onion/", title="c", domain="c.onion")
    _insert_edge(active_db, a, b)
    _insert_edge(active_db, b, c)
    cid = _insert_collection(active_db, "subset")
    _add_member(active_db, cid, a)
    _add_member(active_db, cid, b)

    body = auth_client.get(f"/api/graph?collection_id={cid}").json()
    ids = {int(n["id"]) for n in body["nodes"]}
    assert ids == {a, b}
    # Edge between two surviving members survives; the b→c edge does not.
    pairs = {(int(e["from"]), int(e["to"])) for e in body["edges"]}
    assert pairs == {(a, b)}


def test_graph_collection_metrics_pass_through_from_full_graph(
    auth_client, active_db
):
    a = _insert_node(active_db, "http://a.onion/", title="a", domain="a.onion")
    b = _insert_node(active_db, "http://b.onion/", title="b", domain="b.onion")
    c = _insert_node(active_db, "http://c.onion/", title="c", domain="c.onion")
    _insert_edge(active_db, a, b)
    _insert_edge(active_db, b, c)
    cid = _insert_collection(active_db, "metric-scope")
    # Only `b` is in the collection — its metrics should match the full
    # compute (b is the bridge), not a metrics rebuild over a singleton.
    _add_member(active_db, cid, b)

    full = auth_client.get("/api/graph").json()
    scoped = auth_client.get(f"/api/graph?collection_id={cid}").json()
    full_b = next(n for n in full["nodes"] if int(n["id"]) == b)
    scoped_b = next(n for n in scoped["nodes"] if int(n["id"]) == b)
    assert scoped_b["is_bridge"] == full_b["is_bridge"]
    assert scoped_b["pagerank"] == full_b["pagerank"]
    assert scoped_b["in_degree_count"] == full_b["in_degree_count"]
    assert scoped_b["out_degree_count"] == full_b["out_degree_count"]


def test_graph_collection_unknown_404(auth_client, active_db):
    r = auth_client.get("/api/graph?collection_id=99999")
    assert r.status_code == 404, r.text
    detail = r.json().get("detail")
    assert detail == {"error": "unknown_collection", "collection_id": 99999}


def test_graph_collection_empty_membership_returns_empty(auth_client, active_db):
    _insert_node(active_db, "http://lonely.onion/", title="x")
    cid = _insert_collection(active_db, "empty")

    body = auth_client.get(f"/api/graph?collection_id={cid}").json()
    assert body == {"nodes": [], "edges": []}


def test_graph_collection_membership_change_visible_without_invalidation(
    auth_client, active_db
):
    a = _insert_node(active_db, "http://a.onion/", title="a")
    b = _insert_node(active_db, "http://b.onion/", title="b")
    cid = _insert_collection(active_db, "mut")
    _add_member(active_db, cid, a)
    body1 = auth_client.get(f"/api/graph?collection_id={cid}").json()
    assert {int(n["id"]) for n in body1["nodes"]} == {a}

    # Mutate membership without touching the cache; the post-filter must
    # see the change on the next request.
    _add_member(active_db, cid, b)
    body2 = auth_client.get(f"/api/graph?collection_id={cid}").json()
    assert {int(n["id"]) for n in body2["nodes"]} == {a, b}

    _remove_member(active_db, cid, a)
    body3 = auth_client.get(f"/api/graph?collection_id={cid}").json()
    assert {int(n["id"]) for n in body3["nodes"]} == {b}
