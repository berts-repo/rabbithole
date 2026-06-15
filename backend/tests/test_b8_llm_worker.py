"""Phase B8 — LLM worker batch claim, write-back, retry, auto-enqueue."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import aiohttp
import pytest

from backend.db import auto_rules as auto_rules_db
from backend.db import domains as domains_db
from backend.db import findings as findings_db
from backend.db import llm as llm_db
from backend.db import page_versions as versions_db
from backend.db import pages as pages_db
from backend.db.core import CrawlDB
from backend.services.event_bus import EventBus
from backend.services.graph_cache import GraphCache
from backend.services.llm_worker import LlmWorker, auto_enqueue_for_node


# --- fakes -----------------------------------------------------------------


class _FakeKillSwitch:
    def __init__(self) -> None:
        self.engaged = asyncio.Event()
        self.registered: list[asyncio.Task] = []

    def register_task(self, task: asyncio.Task) -> None:
        self.registered.append(task)


class _FakeProjectState:
    def __init__(self, db: CrawlDB | None) -> None:
        self.active_db = db
        self.graph_cache = GraphCache()


class _FakeResp:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body

    async def __aenter__(self) -> "_FakeResp":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def text(self) -> str:
        return self._body


class _FakeSession:
    """One canned response per .post() call, in order. Or a callable."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.posts: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def post(self, url: str, *, json: dict[str, Any]):
        self.posts.append((url, json))
        if not self._responses:
            return _FakeResp(500, "")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        if callable(nxt):
            return nxt(url, json)
        return nxt


def _make_session_factory(session: _FakeSession):
    def _factory(ollama_url, *, timeout):
        return session

    return _factory


def _ollama_ok(text: str) -> _FakeResp:
    return _FakeResp(200, json.dumps({"response": text}))


# --- fixtures --------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path):
    instance = CrawlDB(tmp_path / "llm_worker.db")
    try:
        yield instance
    finally:
        instance.close()


def _insert_node(
    db: CrawlDB,
    *,
    url: str,
    body: str = "page body",
    domain: str | None = None,
) -> int:
    """Crawl a URL so its resource has page content to analyse; returns the
    resource id."""
    host = domain or url.split("//", 1)[1].split("/", 1)[0]
    rid, _ = versions_db.record_fetch(
        db,
        url=url,
        host=host,
        status_code=200,
        title="t",
        body_text=body,
        body_text_clean=body,
        response_headers={},
        when="2026-05-15T00:00:00+00:00",
    )
    return rid


def _make_worker(db: CrawlDB, session: _FakeSession) -> tuple[LlmWorker, EventBus]:
    bus = EventBus()
    worker = LlmWorker(
        project_state=_FakeProjectState(db),  # type: ignore[arg-type]
        kill_switch=_FakeKillSwitch(),  # type: ignore[arg-type]
        event_bus=bus,
        session_factory=_make_session_factory(session),
        sleep_fn=lambda _: _NoOp(),  # never actually awaited inside _tick
    )
    return worker, bus


class _NoOp:
    def __await__(self):
        if False:
            yield  # pragma: no cover
        return None


def _entity_rows(db: CrawlDB, resource_id: int) -> set[tuple[str, str, str]]:
    """``(type, value, source)`` entity findings for a resource, read straight
    from ``findings`` (type/source live in the metadata JSON)."""
    with db.read() as c:
        rows = c.execute(
            """SELECT value,
                      json_extract(metadata, '$.type') AS type,
                      json_extract(metadata, '$.source') AS source
                 FROM findings
                WHERE kind='entity' AND resource_id=?""",
            (resource_id,),
        ).fetchall()
    return {(r["type"], r["value"], r["source"]) for r in rows}


# --- batch claim + priority ----------------------------------------------


def test_batch_claim_completes_pending(db: CrawlDB):
    n1 = _insert_node(db, url=_ONION("a"))
    n2 = _insert_node(db, url=_ONION("b"))
    high = llm_db.enqueue(
        db, resource_id=n2, analysis_type="Summary", model="qwen2.5:3b", priority=5
    )
    low = llm_db.enqueue(
        db, resource_id=n1, analysis_type="Summary", model="qwen2.5:3b", priority=0
    )
    # Two responses; both pending jobs are claimed and finished in one tick.
    session = _FakeSession([_ollama_ok("hi"), _ollama_ok("hi")])
    worker, _bus = _make_worker(db, session)
    asyncio.run(worker._tick())
    rows = {r["id"]: r for r in llm_db.list_queue(db)}
    assert rows[high]["status"] == "done"
    assert rows[low]["status"] == "done"


# --- Ollama down ----------------------------------------------------------


def test_ollama_unreachable_pushes_back_to_pending(db: CrawlDB):
    node_id = _insert_node(db, url=_ONION("a"))
    aid = llm_db.enqueue(
        db, resource_id=node_id, analysis_type="Summary", model="qwen2.5:3b"
    )
    err = aiohttp.ClientConnectorError(
        connection_key=None,  # type: ignore[arg-type]
        os_error=OSError("refused"),
    )
    session = _FakeSession([err])
    worker, _bus = _make_worker(db, session)
    asyncio.run(worker._tick())
    row = llm_db.get(db, aid)
    assert row is not None
    assert row["status"] == "pending"
    # 30 s retry window kicked in.
    assert worker._status == "ollama_down"


# --- validator drops ------------------------------------------------------


def test_invalid_risk_score_dropped_not_stored(db: CrawlDB):
    node_id = _insert_node(db, url=_ONION("a"))
    aid = llm_db.enqueue(
        db,
        resource_id=node_id,
        analysis_type="Risk Score",
        model="qwen2.5:3b",
    )
    session = _FakeSession([_ollama_ok("high")])  # not an int
    worker, _bus = _make_worker(db, session)
    asyncio.run(worker._tick())
    row = llm_db.get(db, aid)
    assert row is not None
    assert row["status"] == "done"
    assert row["result"] == "<dropped:invalid_output>"


# --- cluster synthesis (item 7, decision D1) ------------------------------


def test_cluster_qa_synthesises_membership(db: CrawlDB):
    # Two crawled members + a Cluster Q&A job. The worker reads the membership
    # snapshot off the claimed job, concatenates page bodies, threads the
    # analyst question into the multi-page prompt, and writes one result row.
    r1 = _insert_node(db, url=_ONION("a"), body="page one mentions btc")
    r2 = _insert_node(db, url=_ONION("b"), body="page two mentions xmr")
    fp = llm_db.compute_fingerprint([r1, r2])
    aid = llm_db.enqueue_cluster(
        db, fingerprint=fp, resource_ids=[r1, r2],
        analysis_type="Cluster Q&A", model="qwen2.5:3b",
        question="which coins are referenced?",
    )
    session = _FakeSession([_ollama_ok("btc and xmr")])
    worker, _bus = _make_worker(db, session)
    asyncio.run(worker._tick())

    row = llm_db.get_cluster_analysis(db, aid)
    assert row is not None
    assert row["status"] == "done"
    assert row["result"] == "btc and xmr"
    # One synthesis call carrying the question + both page bodies.
    assert len(session.posts) == 1
    prompt = session.posts[0][1]["prompt"]
    assert "which coins are referenced?" in prompt
    assert "btc" in prompt and "xmr" in prompt


def test_cluster_job_with_no_crawled_pages_drops(db: CrawlDB):
    # Membership that has no current page content yields a dropped result, not
    # a stuck job.
    fp = llm_db.compute_fingerprint([777])
    aid = llm_db.enqueue_cluster(
        db, fingerprint=fp, resource_ids=[777],
        analysis_type="Cluster Summary", model="qwen2.5:3b",
    )
    session = _FakeSession([])  # no ollama call should be made
    worker, _bus = _make_worker(db, session)
    asyncio.run(worker._tick())

    row = llm_db.get_cluster_analysis(db, aid)
    assert row is not None
    assert row["status"] == "done"
    assert row["result"] == "<dropped:no_content>"
    assert session.posts == []


# --- write-back: entities --------------------------------------------------


def test_entities_writeback_dedupes_against_crawl_source(db: CrawlDB):
    node_id = _insert_node(db, url=_ONION("a"))
    # Pre-existing crawl-sourced entity (same value as LLM will return).
    findings_db.insert_entities(db, node_id, [("blob", "Alice")], source="crawl")
    aid = llm_db.enqueue(
        db,
        resource_id=node_id,
        analysis_type="Entities (LLM)",
        model="qwen2.5:3b",
    )
    session = _FakeSession([_ollama_ok("Alice\nBob")])
    worker, _bus = _make_worker(db, session)
    asyncio.run(worker._tick())
    rows_set = _entity_rows(db, node_id)
    # Crawl-sourced Alice survives; LLM-sourced Alice + Bob added.
    assert ("blob", "Alice", "crawl") in rows_set
    assert ("blob", "Alice", "llm") in rows_set
    assert ("blob", "Bob", "llm") in rows_set
    # Re-running shouldn't multiply LLM rows (duplicate findings are skipped).
    llm_db.rerun(db, aid)
    session2 = _FakeSession([_ollama_ok("Alice\nBob")])
    worker2, _bus = _make_worker(db, session2)
    asyncio.run(worker2._tick())
    llm_rows = {r for r in _entity_rows(db, node_id) if r[2] == "llm"}
    assert llm_rows == {("blob", "Alice", "llm"), ("blob", "Bob", "llm")}


# --- write-back: domain label ---------------------------------------------


def test_domain_label_skipped_when_alias_already_set(db: CrawlDB):
    host = "a" * 56 + ".onion"
    node_id = _insert_node(db, url=f"http://{host}/", domain=host)
    domains_db.touch_domain(db, host, "2026-05-15T00:00:00")
    domains_db.rename_alias(db, host, "Analyst Alias")
    aid = llm_db.enqueue(
        db,
        resource_id=node_id,
        analysis_type="Domain Label",
        model="qwen2.5:3b",
    )
    session = _FakeSession([_ollama_ok("Model Alias")])
    worker, bus = _make_worker(db, session)
    skipped: list[Any] = []

    async def _drive() -> None:
        async def _collect() -> None:
            try:
                async for ev in bus.subscribe("llm.domain_label.skipped"):
                    skipped.append(ev)
                    return
            except asyncio.CancelledError:
                return

        consumer = asyncio.create_task(_collect())
        await asyncio.sleep(0)  # let subscription register
        await worker._tick()
        await asyncio.sleep(0)
        consumer.cancel()
        try:
            await consumer
        except (asyncio.CancelledError, Exception):
            pass

    asyncio.run(_drive())

    profile = domains_db.get_profile(db, host)
    assert profile is not None
    assert profile["alias"] == "Analyst Alias"
    row = llm_db.get(db, aid)
    assert row is not None and row["status"] == "done"
    # The skipped event was published.
    assert any("alias" in ev for ev in skipped)


def test_domain_label_writes_when_no_alias_present(db: CrawlDB):
    host = "b" * 56 + ".onion"
    node_id = _insert_node(db, url=f"http://{host}/", domain=host)
    domains_db.touch_domain(db, host, "2026-05-15T00:00:00")
    aid = llm_db.enqueue(
        db,
        resource_id=node_id,
        analysis_type="Domain Label",
        model="qwen2.5:3b",
    )
    session = _FakeSession([_ollama_ok("Model Alias")])
    worker, _bus = _make_worker(db, session)
    asyncio.run(worker._tick())
    profile = domains_db.get_profile(db, host)
    assert profile is not None
    assert profile["alias"] == "Model Alias"


# --- write-back: summary / category ---------------------------------------


def test_summary_writeback(db: CrawlDB):
    node_id = _insert_node(db, url=_ONION("a"))
    llm_db.enqueue(
        db, resource_id=node_id, analysis_type="Summary", model="qwen2.5:3b"
    )
    session = _FakeSession([_ollama_ok("Two-sentence summary.")])
    worker, _bus = _make_worker(db, session)
    asyncio.run(worker._tick())
    page = pages_db.get_page_detail(db, node_id)
    assert page is not None and page["summary"] == "Two-sentence summary."


def test_category_writeback(db: CrawlDB):
    node_id = _insert_node(db, url=_ONION("a"))
    llm_db.enqueue(
        db, resource_id=node_id, analysis_type="Category", model="qwen2.5:3b"
    )
    session = _FakeSession([_ollama_ok("forum")])
    worker, _bus = _make_worker(db, session)
    asyncio.run(worker._tick())
    page = pages_db.get_page_detail(db, node_id)
    assert page is not None and page["category"] == "forum"


# --- auto_enqueue_for_node ------------------------------------------------


def test_auto_enqueue_skips_excluded_nodes(db: CrawlDB):
    node_id = _insert_node(db, url=_ONION("a"))
    pages_db.set_analysis_excluded(db, node_id, True)
    new_ids = auto_enqueue_for_node(db, node_id)
    assert new_ids == []
    assert llm_db.list_queue(db) == []


def test_auto_enqueue_default_summary_only(db: CrawlDB):
    # Parity with the legacy llm.auto_enqueue.* defaults: a fresh DB seeds the
    # crawl rules from those settings (Summary on, the rest off), so only
    # Summary fires — identical to the pre-D4 behavior.
    node_id = _insert_node(db, url=_ONION("a"))
    new_ids = auto_enqueue_for_node(db, node_id)
    assert len(new_ids) == 1
    rows = llm_db.list_queue(db)
    assert {r["analysis_type"] for r in rows} == {"Summary"}


def test_auto_enqueue_honors_enabled_crawl_rules(db: CrawlDB):
    # Post-D4 the crawl trigger reads the typed rules, not the settings:
    # enabling the Category + Risk Score crawl rules makes them fire too.
    rules = {
        str(r["analysis_type"]): r["id"]
        for r in auto_rules_db.list_rules(db, trigger_kind="crawl")
    }
    auto_rules_db.update(db, rules["Category"], enabled=True)
    auto_rules_db.update(db, rules["Risk Score"], enabled=True)
    node_id = _insert_node(db, url=_ONION("a"))
    auto_enqueue_for_node(db, node_id)
    rows = llm_db.list_queue(db)
    assert {r["analysis_type"] for r in rows} == {
        "Summary",
        "Category",
        "Risk Score",
    }


def test_auto_enqueue_respects_disabled_summary_rule(db: CrawlDB):
    # Disabling the only default-on rule means nothing auto-enqueues.
    summary = next(
        r for r in auto_rules_db.list_rules(db, trigger_kind="crawl")
        if r["analysis_type"] == "Summary"
    )
    auto_rules_db.update(db, summary["id"], enabled=False)
    node_id = _insert_node(db, url=_ONION("a"))
    assert auto_enqueue_for_node(db, node_id) == []
    assert llm_db.list_queue(db) == []


# --- helpers ---------------------------------------------------------------


def _ONION(seed: str) -> str:
    """Return a fake but well-formed v3 onion URL based on a seed character."""
    return "http://" + (seed * 56) + ".onion/"
