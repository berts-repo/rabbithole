"""Phase B5c — CrawlRunner end-to-end behaviour.

Tests inject a fake session factory so no Tor / DNS / sockets are needed.
The fake produces canned ``ClientResponse``-shaped objects keyed by URL.

Coverage targets PLAN.md:301:

* redirect to non-onion blocked,
* 10 MB streaming cap enforced,
* non-allowlisted Content-Type → body discarded but headers persisted,
* stub→crawled promotion flips waiting analyses,
* kill-switch cancels in-flight fetch mid-stream,
* Aho-Corasick literal watchlist match → auto-flag,
* discovered links insert crawl edges.
"""
from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field

import pytest

from backend.crawler.runtime import CrawlRunner, _PACING_RANGES
from backend.db import crawl as crawl_db
from backend.db import jobs as jobs_db
from backend.db import watchlist as watchlist_db
from backend.db.core import CrawlDB
from backend.db.settings import put_setting
from backend.services.event_bus import EventBus


def _job_status(db: CrawlDB, job_id: int) -> str | None:
    """Live crawl status now lives on the linked ``jobs`` row, not ``crawls``."""
    with db._lock:
        row = db._conn.execute(
            "SELECT status FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
    return row["status"] if row is not None else None


SEED_HOST = "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad"
SEED_URL = f"http://{SEED_HOST}.onion/"
# 56 chars of base32 — a valid v3 onion host.
CHILD_HOST = "abacus" * 9 + "22"
CHILD_URL = f"http://{CHILD_HOST}.onion/page"


# ---------------------------------------------------------------------------
# Fake aiohttp surface
# ---------------------------------------------------------------------------


@dataclass
class _FakeContent:
    chunks: list[bytes]

    async def iter_chunked(self, _n: int):
        for chunk in self.chunks:
            yield chunk
            await asyncio.sleep(0)


@dataclass
class _FakeResponse:
    status: int
    headers: dict[str, str]
    body: bytes = b""
    delay_seconds: float = 0.0

    def __post_init__(self):
        # Single-chunk body is fine for most tests; the size-cap test
        # overrides with multiple chunks via ``content`` directly.
        self.content = _FakeContent([self.body] if self.body else [])

    def release(self) -> None:
        return None


@dataclass
class _FakeSession:
    """One session per URL — matches ``runtime._fetch_one``'s pattern."""

    responses: dict[str, list[_FakeResponse]]
    pre_get: callable | None = None

    closed: bool = False
    sent_urls: list[str] = field(default_factory=list)

    async def get(self, url: str, allow_redirects: bool = True) -> _FakeResponse:
        self.sent_urls.append(url)
        if self.pre_get is not None:
            await self.pre_get(url)
        queue = self.responses.get(url)
        if not queue:
            raise AssertionError(f"no canned response for {url!r}")
        resp = queue.pop(0)
        if resp.delay_seconds:
            await asyncio.sleep(resp.delay_seconds)
        return resp

    async def close(self) -> None:
        self.closed = True


def _make_factory(responses_by_url: dict[str, list[_FakeResponse]], *, pre_get=None):
    def _factory(host: str, *, proxy: str, timeout=None):
        return _FakeSession(responses=responses_by_url, pre_get=pre_get)
    return _factory


# ---------------------------------------------------------------------------
# Inert kill switch (engaged is a manual asyncio.Event)
# ---------------------------------------------------------------------------


class _InertKillSwitch:
    def __init__(self) -> None:
        self.engaged = asyncio.Event()
        self._registered: set[asyncio.Task] = set()

    def register_task(self, task: asyncio.Task) -> None:
        self._registered.add(task)

    def cancel_all(self) -> None:
        for t in self._registered:
            t.cancel()


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def kill_switch() -> _InertKillSwitch:
    return _InertKillSwitch()


def _make_runner(
    db: CrawlDB,
    bus: EventBus,
    kill_switch,
    *,
    mode: str = "BFS",
    factory,
    seed_url: str = SEED_URL,
) -> CrawlRunner:
    crawl_id = crawl_db.create_crawl(
        db, seed_url=seed_url, mode=mode, collection_id=None, max_depth=1
    )
    job_id = jobs_db.create_job(
        db,
        kind="crawl",
        target_type="url",
        target_id=0,
        status="pending",
        payload={"url": seed_url, "mode": mode, "crawl_id": crawl_id},
    )
    return CrawlRunner(
        crawl_id=crawl_id,
        job_id=job_id,
        db=db,
        event_bus=bus,
        kill_switch=kill_switch,  # type: ignore[arg-type]
        seed_url=seed_url,
        mode=mode,
        max_depth=1,
        collection_id=None,
        session_factory=factory,
        clock=lambda: "2026-05-12T00:00:00+00:00",
    )


def _html(body: str = "ok") -> bytes:
    return f"<html><head><title>t</title></head><body>{body}</body></html>".encode("utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_runner_persists_node_and_marks_completed(db, bus, kill_switch):
    factory = _make_factory(
        {
            SEED_URL: [
                _FakeResponse(
                    status=200,
                    headers={"Content-Type": "text/html"},
                    body=_html("hello"),
                )
            ]
        }
    )
    runner = _make_runner(db, bus, kill_switch, factory=factory)
    terminal = await runner.run()
    assert terminal == "completed"

    row = crawl_db.get_crawl(db, runner.crawl_id)
    assert _job_status(db, runner.job_id) == "done"  # completed → job done
    assert row["pages_crawled"] == 1
    # Resource landed crawled, with its current page version carrying the body.
    with db._lock:
        node_row = db._conn.execute(
            "SELECT r.state, pv.http_status, pv.body_text_clean "
            "FROM resources r "
            "JOIN pages p ON p.resource_id = r.id "
            "JOIN page_versions pv ON pv.id = p.current_version_id "
            "WHERE r.url=?",
            (SEED_URL,),
        ).fetchone()
    assert node_row["state"] == "crawled"
    assert node_row["http_status"] == 200
    assert "hello" in node_row["body_text_clean"]


async def test_runner_rejects_non_onion_redirect(db, bus, kill_switch):
    factory = _make_factory(
        {
            SEED_URL: [
                _FakeResponse(
                    status=302,
                    headers={"Location": "http://evil.example.com/"},
                )
            ]
        }
    )
    runner = _make_runner(db, bus, kill_switch, factory=factory)
    await runner.run()
    row = crawl_db.get_crawl(db, runner.crawl_id)
    assert row["pages_failed"] == 1
    assert row["pages_crawled"] == 0


async def test_runner_enforces_size_cap(db, bus, kill_switch, monkeypatch):
    """A response whose streamed chunks exceed 10 MB is rejected mid-stream."""
    big_resp = _FakeResponse(
        status=200, headers={"Content-Type": "text/html"}
    )
    # Replace content with chunks that exceed the cap.
    monkeypatch.setattr(
        "backend.crawler.runtime.MAX_RESPONSE_BYTES", 4 * 1024
    )
    big_chunk = b"x" * 2048
    big_resp.content = _FakeContent([big_chunk] * 5)  # 10 KB total > 4 KB cap

    factory = _make_factory({SEED_URL: [big_resp]})
    runner = _make_runner(db, bus, kill_switch, factory=factory)
    await runner.run()
    row = crawl_db.get_crawl(db, runner.crawl_id)
    assert row["pages_failed"] == 1


async def test_runner_discards_body_for_unparseable_content_type(db, bus, kill_switch):
    factory = _make_factory(
        {
            SEED_URL: [
                _FakeResponse(
                    status=200,
                    headers={"Content-Type": "application/pdf"},
                    body=b"%PDF-1.5\n...",
                )
            ]
        }
    )
    runner = _make_runner(db, bus, kill_switch, factory=factory)
    await runner.run()

    with db._lock:
        node_row = db._conn.execute(
            "SELECT pv.body_text, pv.body_text_clean, pv.http_status "
            "FROM resources r "
            "JOIN pages p ON p.resource_id = r.id "
            "JOIN page_versions pv ON pv.id = p.current_version_id "
            "WHERE r.url=?",
            (SEED_URL,),
        ).fetchone()
        headers = db._conn.execute(
            "SELECT key, value FROM response_headers WHERE page_version_id="
            "(SELECT p.current_version_id FROM resources r "
            " JOIN pages p ON p.resource_id = r.id WHERE r.url=?)",
            (SEED_URL,),
        ).fetchall()
    assert node_row["http_status"] == 200
    assert node_row["body_text"] is None
    assert node_row["body_text_clean"] is None
    # Headers still persisted.
    assert any(h["key"] == "Content-Type" for h in headers)
    # FTS index has no tokens for this page (body was never written).
    with db._lock:
        fts_hits = db._conn.execute(
            "SELECT COUNT(*) AS n FROM pages_fts WHERE pages_fts MATCH 'PDF'"
        ).fetchone()
    assert fts_hits["n"] == 0


async def test_runner_inserts_crawl_edges_for_discovered_links(db, bus, kill_switch):
    seed_body = _html(f'<a href="{CHILD_URL}">child</a>')
    factory = _make_factory(
        {
            SEED_URL: [
                _FakeResponse(
                    status=200, headers={"Content-Type": "text/html"}, body=seed_body,
                )
            ],
            CHILD_URL: [
                _FakeResponse(
                    status=200, headers={"Content-Type": "text/html"}, body=_html(),
                )
            ],
        }
    )
    runner = _make_runner(db, bus, kill_switch, factory=factory)
    await runner.run()

    with db._lock:
        rows = db._conn.execute(
            "SELECT source FROM edges WHERE from_id="
            "(SELECT id FROM resources WHERE url=?) AND to_id="
            "(SELECT id FROM resources WHERE url=?)",
            (SEED_URL, CHILD_URL),
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["source"] == "crawl"


async def test_runner_kill_switch_cancellation_marks_stopped(db, bus, kill_switch):
    """Kill switch cancels the fetch mid-stream → crawl row ends in stopped/tor_down."""
    cancel_event = asyncio.Event()

    async def hang(_url: str) -> None:
        cancel_event.set()
        # Block until cancelled.
        await asyncio.sleep(60)

    factory = _make_factory(
        {SEED_URL: [_FakeResponse(status=200, headers={"Content-Type": "text/html"})]},
        pre_get=hang,
    )
    runner = _make_runner(db, bus, kill_switch, factory=factory)
    task = asyncio.create_task(runner.run())
    await cancel_event.wait()
    kill_switch.cancel_all()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    row = crawl_db.get_crawl(db, runner.crawl_id)
    assert _job_status(db, runner.job_id) == "cancelled"  # stopped → job cancelled
    assert row["error"] == "tor_down"


async def test_runner_focused_mode_auto_flags_on_watchlist_match(db, bus, kill_switch):
    watchlist_db.add_term(db, "ransomware")

    seed_body = _html("ransomware is mentioned here")
    factory = _make_factory(
        {
            SEED_URL: [
                _FakeResponse(
                    status=200, headers={"Content-Type": "text/html"}, body=seed_body,
                )
            ]
        }
    )
    runner = _make_runner(db, bus, kill_switch, mode="Focused", factory=factory)
    await runner.run()

    with db._lock:
        flag = db._conn.execute(
            "SELECT note FROM flags WHERE node_id="
            "(SELECT id FROM resources WHERE url=?)",
            (SEED_URL,),
        ).fetchone()
    assert flag is not None
    assert "ransomware" in flag["note"]


async def test_runner_cooperative_stop_marks_stopped(db, bus, kill_switch):
    """request_stop() between URLs ends the run in 'stopped' (no error).

    Drive determinism with two gates: ``seed_started`` lets the test know the
    seed fetch is in flight, then ``seed_allowed`` releases it. We set
    ``request_stop`` while the seed is blocked, so the runner picks it up on
    the next loop iteration before touching CHILD_URL.
    """
    seed_started = asyncio.Event()
    seed_allowed = asyncio.Event()

    async def gated(url: str) -> None:
        if url == SEED_URL:
            seed_started.set()
            await seed_allowed.wait()
            return
        if url == CHILD_URL:
            raise AssertionError("second URL was fetched despite request_stop")

    seed_body = _html(f'<a href="{CHILD_URL}">child</a>')
    factory = _make_factory(
        {
            SEED_URL: [
                _FakeResponse(status=200, headers={"Content-Type": "text/html"}, body=seed_body),
            ],
            CHILD_URL: [
                _FakeResponse(status=200, headers={"Content-Type": "text/html"}, body=_html()),
            ],
        },
        pre_get=gated,
    )

    runner = _make_runner(db, bus, kill_switch, factory=factory)

    task = asyncio.create_task(runner.run())
    await asyncio.wait_for(seed_started.wait(), timeout=2.0)
    runner.request_stop()
    seed_allowed.set()
    terminal = await asyncio.wait_for(task, timeout=2.0)
    assert terminal == "stopped"
    row = crawl_db.get_crawl(db, runner.crawl_id)
    assert _job_status(db, runner.job_id) == "cancelled"  # stopped → job cancelled
    assert row["error"] is None


# ---------------------------------------------------------------------------
# F4b 3.6 — runner adds crawled nodes to its targeted collection
# ---------------------------------------------------------------------------


def _make_collection_runner(
    db: CrawlDB,
    bus: EventBus,
    kill_switch,
    *,
    collection_id: int | None,
    factory,
    seed_url: str = SEED_URL,
) -> CrawlRunner:
    crawl_id = crawl_db.create_crawl(
        db,
        seed_url=seed_url,
        mode="BFS",
        collection_id=collection_id,
        max_depth=1,
    )
    job_id = jobs_db.create_job(
        db,
        kind="crawl",
        target_type="url",
        target_id=0,
        status="pending",
        payload={"url": seed_url, "mode": "BFS", "crawl_id": crawl_id},
    )
    return CrawlRunner(
        crawl_id=crawl_id,
        job_id=job_id,
        db=db,
        event_bus=bus,
        kill_switch=kill_switch,  # type: ignore[arg-type]
        seed_url=seed_url,
        mode="BFS",
        max_depth=1,
        collection_id=collection_id,
        session_factory=factory,
        clock=lambda: "2026-05-12T00:00:00+00:00",
    )


async def test_runner_adds_crawled_nodes_to_targeted_collection(
    db, bus, kill_switch
):
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "INSERT INTO collections(name, description) VALUES (?, NULL)",
            ("targeted",),
        )
        cid = int(cur.lastrowid)

    seed_body = _html(f'<a href="{CHILD_URL}">child</a>')
    factory = _make_factory(
        {
            SEED_URL: [
                _FakeResponse(
                    status=200,
                    headers={"Content-Type": "text/html"},
                    body=seed_body,
                )
            ],
            CHILD_URL: [
                _FakeResponse(
                    status=200,
                    headers={"Content-Type": "text/html"},
                    body=_html(),
                )
            ],
        }
    )
    runner = _make_collection_runner(
        db, bus, kill_switch, collection_id=cid, factory=factory
    )
    terminal = await runner.run()
    assert terminal == "completed"

    with db._lock:
        rows = db._conn.execute(
            "SELECT n.url FROM collection_items ci "
            "JOIN resources n ON n.id = ci.node_id "
            "WHERE ci.collection_id = ? ORDER BY n.url",
            (cid,),
        ).fetchall()
    urls = sorted(r["url"] for r in rows)
    assert urls == sorted([SEED_URL, CHILD_URL])


async def test_runner_skips_membership_when_collection_id_is_none(
    db, bus, kill_switch
):
    factory = _make_factory(
        {
            SEED_URL: [
                _FakeResponse(
                    status=200,
                    headers={"Content-Type": "text/html"},
                    body=_html(),
                )
            ]
        }
    )
    runner = _make_collection_runner(
        db, bus, kill_switch, collection_id=None, factory=factory
    )
    await runner.run()

    with db._lock:
        n = db._conn.execute(
            "SELECT COUNT(*) AS n FROM collection_items"
        ).fetchone()
    assert n["n"] == 0


async def test_runner_swallows_collection_deleted_mid_crawl(db, bus, kill_switch):
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "INSERT INTO collections(name, description) VALUES (?, NULL)",
            ("ephemeral",),
        )
        cid = int(cur.lastrowid)

    # Two-page crawl. Delete the collection between SEED and CHILD fetches.
    seed_started = asyncio.Event()
    delete_done = asyncio.Event()

    async def gated(url: str) -> None:
        if url == SEED_URL:
            seed_started.set()
            await delete_done.wait()

    seed_body = _html(f'<a href="{CHILD_URL}">child</a>')
    factory = _make_factory(
        {
            SEED_URL: [
                _FakeResponse(
                    status=200,
                    headers={"Content-Type": "text/html"},
                    body=seed_body,
                )
            ],
            CHILD_URL: [
                _FakeResponse(
                    status=200,
                    headers={"Content-Type": "text/html"},
                    body=_html(),
                )
            ],
        },
        pre_get=gated,
    )
    runner = _make_collection_runner(
        db, bus, kill_switch, collection_id=cid, factory=factory
    )
    task = asyncio.create_task(runner.run())
    await asyncio.wait_for(seed_started.wait(), timeout=2.0)
    # Analyst deletes the targeted collection mid-crawl.
    with db.transaction(immediate=True) as c:
        c.execute("DELETE FROM collections WHERE id = ?", (cid,))
    delete_done.set()
    terminal = await asyncio.wait_for(task, timeout=2.0)
    # Crawl keeps going — the ValueError on add_item is swallowed.
    assert terminal == "completed"


# ---------------------------------------------------------------------------
# P3 — crawl pacing profile
# ---------------------------------------------------------------------------


async def test_runner_paces_between_fetches_with_configured_profile(
    db, bus, kill_switch
):
    """A multi-page crawl applies an inter-request delay between fetches,
    using the `crawl.pacing` profile range read from settings at crawl start."""
    put_setting(db, "crawl.pacing", "stealth")
    seed_body = _html(f'<a href="{CHILD_URL}">child</a>')
    factory = _make_factory(
        {
            SEED_URL: [
                _FakeResponse(
                    status=200, headers={"Content-Type": "text/html"}, body=seed_body,
                )
            ],
            CHILD_URL: [
                _FakeResponse(
                    status=200, headers={"Content-Type": "text/html"}, body=_html(),
                )
            ],
        }
    )
    runner = _make_runner(db, bus, kill_switch, factory=factory)

    calls: list[tuple[float, float]] = []

    async def _record(pace_range):
        calls.append(pace_range)

    runner._pace = _record  # type: ignore[method-assign]
    terminal = await runner.run()

    assert terminal == "completed"
    # Two pages → exactly one inter-request gap, paced with the stealth range.
    assert calls == [_PACING_RANGES["stealth"]]


async def test_runner_skips_pacing_before_the_first_fetch(db, bus, kill_switch):
    """A single-page crawl never paces — there is no preceding request."""
    factory = _make_factory(
        {
            SEED_URL: [
                _FakeResponse(
                    status=200, headers={"Content-Type": "text/html"}, body=_html(),
                )
            ]
        }
    )
    runner = _make_runner(db, bus, kill_switch, factory=factory)

    calls: list[tuple[float, float]] = []

    async def _record(pace_range):
        calls.append(pace_range)

    runner._pace = _record  # type: ignore[method-assign]
    await runner.run()

    assert calls == []


async def test_pace_is_a_no_op_for_the_fast_profile(db, bus, kill_switch):
    """The `fast` range (0, 0) returns immediately — no delay, no jitter."""
    runner = _make_runner(db, bus, kill_switch, factory=_make_factory({}))
    loop = asyncio.get_running_loop()
    started = loop.time()
    await runner._pace(_PACING_RANGES["fast"])
    assert loop.time() - started < 0.5


async def test_pace_wakes_immediately_when_stop_is_requested(db, bus, kill_switch):
    """A long stealth delay must not hold up Stop — `_pace` waits on the stop
    event rather than sleeping out the full timeout."""
    runner = _make_runner(db, bus, kill_switch, factory=_make_factory({}))
    runner.request_stop()
    loop = asyncio.get_running_loop()
    started = loop.time()
    # Without the stop-aware wait this would sleep 5-30s.
    await runner._pace(_PACING_RANGES["stealth"])
    assert loop.time() - started < 0.5
