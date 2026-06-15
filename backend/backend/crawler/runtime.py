"""Async crawl runtime.

``CrawlRunner`` drives a single crawl from start to finish: pop URL → fetch
through ``make_tor_session`` → parse → persist nodes/entities/edges → enqueue
discovered links. ``CrawlRunnerRegistry`` is a thin manager that lets the
``routes/crawl.py`` handler start/stop runners and look up active state.

Three external dependencies are dependency-injected so unit tests can drive
the loop without a live Tor circuit:

* ``session_factory`` — defaults to :func:`make_tor_session`. Tests supply
  a fake that returns a stubbed ``aiohttp.ClientSession``.
* ``parse_fn`` — defaults to :func:`parse_html`. Same idea.
* ``clock`` — wall-clock function used for ``first_seen`` / ``last_seen``
  / ``started_at``. Tests pass a deterministic stub.

The runtime never constructs an ``aiohttp.ClientSession`` directly (B0 guard
in ``Makefile:28``); every outbound request goes through the security factory.
"""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, TYPE_CHECKING
from urllib.parse import urlsplit

import aiohttp

from .parser import (
    PARSEABLE_CONTENT_TYPES,
    ParseResult,
    is_parseable_content_type,
    parse_html,
)
from .frontier import Frontier, WatchlistMatcher
from ..db import collections as collections_db
from ..db import crawl as crawl_db
from ..db import domains as domains_db
from ..db import edges as edges_db
from ..db import findings as findings_db
from ..db import flags as flags_db
from ..db import jobs as jobs_db
from ..db import page_versions as page_versions_db
from ..db import resources as resources_db
from ..db.settings import get_setting, i2p_enabled
from ..security.net import (
    DEFAULT_TIMEOUT,
    EgressError,
    MAX_RESPONSE_BYTES,
    make_tor_session,
    network_of_host,
    validate_network_url,
)
from ..services.event_bus import EventBus
# One-way import: crawler depends on the LLM worker's auto-enqueue helper.
# ``services/llm_worker.py`` must NEVER import this module back.
from ..services.llm_worker import auto_enqueue_for_node

if TYPE_CHECKING:
    from ..db.core import CrawlDB
    from ..services.graph_cache import GraphCache
    from ..services.kill_switch import KillSwitch


log = logging.getLogger(__name__)


REDIRECT_CAP = 5  # PLAN.md key constants: "Redirect cap: 5"


# Inter-request crawl pacing. Each `crawl.pacing` profile maps to a
# (low, high) seconds range; the loop sleeps a fresh `random.uniform(...)`
# between fetches. `fast` disables the delay; `polite` (default) jitters a
# short delay so the cadence is not a machine-detectable constant; `stealth`
# is human-scale think-time for targets that watch their logs. Pacing removes
# the timing tell only — breadth-first link order stays machine-like.
_PACING_RANGES: dict[str, tuple[float, float]] = {
    "fast": (0.0, 0.0),
    "polite": (0.5, 2.0),
    "stealth": (5.0, 30.0),
}
_DEFAULT_PACING = "polite"


SessionFactory = Callable[..., aiohttp.ClientSession]
ParseFn = Callable[[bytes | str, str | None], ParseResult]
Clock = Callable[[], str]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


class RedirectError(Exception):
    """Raised when a redirect chain leaves the supported-network envelope
    (clearnet, or a cross-network jump such as ``.onion`` → ``.i2p``)."""


class ResponseTooLargeError(Exception):
    """Raised when a streamed body exceeds ``MAX_RESPONSE_BYTES``."""


@dataclass
class _FetchOutcome:
    """Internal — what ``_fetch_one`` returns to the loop."""

    final_url: str
    status_code: int
    headers: dict[str, str]
    body: bytes | None  # None when the CT gate dropped the body
    parseable: bool


# ---------------------------------------------------------------------------
# CrawlRunner
# ---------------------------------------------------------------------------


@dataclass
class CrawlRunner:
    """Single crawl session. Use :meth:`run` to drive it to completion."""

    crawl_id: int
    job_id: int
    db: "CrawlDB"
    event_bus: EventBus
    kill_switch: "KillSwitch"
    seed_url: str
    mode: str
    max_depth: int | None = None
    collection_id: int | None = None
    # Optional so unit tests can construct a runner without the full app
    # state. In-process callers (routes + schedule daemon) always pass it.
    graph_cache: "GraphCache | None" = None

    session_factory: SessionFactory = field(default=make_tor_session)
    parse_fn: ParseFn = field(default=parse_html)
    clock: Clock = field(default=_now_iso)

    _stop_requested: asyncio.Event = field(default_factory=asyncio.Event)
    _matcher: WatchlistMatcher | None = None
    _watchlist_watcher_task: asyncio.Task | None = None

    # -- public surface ----------------------------------------------------

    def request_stop(self) -> None:
        """Cooperative stop. The loop exits after the current URL."""
        self._stop_requested.set()

    async def run(self) -> str:
        """Drive the crawl to completion. Returns the final crawl terminal.

        Possible terminals: ``completed``, ``stopped``, ``failed`` — the
        crawl-domain vocabulary used by the live SSE view and the queue
        runner. The unified ``jobs`` status is written here too, mapped
        ``completed→done`` / ``stopped→cancelled`` / ``failed→failed``;
        ``stopped`` covers analyst-requested stops and kill-switch
        cancellation (the latter carries ``error='tor_down'``). ``crawls``
        keeps only the per-run timing/error via ``set_started`` / ``finalize``.
        """
        started = self.clock()
        jobs_db.set_status(self.db, self.job_id, "running")
        crawl_db.set_started(self.db, self.crawl_id, started)
        self._publish_status("running", {"started_at": started})

        tor_proxy = get_setting(self.db, "tor.proxy") or "socks5h://127.0.0.1:9050"
        i2p_proxy = get_setting(self.db, "i2p.proxy") or "socks5h://127.0.0.1:4447"
        allow_i2p = i2p_enabled(self.db)
        pacing = get_setting(self.db, "crawl.pacing") or _DEFAULT_PACING
        pace_range = _PACING_RANGES.get(pacing, _PACING_RANGES[_DEFAULT_PACING])

        frontier = Frontier(
            mode=self.mode,
            seed_host=_host_of(self.seed_url),
            max_depth=self.max_depth,
        )
        frontier.enqueue(self.seed_url, depth=0)
        crawl_db.bump_counter(self.db, self.crawl_id, "pages_queued")

        if self.mode == "Focused":
            self._matcher = WatchlistMatcher.from_db(self.db)
            self._watchlist_watcher_task = asyncio.create_task(
                self._watch_watchlist(), name=f"watchlist_watch_{self.crawl_id}"
            )

        terminal: str
        fetched_any = False
        try:
            while True:
                if self.kill_switch.engaged.is_set():
                    raise asyncio.CancelledError()
                if self._stop_requested.is_set():
                    terminal = "stopped"
                    break
                entry = frontier.pop()
                if entry is None:
                    terminal = "completed"
                    break
                if fetched_any:
                    # Jittered inter-request delay — skipped before the first
                    # fetch. Wakes early on a stop request so a long stealth
                    # delay never holds up Stop.
                    await self._pace(pace_range)
                    if self._stop_requested.is_set():
                        terminal = "stopped"
                        break
                await self._process_one(
                    frontier,
                    entry,
                    tor_proxy=tor_proxy,
                    i2p_proxy=i2p_proxy,
                    allow_i2p=allow_i2p,
                )
                fetched_any = True
        except asyncio.CancelledError:
            terminal = "stopped"
            when = self.clock()
            jobs_db.set_status(self.db, self.job_id, "cancelled", error="tor_down")
            crawl_db.finalize(self.db, self.crawl_id, when, error="tor_down")
            self._publish_status("stopped", {"error": "tor_down"})
            raise
        except Exception as exc:  # noqa: BLE001 — crawl must never crash the host
            log.exception("crawl %s failed", self.crawl_id)
            when = self.clock()
            jobs_db.set_status(self.db, self.job_id, "failed", error=str(exc))
            crawl_db.finalize(self.db, self.crawl_id, when, error=str(exc))
            self._publish_status("failed", {"error": str(exc)})
            return "failed"
        finally:
            if self._watchlist_watcher_task is not None:
                self._watchlist_watcher_task.cancel()
                try:
                    await self._watchlist_watcher_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

        when = self.clock()
        if terminal == "stopped":
            jobs_db.set_status(self.db, self.job_id, "cancelled")
            crawl_db.finalize(self.db, self.crawl_id, when)
            self._publish_status("stopped", {})
        else:
            jobs_db.set_status(self.db, self.job_id, "done")
            crawl_db.finalize(self.db, self.crawl_id, when)
            self._publish_status("completed", {})
        return terminal

    # -- per-URL processing ------------------------------------------------

    async def _process_one(
        self,
        frontier: Frontier,
        entry,
        *,
        tor_proxy: str,
        i2p_proxy: str,
        allow_i2p: bool,
    ) -> None:
        url = entry.url
        host = entry.host
        when = self.clock()
        try:
            outcome = await self._fetch_one(
                url, tor_proxy=tor_proxy, i2p_proxy=i2p_proxy
            )
        except RedirectError as exc:
            self._publish_log(f"redirect rejected: {url} ({exc})")
            crawl_db.bump_counter(self.db, self.crawl_id, "pages_failed")
            return
        except ResponseTooLargeError:
            self._publish_log(f"response too large: {url}")
            crawl_db.bump_counter(self.db, self.crawl_id, "pages_failed")
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._publish_log(f"fetch failed: {url} ({exc})")
            crawl_db.bump_counter(self.db, self.crawl_id, "pages_failed")
            return

        domains_db.touch_domain(self.db, host, when)

        if not outcome.parseable or outcome.body is None:
            node_id, _ = page_versions_db.record_failed_fetch(
                self.db,
                url=outcome.final_url,
                status_code=outcome.status_code,
                response_headers=outcome.headers,
                host=_host_of(outcome.final_url),
                when=when,
            )
            crawl_db.link_crawl_node(
                self.db, self.crawl_id, node_id, entry.depth
            )
            self._add_to_targeted_collection(node_id)
            crawl_db.bump_counter(self.db, self.crawl_id, "pages_skipped")
            self._publish_log(
                f"skipped (non-html): {outcome.final_url} status={outcome.status_code}"
            )
            self._invalidate_graph_cache()
            return

        result = self.parse_fn(outcome.body, outcome.final_url)
        node_id, version_id = page_versions_db.record_fetch(
            self.db,
            url=outcome.final_url,
            status_code=outcome.status_code,
            title=result.title,
            body_text=result.body_text,
            body_text_clean=result.body_text_clean,
            response_headers=outcome.headers,
            host=_host_of(outcome.final_url),
            when=when,
        )
        # Extracted entities attach to the version they came from (the reset's
        # findings model); there is no waiting-analyses promotion any more —
        # analysis work-state lives on the jobs table, not on a stub flip.
        findings_db.insert_entities(
            self.db, node_id, result.entities,
            source="crawl", page_version_id=version_id, now=when,
        )

        # Edge: parent -> this node (crawl source).
        if entry.parent_id is not None:
            edges_db.insert_crawl_edge(
                self.db,
                from_id=entry.parent_id,
                to_id=node_id,
                anchor_text=entry.anchor_text,
            )

        crawl_db.link_crawl_node(self.db, self.crawl_id, node_id, entry.depth)
        self._add_to_targeted_collection(node_id)
        crawl_db.bump_counter(self.db, self.crawl_id, "pages_crawled")

        # B8 auto-enqueue: each ``llm.auto_enqueue.*`` flag the analyst has
        # turned on adds one analysis to the queue. Skipped when the node
        # has ``analysis_excluded=true``. Never raises — failures inside
        # the helper are swallowed there.
        try:
            auto_enqueue_for_node(self.db, node_id)
        except Exception:  # noqa: BLE001 — never let the crawl loop die
            log.exception(
                "auto-enqueue failed for crawl=%s node=%d",
                self.crawl_id,
                node_id,
            )

        # Watchlist match — auto-flag (PLAN.md:286). Even outside Focused
        # mode the analyst expects a hit to surface in the Flags pane.
        matched: list[str] = []
        if self._matcher is not None and not self._matcher.empty:
            matched = self._matcher.match(result.body_text_clean)
            if matched:
                flags_db.insert_watchlist_flag(self.db, node_id, matched)
                self.event_bus.publish(
                    "crawl.alert",
                    {
                        "crawl_id": self.crawl_id,
                        "node_id": node_id,
                        "matched": matched,
                    },
                )

        focused_eligible = (self.mode != "Focused") or bool(matched)

        # Enqueue discovered links. Each child becomes a stub if new. Links to
        # a network we cannot egress to (``.i2p`` while I2P is disabled) are
        # still recorded as resource nodes + edges so the graph shows them, but
        # they are never scheduled for a fetch.
        for absolute_url, anchor_text in result.links:
            if frontier.seen(absolute_url):
                continue
            child_host = _host_of(absolute_url)
            child_id = resources_db.upsert_resource(
                self.db, absolute_url, child_host,
                state="known", when=when,
            )
            edges_db.insert_crawl_edge(
                self.db,
                from_id=node_id,
                to_id=child_id,
                anchor_text=anchor_text,
            )
            if network_of_host(child_host) == "i2p" and not allow_i2p:
                continue
            enqueued = frontier.enqueue(
                absolute_url,
                depth=entry.depth + 1,
                parent_id=node_id,
                anchor_text=anchor_text,
                focused_eligible=focused_eligible,
            )
            if enqueued:
                crawl_db.bump_counter(self.db, self.crawl_id, "pages_queued")

        self._publish_page(node_id, outcome.final_url, result.title)
        self._publish_log(
            f"crawled: {outcome.final_url} status={outcome.status_code} "
            f"entities={len(result.entities)} links={len(result.links)}"
        )
        self._invalidate_graph_cache()

    # -- HTTP fetch + redirect walk ----------------------------------------

    async def _fetch_one(
        self, url: str, *, tor_proxy: str, i2p_proxy: str
    ) -> _FetchOutcome:
        """Walk redirects up to ``REDIRECT_CAP`` and stream the final body.

        Each hop is routed through the proxy for its network (``.onion`` → Tor,
        ``.i2p`` → the I2P SOCKS proxy). A redirect must stay on the same
        network as the entry URL — a cross-network jump is rejected.
        """
        network, _ = validate_network_url(url)
        current = url
        for hop in range(REDIRECT_CAP + 1):
            host = _host_of(current)
            proxy = i2p_proxy if network_of_host(host) == "i2p" else tor_proxy
            session = self.session_factory(host, proxy=proxy, timeout=DEFAULT_TIMEOUT)
            task = asyncio.current_task()
            if task is not None:
                self.kill_switch.register_task(task)
            try:
                response = await session.get(current, allow_redirects=False)
                try:
                    status_code = response.status
                    headers = {k: v for k, v in response.headers.items()}
                    if 300 <= status_code < 400 and "Location" in response.headers:
                        next_url = _resolve_redirect(
                            current, response.headers["Location"]
                        )
                        try:
                            next_network, next_url = validate_network_url(next_url)
                        except EgressError as exc:
                            raise RedirectError(str(exc)) from exc
                        if next_network != network:
                            raise RedirectError(
                                f"cross-network redirect target: {next_url!r}"
                            )
                        current = next_url
                        continue

                    body = await self._read_body(response)
                    parseable = is_parseable_content_type(
                        response.headers.get("Content-Type")
                    )
                    return _FetchOutcome(
                        final_url=current,
                        status_code=status_code,
                        headers=headers,
                        body=body if parseable else None,
                        parseable=parseable,
                    )
                finally:
                    response.release()
            finally:
                await session.close()
            # The for-loop only reaches here on `continue` (above), which
            # already incremented `hop`. Stop after REDIRECT_CAP hops.
        raise RedirectError(f"too many redirects: {url}")

    async def _read_body(self, response: aiohttp.ClientResponse) -> bytes:
        """Stream the body in chunks, aborting if it exceeds the cap."""
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.content.iter_chunked(64 * 1024):
            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                raise ResponseTooLargeError(
                    f"response exceeded {MAX_RESPONSE_BYTES} bytes"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    # -- crawl pacing ------------------------------------------------------

    async def _pace(self, pace_range: tuple[float, float]) -> None:
        """Sleep a jittered inter-request delay, waking early on a stop.

        Implements the ``crawl.pacing`` profile. Waiting on the stop event
        rather than a bare ``asyncio.sleep`` means a long ``stealth`` delay
        collapses to near-zero the instant the analyst clicks Stop; a
        kill-switch cancellation propagates as ``CancelledError`` through the
        wait, exactly as in ``_fetch_one``.
        """
        low, high = pace_range
        if high <= 0:
            return
        delay = random.uniform(low, high)
        try:
            await asyncio.wait_for(self._stop_requested.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    # -- event bus helpers -------------------------------------------------

    def _publish_status(self, status: str, extra: dict) -> None:
        payload = {"crawl_id": self.crawl_id, "status": status, **extra}
        self.event_bus.publish("crawl.status", payload)

    def _publish_log(self, message: str) -> None:
        self.event_bus.publish(
            "crawl.log",
            {"crawl_id": self.crawl_id, "message": message},
        )

    def _publish_page(self, node_id: int, url: str, title: str | None) -> None:
        self.event_bus.publish(
            "crawl.page",
            {
                "crawl_id": self.crawl_id,
                "node_id": node_id,
                "url": url,
                "title": title,
            },
        )

    def _invalidate_graph_cache(self) -> None:
        """Drop the cached graph payload — new node/edge data is on disk."""
        if self.graph_cache is not None:
            self.graph_cache.invalidate()

    def _add_to_targeted_collection(self, node_id: int) -> None:
        """Add a recorded node to the runner's collection, if any.

        Called from both record paths in the crawl loop. ``add_item`` is
        idempotent (``INSERT OR IGNORE``) so re-recorded pages stay put.
        Defensively swallows ``ValueError`` so a collection deleted
        mid-crawl doesn't kill the runner — the analyst's deletion wins.
        """
        if self.collection_id is None:
            return
        try:
            collections_db.add_item(self.db, self.collection_id, node_id)
        except ValueError:
            # unknown_collection (deleted mid-crawl) or unknown_node
            # (shouldn't happen — we just recorded it). Either way, the
            # crawl loop keeps going.
            pass

    # -- watchlist subscription -------------------------------------------

    async def _watch_watchlist(self) -> None:
        """Rebuild the matcher on every ``watchlist.changed`` event."""
        try:
            async for _event in self.event_bus.subscribe("watchlist.changed"):
                self._matcher = WatchlistMatcher.from_db(self.db)
        except asyncio.CancelledError:
            return


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def _resolve_redirect(base: str, location: str) -> str:
    """Resolve ``Location`` against the base URL (handles relative redirects)."""
    from urllib.parse import urljoin

    return urljoin(base, location)


CompletionCallback = Callable[
    [CrawlRunner, "str | None", "BaseException | None"], None
]


class CrawlRunnerRegistry:
    """Tracks the in-flight runner for the active process.

    One process holds at most one running crawl. The DB-level check in
    ``crawl_db.find_active`` is authoritative; this registry just owns the
    asyncio task so ``POST /api/crawl/stop`` and the lifespan shutdown can
    find it.

    Callers may pass ``on_finish`` to ``start`` to hook into completion —
    the durable crawl queue runner uses this to flip the queue row to its
    terminal status and pick up the next row without polling the DB. The
    callback runs after self-eviction so a synchronous ``try_advance``
    from inside the callback sees an idle registry.
    """

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._runner: CrawlRunner | None = None

    @property
    def runner(self) -> CrawlRunner | None:
        return self._runner

    @property
    def crawl_id(self) -> int | None:
        return None if self._runner is None else self._runner.crawl_id

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(
        self,
        runner: CrawlRunner,
        *,
        on_finish: CompletionCallback | None = None,
    ) -> asyncio.Task:
        if self.is_running():
            raise RuntimeError("a crawl is already running in this process")

        async def _drive() -> None:
            result: str | None = None
            exc: BaseException | None = None
            try:
                result = await runner.run()
            except BaseException as e:  # noqa: BLE001 — re-raised after capture
                exc = e
                raise
            finally:
                # Self-evict on completion regardless of outcome so the
                # next start() doesn't get the stale handle.
                if self._task is asyncio.current_task():
                    self._runner = None
                    self._task = None
                if on_finish is not None:
                    try:
                        on_finish(runner, result, exc)
                    except Exception:  # noqa: BLE001 — never let the task die
                        log.exception(
                            "on_finish callback failed for crawl %s",
                            runner.crawl_id,
                        )

        self._runner = runner
        self._task = asyncio.create_task(_drive(), name=f"crawl_{runner.crawl_id}")
        return self._task

    async def stop(self) -> None:
        """Cooperative stop. Returns after the runner's task finishes."""
        if self._runner is None or self._task is None:
            return
        self._runner.request_stop()
        try:
            await asyncio.wait_for(self._task, timeout=30.0)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):  # noqa: BLE001
            pass


__all__ = [
    "REDIRECT_CAP",
    "CompletionCallback",
    "CrawlRunner",
    "CrawlRunnerRegistry",
    "PARSEABLE_CONTENT_TYPES",
    "RedirectError",
    "ResponseTooLargeError",
]
