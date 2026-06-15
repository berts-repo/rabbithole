"""Phase B7e — fingerprint clusters + insert_response_headers helper."""
from __future__ import annotations

import csv as csv_module
import io
from pathlib import Path

import pytest

from backend.db import fingerprints as fingerprints_db
from backend.db import page_versions as versions_db
from backend.db import pages as pages_db
from backend.db import resources as resources_db
from backend.db.core import CrawlDB


def _insert_node(
    db: CrawlDB,
    url: str,
    *,
    title: str | None = None,
    stub: bool = False,
    category: str | None = None,
) -> int:
    """Create a resource + page version → the **page_version_id**.

    Headers key off the page version now (not a node), so the returned id is
    what ``insert_response_headers`` / ``_raw_insert_header`` write against.
    ``stub=True`` leaves the resource ``known`` (so clustering excludes it)
    while still giving it a real version row for a valid header FK target.
    """
    host = url.split("/")[2] if "//" in url else url
    when = "2026-05-14T00:00:00+00:00"
    if not stub:
        rid, vid = versions_db.record_fetch(
            db,
            url=url,
            host=host,
            status_code=200,
            title=title,
            body_text=None,
            body_text_clean=None,
            response_headers={},
            when=when,
        )
        if category is not None:
            pages_db.set_category(db, rid, category)
        return vid
    rid = resources_db.upsert_resource(db, url, host, state="known", when=when)
    with db.transaction(immediate=True) as c:
        page_id = pages_db.ensure_page(db, rid, now=when)
        cur = c.execute(
            "INSERT INTO page_versions(page_id, fetched_at, http_status, title) "
            "VALUES (?, ?, 200, ?)",
            (page_id, when, title),
        )
        vid = int(cur.lastrowid)
        c.execute(
            "UPDATE pages SET current_version_id=? WHERE id=?", (vid, page_id)
        )
    return vid


def _raw_insert_header(db: CrawlDB, version_id: int, key: str, value: str) -> None:
    """Bypass the helper so we can simulate legacy/bad rows."""
    with db.transaction(immediate=True) as c:
        c.execute(
            "INSERT OR REPLACE INTO response_headers(page_version_id, key, value) "
            "VALUES (?, ?, ?)",
            (version_id, key, value),
        )


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "b7e.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


# ---------------------------------------------------------------------------
# insert_response_headers (helper)
# ---------------------------------------------------------------------------


def test_insert_dropping_invalid_header_name(active_db):
    nid = _insert_node(active_db, "http://a.onion/")
    written = fingerprints_db.insert_response_headers(
        active_db,
        nid,
        {"Server": "nginx", "Bad Header": "drop", "Cookie": "ok"},
    )
    # "Bad Header" has a space → invalid token → dropped. The valid two persist.
    assert written == 2
    with active_db._lock:  # noqa: SLF001
        rows = active_db._conn.execute(
            "SELECT key FROM response_headers WHERE page_version_id = ?", (nid,)
        ).fetchall()
    keys = {r["key"] for r in rows}
    assert keys == {"Server", "Cookie"}


def test_insert_truncates_oversize_value(active_db):
    nid = _insert_node(active_db, "http://a.onion/")
    big = "x" * (fingerprints_db.HEADER_VALUE_MAX + 1024)
    fingerprints_db.insert_response_headers(active_db, nid, {"X-Big": big})
    with active_db._lock:  # noqa: SLF001
        row = active_db._conn.execute(
            "SELECT value FROM response_headers WHERE page_version_id = ?", (nid,)
        ).fetchone()
    assert len(row["value"]) == fingerprints_db.HEADER_VALUE_MAX


def test_insert_empty_clears_existing(active_db):
    nid = _insert_node(active_db, "http://a.onion/")
    fingerprints_db.insert_response_headers(active_db, nid, {"Server": "nginx"})
    fingerprints_db.insert_response_headers(active_db, nid, {})
    with active_db._lock:  # noqa: SLF001
        rows = active_db._conn.execute(
            "SELECT * FROM response_headers WHERE page_version_id = ?", (nid,)
        ).fetchall()
    assert rows == []


def test_validate_header_name():
    assert fingerprints_db.validate_header_name("Server") is True
    assert fingerprints_db.validate_header_name("X-Powered-By") is True
    assert fingerprints_db.validate_header_name("Bad Header") is False
    assert fingerprints_db.validate_header_name("\x01evil") is False
    assert fingerprints_db.validate_header_name("") is False


# ---------------------------------------------------------------------------
# list_clusters — IDF, thresholds, filters
# ---------------------------------------------------------------------------


def test_idf_ranks_rare_first(auth_client, active_db):
    """A header value shared by 2 of 5 sites has higher IDF than one shared
    by 4 of 5. The rare cluster should sort first."""
    # 5 crawled nodes. 2 share a rare Server value; 4 share a common one.
    nodes = [
        _insert_node(active_db, f"http://node-{i}.onion/") for i in range(5)
    ]
    fingerprints_db.insert_response_headers(
        active_db, nodes[0], {"Server": "rare-stack", "Common": "v1"}
    )
    fingerprints_db.insert_response_headers(
        active_db, nodes[1], {"Server": "rare-stack", "Common": "v1"}
    )
    fingerprints_db.insert_response_headers(
        active_db, nodes[2], {"Common": "v1"}
    )
    fingerprints_db.insert_response_headers(
        active_db, nodes[3], {"Common": "v1"}
    )
    fingerprints_db.insert_response_headers(
        active_db, nodes[4], {"Common": "other"}
    )

    r = auth_client.get("/api/fingerprints?min_sites=2")
    assert r.status_code == 200
    clusters = r.json()["clusters"]
    # The rare cluster must precede the common one.
    rare = next(c for c in clusters if c["value"] == "rare-stack")
    common = next(c for c in clusters if c["value"] == "v1")
    assert clusters.index(rare) < clusters.index(common)
    assert rare["sites"] == 2
    assert common["sites"] == 4
    assert rare["idf"] > common["idf"]


def test_min_sites_threshold(auth_client, active_db):
    a = _insert_node(active_db, "http://a.onion/")
    b = _insert_node(active_db, "http://b.onion/")
    c = _insert_node(active_db, "http://c.onion/")
    fingerprints_db.insert_response_headers(active_db, a, {"X-Only-One": "lone"})
    fingerprints_db.insert_response_headers(active_db, b, {"Server": "nginx"})
    fingerprints_db.insert_response_headers(active_db, c, {"Server": "nginx"})

    r2 = auth_client.get("/api/fingerprints?min_sites=2").json()["clusters"]
    keys2 = {c["key"] for c in r2}
    assert "Server" in keys2
    assert "X-Only-One" not in keys2

    r3 = auth_client.get("/api/fingerprints?min_sites=3").json()["clusters"]
    assert r3 == []


def test_ephemeral_headers_excluded(auth_client, active_db):
    a = _insert_node(active_db, "http://a.onion/")
    b = _insert_node(active_db, "http://b.onion/")
    fingerprints_db.insert_response_headers(
        active_db, a, {"Date": "2026-05-14", "Set-Cookie": "session=x"}
    )
    fingerprints_db.insert_response_headers(
        active_db, b, {"Date": "2026-05-14", "Set-Cookie": "session=x"}
    )
    clusters = auth_client.get("/api/fingerprints?min_sites=2").json()["clusters"]
    assert clusters == []


def test_invalid_header_name_excluded_at_storage(active_db):
    """A row written via raw SQL with a bad key is dropped from list_clusters."""
    a = _insert_node(active_db, "http://a.onion/")
    b = _insert_node(active_db, "http://b.onion/")
    _raw_insert_header(active_db, a, "Bad Key", "v")
    _raw_insert_header(active_db, b, "Bad Key", "v")
    clusters = fingerprints_db.list_clusters(active_db, min_sites=2)
    assert all(c["key"] != "Bad Key" for c in clusters)


def test_graph_filter_excludes_nodes(auth_client, active_db):
    """Adding a graph_filters term that matches a node removes it from cluster counts."""
    a = _insert_node(active_db, "http://hidden-noise.onion/")
    b = _insert_node(active_db, "http://b.onion/")
    c = _insert_node(active_db, "http://c.onion/")
    for nid in (a, b, c):
        fingerprints_db.insert_response_headers(
            active_db, nid, {"X-Cluster": "shared"}
        )

    # 3 sites share the header → cluster present at min_sites=3.
    before = auth_client.get("/api/fingerprints?min_sites=3").json()["clusters"]
    assert any(c["value"] == "shared" and c["sites"] == 3 for c in before)

    # Hide node `a` via the Hidden sub-tab.
    auth_client.post("/api/graph-filters", json={"term": "hidden-noise"})

    after = auth_client.get("/api/fingerprints?min_sites=3").json()["clusters"]
    assert all(c["value"] != "shared" for c in after)
    after2 = auth_client.get("/api/fingerprints?min_sites=2").json()["clusters"]
    cluster = next(c for c in after2 if c["value"] == "shared")
    assert cluster["sites"] == 2


def test_clusters_exclude_stubs(active_db):
    crawled = _insert_node(active_db, "http://a.onion/")
    stub = _insert_node(active_db, "http://b.onion/", stub=True)
    fingerprints_db.insert_response_headers(
        active_db, crawled, {"Server": "nginx"}
    )
    # Stub has no headers normally — but write one via raw SQL to make the
    # exclusion explicit.
    _raw_insert_header(active_db, stub, "Server", "nginx")
    clusters = fingerprints_db.list_clusters(active_db, min_sites=2)
    assert all(c["value"] != "nginx" for c in clusters)


# ---------------------------------------------------------------------------
# Members + CSV
# ---------------------------------------------------------------------------


def test_members_capped_at_500(active_db):
    nodes = []
    for i in range(510):
        nid = _insert_node(active_db, f"http://node-{i}.onion/")
        fingerprints_db.insert_response_headers(
            active_db, nid, {"X-Tag": "shared"}
        )
        nodes.append(nid)
    members = fingerprints_db.list_cluster_members(
        active_db, key="X-Tag", value="shared"
    )
    assert len(members) == 500


def test_members_excludes_stubs(auth_client, active_db):
    crawled = _insert_node(active_db, "http://crawled.onion/")
    stub = _insert_node(active_db, "http://stub.onion/", stub=True)
    fingerprints_db.insert_response_headers(
        active_db, crawled, {"Server": "nginx"}
    )
    _raw_insert_header(active_db, stub, "Server", "nginx")

    members = auth_client.get(
        "/api/fingerprints/members?key=Server&value=nginx"
    ).json()["members"]
    urls = {m["url"] for m in members}
    assert "http://crawled.onion/" in urls
    assert "http://stub.onion/" not in urls


def test_members_missing_params_400(auth_client, active_db):
    r = auth_client.get("/api/fingerprints/members")
    assert r.status_code == 400
    assert r.json()["error"] == "missing_key_value"


def test_export_csv_shape(auth_client, active_db):
    a = _insert_node(active_db, "http://a.onion/")
    b = _insert_node(active_db, "http://b.onion/")
    fingerprints_db.insert_response_headers(active_db, a, {"Server": "nginx"})
    fingerprints_db.insert_response_headers(active_db, b, {"Server": "nginx"})
    r = auth_client.get("/api/fingerprints/export.csv?min_sites=2")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    rows = list(csv_module.reader(io.StringIO(r.text)))
    assert rows[0] == ["header_key", "header_value", "sites", "idf"]
    assert any(row[0] == "Server" and row[1] == "nginx" for row in rows[1:])


def test_export_csv_formula_injection_guarded(active_db):
    a = _insert_node(active_db, "http://a.onion/")
    b = _insert_node(active_db, "http://b.onion/")
    fingerprints_db.insert_response_headers(
        active_db, a, {"X-Server": "=DANGER"}
    )
    fingerprints_db.insert_response_headers(
        active_db, b, {"X-Server": "=DANGER"}
    )
    body = fingerprints_db.export_clusters_csv(active_db, min_sites=2)
    rows = list(csv_module.reader(io.StringIO(body)))
    # `=` prefix must be escaped with a single quote.
    assert any(row[1] == "'=DANGER" for row in rows[1:])


def test_export_csv_bad_min_sites_400(auth_client, active_db):
    r = auth_client.get("/api/fingerprints/export.csv?min_sites=0")
    assert r.status_code == 400
    assert r.json()["error"] == "bad_min_sites"
