"""Dark-web search-tab harvest stream.

PLAN.md:347. SSE endpoint that, given a query string and the analyst's
enabled engines, fetches each engine's result page through Tor, parses
out ``.onion`` links, and (for any link not already crawled) issues
a bounded GET probe to extract a title + meta description.

Probes are **transient**: nothing touches the DB. The SSE payload carries
title/description in memory for the lifetime of the stream; the analyst's
"Queue Crawl" / "+ Collection" buttons are what create persistent rows.

Probe shape (decision locked with user 2026-05-15):
  * **GET** (not HEAD) so we can extract the metadata the UI displays.
  * Total ≤1 MB, html-only via Content-Type allowlist, 10 s timeout.
  * Same egress envelope as the crawler — Tor SOCKS5h, .onion targets only.

Stream event types match search-tab.md:90:
  * URL result    — ``{engine, url, crawled, anchor_text}``; crawled rows also
                    carry ``{node_id, title, category, last_seen}`` from the
                    local DB so the row can render + "→ Graph" can highlight.
  * ``probe``     — ``{type:"probe", url, title, description}`` (uncrawled only)
  * ``done``      — ``{type:"done", engine, count}``
  * ``error``     — ``{type:"error", engine, message, reason}`` where reason is
                    one of connection|timeout|unreadable|invalid (see
                    ``_FetchError``)
  * ``all_done``  — ``{type:"all_done"}`` then stream closes
  * ``status``    — early ``{type:"status", state:"connecting", engine}`` heartbeat

An optional ``engines`` query param (comma-separated engine ids) narrows the
search to the analyst's per-session source selection; absent = every enabled
engine. The id set is always intersected with the truly-enabled engines.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncIterator
from urllib.parse import (
    parse_qs,
    parse_qsl,
    quote_plus,
    urldefrag,
    urlencode,
    urljoin,
    urlsplit,
    urlunsplit,
)

import aiohttp
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from ..crawler.parser import is_parseable_content_type, parse_html
from ..db import resources as resources_db
from ..db import search_engines as search_engines_db
from ..db.core import CrawlDB
from ..db.settings import get_setting, i2p_enabled
from ..security.net import (
    EgressError,
    I2P_URL_RE,
    ONION_URL_RE,
    make_tor_session,
    validate_network_url,
)
from .deps import get_active_db


router = APIRouter()
log = logging.getLogger(__name__)


# Probe limits — tighter than the regular crawler's 10 MB / 60 s.
_PROBE_MAX_BYTES = 1 * 1024 * 1024
_PROBE_TIMEOUT_SECONDS = 10.0
_DEFAULT_PROXY = "socks5h://127.0.0.1:9050"
_DEFAULT_I2P_PROXY = "socks5h://127.0.0.1:4447"
_QUERY_PLACEHOLDER = "{q}"
_PROBE_CONCURRENCY = 4
_QUERY_MAX_LEN = 256

# Query-param names search engines use to wrap a result behind a redirect on
# their own domain (e.g. Ahmia's ``/search/redirect?redirect_url=<onion>``).
# When present we extract the embedded target rather than the wrapper URL, so
# results point at the real site and a page of hits doesn't collapse to the
# engine's own onion.
_REDIRECT_PARAMS = ("redirect_url", "url", "u", "redirect", "link", "r")

# Non-anchored URL scanners for pulling targets out of result-page *text*
# (some engines print the URL under each hit) — the anchored *_URL_RE are
# match-only. Same host shapes as the egress contract, for both networks.
_ONION_SCAN_RE = re.compile(
    r"https?://[a-z2-7]{56}\.onion(?::\d+)?(?:[/?#][^\s\"'<>]*)?",
    re.IGNORECASE,
)
_I2P_SCAN_RE = re.compile(
    r"https?://(?:[a-z0-9-]+\.)+i2p(?::\d+)?(?:[/?#][^\s\"'<>]*)?",
    re.IGNORECASE,
)


def _sse(payload: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(payload, default=str)}\n\n".encode("utf-8")


def _enabled_engines(db: CrawlDB) -> list[dict[str, Any]]:
    """List engines whose ``search.engine.{id}.enabled`` setting is truthy.

    Unset = disabled; ``seed_defaults`` writes ``true`` for each preseeded
    engine so the Search tab pre-selects them on a fresh project.
    """
    out: list[dict[str, Any]] = []
    for engine in search_engines_db.list_engines(db):
        flag = get_setting(db, f"search.engine.{engine['id']}.enabled")
        if flag is None or flag.strip().lower() != "true":
            continue
        out.append(engine)
    return out


def _parse_engine_ids(raw: str) -> set[int] | None:
    """Parse the optional ``engines`` query param (comma-separated ids).

    Returns the requested id set, or ``None`` when the param is absent/blank —
    the analyst's per-session source-selector override. ``None`` means "every
    enabled engine" (the pre-selection a fresh Search tab sends). Garbage
    tokens are dropped rather than 400'd; the result is always intersected with
    the truly-enabled set, so a stale or bogus id can never widen the search.
    """
    raw = raw.strip()
    if not raw:
        return None
    ids: set[int] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            ids.add(int(token))
        except ValueError:
            continue
    return ids


def _substitute_query(template: str, q: str) -> str:
    encoded = quote_plus(q)
    if _QUERY_PLACEHOLDER in template:
        return template.replace(_QUERY_PLACEHOLDER, encoded)
    sep = "&" if ("?" in template) else "?"
    return f"{template}{sep}q={encoded}"


def _append_params(url: str, params: dict[str, str]) -> str:
    """Return ``url`` with ``params`` appended to its query string."""
    parts = urlsplit(url)
    merged = parse_qsl(parts.query, keep_blank_values=True)
    merged.extend(params.items())
    return urlunsplit(parts._replace(query=urlencode(merged)))


def _search_form_hidden_fields(body: bytes) -> dict[str, str]:
    """Hidden inputs of the page's search ``<form>`` (the bot-gate token, etc.).

    Some engines (Ahmia) gate their result page behind a per-page hidden field
    the homepage form carries: a bare GET of the query URL 302-bounces to the
    homepage. A browser loads the homepage, picks up the form's hidden inputs,
    and submits them with the query. We replay that — locate the form holding a
    free-text query input and return its hidden fields so the query can be
    re-issued the way the engine expects. Empty when no such form exists (the
    common case — naive engines need no priming).
    """
    soup = BeautifulSoup(body, "lxml")
    for form in soup.find_all("form"):
        inputs = form.find_all("input")
        has_query = any(
            (inp.get("type") or "text").strip().lower() in ("text", "search")
            for inp in inputs
        )
        if not has_query:
            continue
        fields: dict[str, str] = {}
        for inp in inputs:
            if (inp.get("type") or "text").strip().lower() != "hidden":
                continue
            name = inp.get("name")
            if name:
                fields[name] = inp.get("value") or ""
        if fields:
            return fields
    return {}


def _is_target_url(candidate: str) -> bool:
    """True for a crawlable ``.onion`` or ``.i2p`` result URL."""
    return bool(ONION_URL_RE.match(candidate) or I2P_URL_RE.match(candidate))


def _target_from_link(absolute: str) -> str | None:
    """The real eepsite/onion a result link points at, or ``None`` if it isn't one.

    Prefers an embedded redirect target (``…?redirect_url=<target>``) over the
    wrapper URL itself, so an engine's redirect links resolve to the sites they
    point at rather than to the engine.
    """
    parts = urlsplit(absolute)
    if parts.query:
        params = parse_qs(parts.query)
        for key in _REDIRECT_PARAMS:
            for val in params.get(key, []):
                cand = val.strip().lower()
                if _is_target_url(cand):
                    return cand
    low = absolute.lower()
    return low if _is_target_url(low) else None


def _extract_result_links(
    body: bytes, engine_url: str
) -> list[tuple[str, str | None]]:
    """Onion/eepsite result URLs from an engine result page, with anchor text.

    Broader than the crawler's ``parse_html`` link rule (which keeps only direct
    ``<a href>``s) because engine pages hide targets behind redirect wrappers or
    print them as plain text. Sources, in priority order:

      1. ``<a href>`` — direct or redirect-unwrapped (carries anchor text).
      2. Bare ``.onion``/``.i2p`` URLs in the page's visible text (no anchor).

    The engine's own host (nav / logo / footer self-links) is dropped — those
    are chrome, not results. Deduped, first occurrence wins.
    """
    engine_host = (urlsplit(engine_url).hostname or "").lower()
    soup = BeautifulSoup(body, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    out: list[tuple[str, str | None]] = []
    seen: set[str] = set()

    def _add(url: str, anchor: str | None) -> None:
        host = (urlsplit(url).hostname or "").lower()
        if host == engine_host or url in seen:
            return
        seen.add(url)
        out.append((url, anchor or None))

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "data:")):
            continue
        absolute, _ = urldefrag(urljoin(engine_url, href))
        target = _target_from_link(absolute)
        if target is not None:
            _add(target, anchor.get_text(" ", strip=True))

    text = soup.get_text(" ")
    for match in _ONION_SCAN_RE.finditer(text):
        _add(match.group(0).lower(), None)
    for match in _I2P_SCAN_RE.finditer(text):
        _add(match.group(0).lower(), None)

    return out


def _extract_meta_description(html: bytes | str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all("meta"):
        name = (tag.get("name") or tag.get("property") or "").strip().lower()
        if name in ("description", "og:description", "twitter:description"):
            content = tag.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()[:512]
    return None


# --- bounded GET ------------------------------------------------------------


class _FetchError(Exception):
    """A bounded GET failed, with a coarse ``reason`` for the UI.

    The reason drives the Search tab's two-way "all sources failed" empty
    state (Tor-down vs. engine-down) and the per-source badge ("error" vs.
    "timed out"). Kept deliberately coarse — the analyst needs a direction to
    look, not a stack trace.

    Reasons:
      * ``connection`` — couldn't reach the host (proxy/transport error). The
        likely culprit is Tor, so the UI nudges toward "is Tor running?".
      * ``timeout``    — the host accepted but didn't answer in time.
      * ``unreadable`` — the host answered but the body was non-HTML or over
        the size cap; the engine is up but unusable, not a Tor problem.
      * ``invalid``    — the target wasn't a routable .onion (defensive; engine
        URLs are validated on save, so this is effectively probe-only).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def _bounded_get(
    target_url: str, *, tor_proxy: str, i2p_proxy: str
) -> tuple[int, str, bytes]:
    """One GET via the target's network with the harvest-probe limits.

    Routes ``.onion`` through ``tor_proxy`` and ``.i2p`` through ``i2p_proxy``
    (both SOCKS5h). Returns ``(status_code, content_type, body)`` on success;
    raises :class:`_FetchError` with a coarse reason on any failure (host
    invalid, transport error, timeout, content-type rejection, or size cap).
    """
    try:
        network, _ = validate_network_url(target_url)
    except EgressError:
        raise _FetchError("invalid")
    host = (urlsplit(target_url).hostname or "").lower()
    proxy = i2p_proxy if network == "i2p" else tor_proxy

    timeout = aiohttp.ClientTimeout(total=_PROBE_TIMEOUT_SECONDS)
    try:
        session_ctx = make_tor_session(host, proxy=proxy, timeout=timeout)
    except (EgressError, ValueError):
        raise _FetchError("invalid")
    try:
        async with session_ctx as session:
            async with session.get(target_url, allow_redirects=False) as resp:
                content_type = resp.headers.get("Content-Type", "")
                if not is_parseable_content_type(content_type):
                    raise _FetchError("unreadable")
                buf = bytearray()
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    buf.extend(chunk)
                    if len(buf) > _PROBE_MAX_BYTES:
                        raise _FetchError("unreadable")
                return resp.status, content_type, bytes(buf)
    except asyncio.TimeoutError:
        raise _FetchError("timeout")
    except aiohttp.ClientError:
        raise _FetchError("connection")
    except _FetchError:
        raise
    except Exception:  # noqa: BLE001
        log.exception("harvest probe failed for %s", target_url)
        raise _FetchError("connection")


# --- per-engine + probe stages ---------------------------------------------


async def _fetch_engine_links(
    engine_url: str, q: str, *, tor_proxy: str, i2p_proxy: str
) -> list[tuple[str, str | None]]:
    """Result links for one engine, priming its search form if a bare GET is
    bounced.

    A direct query GET works for naive engines. When it yields nothing — the
    signature of a bot-gate that 302-bounced us to the homepage — we fetch the
    engine's homepage, scrape the search form's hidden fields, and re-issue the
    query carrying them, exactly as the form would. The prime fetch stays on the
    same host (and thus the same isolated circuit) as the query. Raises
    :class:`_FetchError` if the query fetch itself fails.
    """
    target = _substitute_query(engine_url, q)
    _status, _ct, body = await _bounded_get(
        target, tor_proxy=tor_proxy, i2p_proxy=i2p_proxy
    )
    links = _extract_result_links(body, target)
    if links:
        return links

    parts = urlsplit(engine_url)
    homepage = urlunsplit((parts.scheme, parts.netloc, "/", "", ""))
    try:
        _status, _ct, home_body = await _bounded_get(
            homepage, tor_proxy=tor_proxy, i2p_proxy=i2p_proxy
        )
    except _FetchError:
        return links
    hidden = _search_form_hidden_fields(home_body)
    if not hidden:
        return links

    primed = _append_params(target, hidden)
    _status, _ct, body = await _bounded_get(
        primed, tor_proxy=tor_proxy, i2p_proxy=i2p_proxy
    )
    return _extract_result_links(body, primed)


async def _query_engine(
    engine: dict[str, Any],
    *,
    q: str,
    tor_proxy: str,
    i2p_proxy: str,
    out: asyncio.Queue[bytes],
    crawled_meta: dict[str, dict[str, Any]],
    probe_candidates: set[str],
) -> None:
    await out.put(
        _sse(
            {"type": "status", "engine": engine["label"], "state": "connecting"}
        )
    )
    try:
        links = await _fetch_engine_links(
            str(engine["url"]), q, tor_proxy=tor_proxy, i2p_proxy=i2p_proxy
        )
    except _FetchError as exc:
        await out.put(
            _sse(
                {
                    "type": "error",
                    "engine": engine["label"],
                    "message": "fetch failed",
                    "reason": exc.reason,
                }
            )
        )
        return
    count = 0
    for absolute_url, anchor_text in links:
        meta = crawled_meta.get(absolute_url)
        result: dict[str, Any] = {
            "engine": engine["label"],
            "url": absolute_url,
            "crawled": meta is not None,
            "anchor_text": anchor_text or None,
        }
        if meta is not None:
            # Already crawled — carry the node id (so "→ Graph" can highlight)
            # plus the title/category/last-seen the result row shows. No probe
            # needed; this is local DB state.
            result["node_id"] = meta["id"]
            result["title"] = meta["title"]
            result["category"] = meta["category"]
            result["last_seen"] = meta["last_seen"]
        else:
            probe_candidates.add(absolute_url)
        await out.put(_sse(result))
        count += 1
    await out.put(
        _sse({"type": "done", "engine": engine["label"], "count": count})
    )


async def _probe_unknowns(
    urls: list[str],
    *,
    tor_proxy: str,
    i2p_proxy: str,
    out: asyncio.Queue[bytes],
) -> None:
    sem = asyncio.Semaphore(_PROBE_CONCURRENCY)

    async def _one(url: str) -> None:
        async with sem:
            try:
                _status_code, _ct, body = await _bounded_get(
                    url, tor_proxy=tor_proxy, i2p_proxy=i2p_proxy
                )
            except _FetchError:
                # A probe that can't be reached/read just stays a bare URL row
                # in the UI — no error event, the result is still actionable.
                return
            try:
                title_result = parse_html(body, base_url=url)
            except Exception:  # noqa: BLE001
                return
            description = _extract_meta_description(body)
            await out.put(
                _sse(
                    {
                        "type": "probe",
                        "url": url,
                        "title": title_result.title,
                        "description": description,
                    }
                )
            )

    await asyncio.gather(*(_one(u) for u in urls))


# --- route ------------------------------------------------------------------


@router.get("/api/harvest/search")
async def harvest_search(
    request: Request,
    q: str = "",
    engines: str = "",
    db: CrawlDB = Depends(get_active_db),
) -> Any:
    query = q.strip()
    if not query:
        return JSONResponse(
            {"error": "missing_query"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if len(query) > _QUERY_MAX_LEN:
        return JSONResponse(
            {"error": "query_too_long"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    selected_ids = _parse_engine_ids(engines)
    engine_list = _enabled_engines(db)
    if selected_ids is not None:
        # Per-session source override — intersect with enabled so a deselected
        # or stale id is never queried.
        engine_list = [e for e in engine_list if e["id"] in selected_ids]
    tor_proxy = get_setting(db, "tor.proxy") or _DEFAULT_PROXY
    i2p_proxy = get_setting(db, "i2p.proxy") or _DEFAULT_I2P_PROXY
    allow_i2p = i2p_enabled(db)
    # I2P engines require I2P egress — drop them when it's off rather than fail
    # each query. (Onion engines may still surface .i2p links in their results;
    # those just don't get probed below.)
    if not allow_i2p:
        engine_list = [e for e in engine_list if e.get("network") != "i2p"]
    crawled_meta = resources_db.crawled_meta_by_url(db)
    # When passive mode is on, engine queries still run and URL results still
    # stream, but the per-URL probe stage is skipped — the analyst opted out
    # of having the app contact discovered onions during search.
    passive = (
        (get_setting(db, "search.passive_mode") or "false").strip().lower()
        == "true"
    )
    kill_switch = request.app.state.kill_switch

    if not engine_list:
        async def _empty_stream() -> AsyncIterator[bytes]:
            yield _sse({"type": "all_done", "reason": "no_engines"})

        return StreamingResponse(
            _empty_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    out: asyncio.Queue[bytes] = asyncio.Queue(maxsize=512)
    probe_candidates: set[str] = set()

    async def _drive() -> None:
        try:
            engine_tasks = [
                asyncio.create_task(
                    _query_engine(
                        engine,
                        q=query,
                        tor_proxy=tor_proxy,
                        i2p_proxy=i2p_proxy,
                        out=out,
                        crawled_meta=crawled_meta,
                        probe_candidates=probe_candidates,
                    ),
                    name=f"harvest_engine_{engine['id']}",
                )
                for engine in engine_list
            ]
            for task in engine_tasks:
                kill_switch.register_task(task)
            await asyncio.gather(*engine_tasks, return_exceptions=True)

            # Probe discovered unknowns. I2P targets need I2P egress, so drop
            # them when it's off rather than route them at a dead proxy.
            to_probe = sorted(
                u for u in probe_candidates
                if allow_i2p or ONION_URL_RE.match(u)
            )
            if to_probe and not passive:
                probe_task = asyncio.create_task(
                    _probe_unknowns(
                        to_probe, tor_proxy=tor_proxy, i2p_proxy=i2p_proxy, out=out
                    ),
                    name="harvest_probes",
                )
                kill_switch.register_task(probe_task)
                try:
                    await probe_task
                except Exception:  # noqa: BLE001
                    log.exception("harvest probes failed")

            await out.put(_sse({"type": "all_done"}))
        finally:
            await out.put(b"")  # consumer-side break sentinel

    driver = asyncio.create_task(_drive(), name="harvest_drive")

    async def _stream() -> AsyncIterator[bytes]:
        try:
            while True:
                event = await out.get()
                if event == b"":
                    break
                yield event
        finally:
            if not driver.done():
                driver.cancel()
                try:
                    await driver
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = ["router"]
