"""Phase B8 — harvest-search SSE.

Probe creates zero DB rows. Stream emits the documented event types.
Bounded GET rejects non-html responses.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.db import page_versions as versions_db
from backend.db import search_engines as search_engines_db
from backend.db.core import CrawlDB
from backend.db.settings import put_setting


def _host(url: str) -> str:
    return url.split("//", 1)[1].split("/", 1)[0]


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "b8_harvest.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


def _row_count(db: CrawlDB, table: str) -> int:
    return int(
        db._conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
    )


# --- query validation -----------------------------------------------------


def test_missing_query_400(auth_client, active_db):
    r = auth_client.get("/api/harvest/search")
    assert r.status_code == 400
    assert r.json()["error"] == "missing_query"


def test_query_too_long_400(auth_client, active_db):
    r = auth_client.get(
        "/api/harvest/search", params={"q": "x" * 300}
    )
    assert r.status_code == 400


def test_no_engines_emits_all_done_immediately(auth_client, active_db):
    r = auth_client.get("/api/harvest/search", params={"q": "test"})
    assert r.status_code == 200
    assert "no_engines" in r.text
    assert "all_done" in r.text


# --- substitution helper --------------------------------------------------


def test_substitute_query_uses_placeholder():
    from backend.routes.harvest_search import _substitute_query

    out = _substitute_query("http://x.onion/?q={q}", "hello world")
    assert out == "http://x.onion/?q=hello+world"


def test_substitute_query_falls_back_to_query_string():
    from backend.routes.harvest_search import _substitute_query

    out = _substitute_query("http://x.onion/search", "foo")
    assert out == "http://x.onion/search?q=foo"
    out2 = _substitute_query("http://x.onion/?lang=en", "foo")
    assert out2 == "http://x.onion/?lang=en&q=foo"


def test_extract_result_links_unwraps_redirects_and_text():
    from backend.routes.harvest_search import _extract_result_links

    engine_url = "http://" + ("a" * 56) + ".onion/search/?q=aliens"
    t1 = "http://" + ("b" * 56) + ".onion/"
    t2 = "http://" + ("c" * 56) + ".onion/page"
    t3 = "http://" + ("d" * 56) + ".onion/"
    from urllib.parse import quote_plus

    html = (
        "<html><body>"
        # 1. redirect-wrapped result (Ahmia style) — should unwrap to t1
        f'<a href="/search/redirect?redirect_url={quote_plus(t1)}">Site One</a>'
        # 2. direct external onion link → t2
        f'<a href="{t2}">Site Two</a>'
        # 3. self-link to the engine itself → dropped as chrome
        f'<a href="http://{"a" * 56}.onion/about">About</a>'
        # 4. bare onion printed in text → t3
        f"<p>Also see {t3} for more</p>"
        "</body></html>"
    ).encode("utf-8")

    links = _extract_result_links(html, engine_url)
    urls = [u for u, _ in links]
    assert t1 in urls  # redirect unwrapped to the real target
    assert t2 in urls  # direct external link
    assert t3 in urls  # scraped from page text
    # The engine's own onion is never a result.
    assert all(not u.startswith(f"http://{'a' * 56}.onion") for u in urls)
    # Anchor text is carried for href links, absent for text-scraped ones.
    by_url = dict(links)
    assert by_url[t1] == "Site One"
    assert by_url[t3] is None


def test_extract_result_links_dedupes_href_and_text():
    from backend.routes.harvest_search import _extract_result_links

    engine_url = "http://" + ("a" * 56) + ".onion/?q=x"
    target = "http://" + ("b" * 56) + ".onion/"
    html = (
        f'<html><body><a href="{target}">Hit</a>'
        f"<p>{target}</p></body></html>"
    ).encode("utf-8")
    links = _extract_result_links(html, engine_url)
    assert [u for u, _ in links] == [target]


def test_search_form_hidden_fields_extracts_token():
    from backend.routes.harvest_search import _search_form_hidden_fields

    # Ahmia-style homepage: a search form carrying a per-page hidden token.
    body = (
        "<html><body>"
        '<form action="/search/">'
        '<input id="id_q" type="search" name="q">'
        '<input type="hidden" name="a6be55" value="c7cd44">'
        "</form>"
        # A non-search form's hidden inputs must not be harvested.
        '<form action="/subscribe"><input type="hidden" name="csrf" value="x">'
        '<input type="submit"></form>'
        "</body></html>"
    ).encode("utf-8")
    assert _search_form_hidden_fields(body) == {"a6be55": "c7cd44"}
    # A page with no search form (e.g. a results page) primes nothing.
    assert _search_form_hidden_fields(b"<html><body><p>hi</p></body></html>") == {}


def test_append_params_merges_query():
    from backend.routes.harvest_search import _append_params

    out = _append_params("http://x.onion/search/?q=aliens", {"tok": "abc"})
    assert out == "http://x.onion/search/?q=aliens&tok=abc"


def test_fetch_engine_links_primes_bot_gated_form(monkeypatch):
    """An engine whose bare query GET bounces (no links) is retried with the
    homepage form's hidden token, and that primed query yields the results."""
    import asyncio

    from backend.routes import harvest_search as hs

    engine_url = "http://" + ("a" * 56) + ".onion/search/?q={q}"
    query_url = "http://" + ("a" * 56) + ".onion/search/?q=aliens"
    homepage = "http://" + ("a" * 56) + ".onion/"
    primed_url = query_url + "&tok=secret"
    result_onion = "http://" + ("b" * 56) + ".onion/"

    homepage_html = (
        '<html><body><form action="/search/">'
        '<input type="search" name="q">'
        '<input type="hidden" name="tok" value="secret">'
        "</form></body></html>"
    ).encode("utf-8")
    results_html = (
        f'<html><body><a href="{result_onion}">Hit</a></body></html>'
    ).encode("utf-8")
    pages = {
        query_url: b"<html><body><p>no results</p></body></html>",  # bot-gate
        homepage: homepage_html,
        primed_url: results_html,
    }
    fetched: list[str] = []

    async def _fake_bounded_get(target_url, *, tor_proxy, i2p_proxy):
        fetched.append(target_url)
        return 200, "text/html", pages[target_url]

    monkeypatch.setattr(hs, "_bounded_get", _fake_bounded_get)
    links = asyncio.run(
        hs._fetch_engine_links(engine_url, "aliens", tor_proxy="p", i2p_proxy="i")
    )

    assert [u for u, _ in links] == [result_onion]
    # The bare query was tried first, then the homepage was primed, then the
    # token-bearing query produced the hit.
    assert fetched == [query_url, homepage, primed_url]


def test_fetch_engine_links_no_prime_when_direct_yields_results(monkeypatch):
    """A naive engine that answers the first GET is never primed — no second
    fetch of its homepage."""
    import asyncio

    from backend.routes import harvest_search as hs

    engine_url = "http://" + ("a" * 56) + ".onion/search?q={q}"
    result_onion = "http://" + ("b" * 56) + ".onion/"
    fetched: list[str] = []

    async def _fake_bounded_get(target_url, *, tor_proxy, i2p_proxy):
        fetched.append(target_url)
        html = f'<html><body><a href="{result_onion}">Hit</a></body></html>'
        return 200, "text/html", html.encode("utf-8")

    monkeypatch.setattr(hs, "_bounded_get", _fake_bounded_get)
    links = asyncio.run(hs._fetch_engine_links(engine_url, "aliens", tor_proxy="p", i2p_proxy="i"))

    assert [u for u, _ in links] == [result_onion]
    assert fetched == ["http://" + ("a" * 56) + ".onion/search?q=aliens"]


def test_target_from_link_prefers_embedded_onion():
    from backend.routes.harvest_search import _target_from_link

    onion = "http://" + ("b" * 56) + ".onion/"
    wrapper = f"http://{'a' * 56}.onion/r?url={onion}"
    assert _target_from_link(wrapper) == onion
    assert _target_from_link(onion) == onion
    assert _target_from_link("http://example.com/") is None


def test_parse_engine_ids():
    from backend.routes.harvest_search import _parse_engine_ids

    assert _parse_engine_ids("") is None
    assert _parse_engine_ids("   ") is None
    assert _parse_engine_ids("3") == {3}
    assert _parse_engine_ids("3, 7 ,9") == {3, 7, 9}
    # Garbage tokens are dropped, not fatal.
    assert _parse_engine_ids("3,foo,,7") == {3, 7}
    assert _parse_engine_ids("foo") == set()


# --- end-to-end with stubbed _bounded_get ---------------------------------


def test_probe_creates_zero_db_rows(
    auth_client, active_db, monkeypatch
):
    """Engine query + probe paths must never write to nodes/crawls."""
    # Seed an engine + enable it.
    eid = search_engines_db.create_engine(
        active_db,
        label="StubEngine",
        url="http://" + ("a" * 56) + ".onion/?q={q}",
    )
    put_setting(active_db, f"search.engine.{eid}.enabled", True)

    # Engine result page links to two onion URLs; one will be "discovered".
    new_onion_a = "http://" + ("b" * 56) + ".onion/"
    new_onion_b = "http://" + ("c" * 56) + ".onion/"
    engine_html = (
        f'<html><body><a href="{new_onion_a}">A</a>'
        f'<a href="{new_onion_b}">B</a></body></html>'
    ).encode("utf-8")
    probe_a_html = b"<html><head><title>Probe A</title><meta name='description' content='desc A'></head></html>"
    probe_b_html = b"<html><head><title>Probe B</title></head></html>"

    pages: dict[str, bytes] = {
        f"http://{'a' * 56}.onion/?q=test": engine_html,
        new_onion_a: probe_a_html,
        new_onion_b: probe_b_html,
    }

    async def _fake_bounded_get(target_url, *, tor_proxy, i2p_proxy):
        body = pages.get(target_url)
        if body is None:
            return None
        return 200, "text/html", body

    monkeypatch.setattr(
        "backend.routes.harvest_search._bounded_get",
        _fake_bounded_get,
    )

    resources_before = _row_count(active_db, "resources")
    crawls_before = _row_count(active_db, "crawls")
    page_versions_before = _row_count(active_db, "page_versions")

    r = auth_client.get("/api/harvest/search", params={"q": "test"})
    assert r.status_code == 200
    body = r.text
    # SSE event types arrived.
    assert '"type": "status"' in body or '"type":"status"' in body
    assert '"type": "done"' in body or '"type":"done"' in body
    assert '"type": "all_done"' in body or '"type":"all_done"' in body
    # Probe events with title from the probe HTML in memory only.
    assert "Probe A" in body
    assert "desc A" in body

    # Critical invariant: zero persistence.
    assert _row_count(active_db, "resources") == resources_before
    assert _row_count(active_db, "crawls") == crawls_before
    assert _row_count(active_db, "page_versions") == page_versions_before


def test_passive_mode_skips_probe_stage(
    auth_client, active_db, monkeypatch
):
    """When ``search.passive_mode=true`` the SSE still streams engine URL
    results, ``done``, and ``all_done`` events, but emits no ``probe`` events
    and never contacts the discovered onions. Privacy opt-out: the app stays
    on the configured search engines only."""
    eid = search_engines_db.create_engine(
        active_db,
        label="StubEngine",
        url="http://" + ("a" * 56) + ".onion/?q={q}",
    )
    put_setting(active_db, f"search.engine.{eid}.enabled", True)
    put_setting(active_db, "search.passive_mode", True)

    new_onion = "http://" + ("b" * 56) + ".onion/"
    engine_html = (
        f'<html><body><a href="{new_onion}">B</a></body></html>'
    ).encode("utf-8")
    engine_url = f"http://{'a' * 56}.onion/?q=test"

    contacted_urls: list[str] = []

    async def _fake_bounded_get(target_url, *, tor_proxy, i2p_proxy):
        contacted_urls.append(target_url)
        if target_url == engine_url:
            return 200, "text/html", engine_html
        # Probe stage must never run — fail loudly if it does.
        raise AssertionError(
            f"passive mode probed {target_url}; only the engine URL "
            f"({engine_url}) should have been fetched"
        )

    monkeypatch.setattr(
        "backend.routes.harvest_search._bounded_get",
        _fake_bounded_get,
    )

    r = auth_client.get("/api/harvest/search", params={"q": "test"})
    assert r.status_code == 200
    body = r.text

    # Engine URL was fetched; nothing else.
    assert contacted_urls == [engine_url]

    # Standard SSE events still arrive.
    assert '"type": "done"' in body or '"type":"done"' in body
    assert '"type": "all_done"' in body or '"type":"all_done"' in body
    # The discovered URL is still reported as a result row.
    assert new_onion in body
    # No probe events: that is the whole point of passive mode.
    assert '"type": "probe"' not in body
    assert '"type":"probe"' not in body


def test_non_html_content_type_aborts_probe(monkeypatch, active_db):
    """``_bounded_get`` raises _FetchError('unreadable') on non-html."""
    import asyncio

    from backend.routes.harvest_search import _bounded_get, _FetchError

    # Patch make_tor_session to a fake that returns non-html.
    class _FakeResp:
        def __init__(self) -> None:
            self.status = 200
            self.headers = {"Content-Type": "application/octet-stream"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        def get(self, url, *, allow_redirects):
            return _FakeResp()

    def _factory(host, *, proxy, timeout):
        return _FakeSession()

    monkeypatch.setattr(
        "backend.routes.harvest_search.make_tor_session", _factory
    )
    with pytest.raises(_FetchError) as exc:
        asyncio.run(
            _bounded_get(
                "http://" + ("a" * 56) + ".onion/",
                tor_proxy="socks5h://127.0.0.1:9050",
                i2p_proxy="socks5h://127.0.0.1:4447",
            )
        )
    assert exc.value.reason == "unreadable"


# --- crawled-result enrichment --------------------------------------------


def test_crawled_result_carries_node_metadata(
    auth_client, active_db, monkeypatch
):
    """A discovered URL that is already crawled streams with the node id +
    title the result row renders — not a bare ``crawled: true`` flag."""
    eid = search_engines_db.create_engine(
        active_db,
        label="StubEngine",
        url="http://" + ("a" * 56) + ".onion/?q={q}",
    )
    put_setting(active_db, f"search.engine.{eid}.enabled", True)

    crawled_url = "http://" + ("b" * 56) + ".onion/"
    rid, _vid = versions_db.record_fetch(
        active_db,
        url=crawled_url,
        host=_host(crawled_url),
        status_code=200,
        title="Known Market",
        body_text=None,
        body_text_clean=None,
        response_headers={},
        when="2026-05-12T00:00:00+00:00",
    )

    engine_html = (
        f'<html><body><a href="{crawled_url}">B</a></body></html>'
    ).encode("utf-8")
    pages: dict[str, bytes] = {
        f"http://{'a' * 56}.onion/?q=test": engine_html,
    }

    async def _fake_bounded_get(target_url, *, tor_proxy, i2p_proxy):
        body = pages.get(target_url)
        if body is None:
            from backend.routes.harvest_search import _FetchError

            raise _FetchError("connection")
        return 200, "text/html", body

    monkeypatch.setattr(
        "backend.routes.harvest_search._bounded_get", _fake_bounded_get
    )

    r = auth_client.get("/api/harvest/search", params={"q": "test"})
    assert r.status_code == 200
    # Find the URL-result line for the crawled onion and parse it.
    payloads = _result_payloads(r.text)
    crawled_rows = [
        p for p in payloads if p.get("url") == crawled_url and "crawled" in p
    ]
    assert len(crawled_rows) == 1
    row = crawled_rows[0]
    assert row["crawled"] is True
    assert row["node_id"] == rid
    assert row["title"] == "Known Market"
    assert "last_seen" in row
    # Crawled URLs are not probed (they're already known).
    assert '"type": "probe"' not in r.text


# --- per-session engine selection -----------------------------------------


def test_engines_param_filters_sources(auth_client, active_db, monkeypatch):
    """``engines=<id>`` narrows the search to that engine; a deselected
    enabled engine is never contacted."""
    keep = search_engines_db.create_engine(
        active_db, label="Keep", url="http://" + ("a" * 56) + ".onion/?q={q}"
    )
    drop = search_engines_db.create_engine(
        active_db, label="Drop", url="http://" + ("d" * 56) + ".onion/?q={q}"
    )
    put_setting(active_db, f"search.engine.{keep}.enabled", True)
    put_setting(active_db, f"search.engine.{drop}.enabled", True)

    keep_url = f"http://{'a' * 56}.onion/?q=test"
    drop_url = f"http://{'d' * 56}.onion/?q=test"
    contacted: list[str] = []

    async def _fake_bounded_get(target_url, *, tor_proxy, i2p_proxy):
        contacted.append(target_url)
        return 200, "text/html", b"<html><body></body></html>"

    monkeypatch.setattr(
        "backend.routes.harvest_search._bounded_get", _fake_bounded_get
    )

    r = auth_client.get(
        "/api/harvest/search", params={"q": "test", "engines": str(keep)}
    )
    assert r.status_code == 200
    assert keep_url in contacted
    assert drop_url not in contacted


def test_engines_param_all_filtered_out_emits_no_engines(
    auth_client, active_db, monkeypatch
):
    """An ``engines`` set that intersects to nothing (stale/bogus ids) lands on
    the same no-engines path as a project with none configured."""
    eid = search_engines_db.create_engine(
        active_db, label="Keep", url="http://" + ("a" * 56) + ".onion/?q={q}"
    )
    put_setting(active_db, f"search.engine.{eid}.enabled", True)

    async def _fake_bounded_get(target_url, *, tor_proxy, i2p_proxy):
        raise AssertionError("no engine should be queried")

    monkeypatch.setattr(
        "backend.routes.harvest_search._bounded_get", _fake_bounded_get
    )

    r = auth_client.get(
        "/api/harvest/search",
        params={"q": "test", "engines": str(eid + 999)},
    )
    assert r.status_code == 200
    assert "no_engines" in r.text


# --- error reason propagation ---------------------------------------------


def test_error_event_carries_reason(auth_client, active_db, monkeypatch):
    """A failed engine fetch surfaces its coarse reason so the UI can pick the
    right "all sources failed" empty state."""
    eid = search_engines_db.create_engine(
        active_db, label="StubEngine", url="http://" + ("a" * 56) + ".onion/?q={q}"
    )
    put_setting(active_db, f"search.engine.{eid}.enabled", True)

    async def _fake_bounded_get(target_url, *, tor_proxy, i2p_proxy):
        from backend.routes.harvest_search import _FetchError

        raise _FetchError("timeout")

    monkeypatch.setattr(
        "backend.routes.harvest_search._bounded_get", _fake_bounded_get
    )

    r = auth_client.get("/api/harvest/search", params={"q": "test"})
    assert r.status_code == 200
    errors = [p for p in _result_payloads(r.text) if p.get("type") == "error"]
    assert len(errors) == 1
    assert errors[0]["reason"] == "timeout"


def _result_payloads(body: str) -> list[dict]:
    """Parse the ``data: {...}`` JSON lines of an SSE body into dicts."""
    import json

    out: list[dict] = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        try:
            out.append(json.loads(line[len("data:"):].strip()))
        except json.JSONDecodeError:
            continue
    return out
