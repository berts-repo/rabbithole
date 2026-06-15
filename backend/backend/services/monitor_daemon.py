"""Uptime monitor probe loop.

PLAN.md:320. Single-instance per process (sibling of ``CrawlQueueRunner``).
Each tick walks enabled monitors and issues a HEAD probe via Tor for any
that are due. Probe results land in the ``probes`` table (atomic with the
paired ``kind='probe'`` job that surfaces in the Activity view) and are
broadcast on ``monitor.probed`` so the right-panel Domain tab can refresh
without polling, plus ``jobs.changed`` for the Activity stream.

Respects the kill switch: a tick that begins after the switch engages is
a no-op; an in-flight tick that observes the switch flips between probes
breaks out early.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, TYPE_CHECKING
from urllib.parse import urlparse

import aiohttp

from ..crawler.parser import is_parseable_content_type, parse_html
from ..db import monitors as monitors_db
from ..db import page_versions as versions_db
from ..db.settings import get_setting
from ..security.net import EgressError, make_tor_session
from .event_bus import EventBus

if TYPE_CHECKING:
    from .kill_switch import KillSwitch
    from .project_state import ProjectState


log = logging.getLogger(__name__)


_TICK_INTERVAL_SECONDS = 60.0
_PROBE_TIMEOUT_SECONDS = 10.0
_DEFAULT_PROXY = "socks5h://127.0.0.1:9050"
# Cap the body a content-tracking probe will read + hash. Oversized or
# non-parseable responses fall back to status-only (body_hash = None).
_MAX_PROBE_BODY_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class _ProbeResult:
    """Outcome of one probe: the HTTP status and, when the monitor tracks
    content, the clean-text hash of the body (``None`` otherwise)."""

    status_code: int | None
    body_hash: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


SessionFactory = Callable[..., aiohttp.ClientSession]


def _default_session_factory(
    target_host: str, *, proxy: str, timeout: aiohttp.ClientTimeout
) -> aiohttp.ClientSession:
    return make_tor_session(target_host, proxy=proxy, timeout=timeout)


@dataclass
class MonitorDaemon:
    """Polls ``monitors`` and writes ``probes`` rows for due monitors."""

    project_state: "ProjectState"
    kill_switch: "KillSwitch"
    event_bus: EventBus
    session_factory: SessionFactory = field(default=_default_session_factory)
    sleep_fn: Callable[[float], Awaitable[None]] = field(default=asyncio.sleep)
    clock: Callable[[], datetime] = field(default=_now)
    tick_interval: float = _TICK_INTERVAL_SECONDS
    probe_timeout: float = _PROBE_TIMEOUT_SECONDS

    _loop_task: Optional[asyncio.Task] = None
    _stopping: bool = False

    # -- single tick ------------------------------------------------------

    async def _tick(self) -> int:
        """One pass over enabled monitors. Returns the number of probes issued."""
        db = self.project_state.active_db
        if db is None:
            return 0
        if self.kill_switch.engaged.is_set():
            return 0

        proxy = get_setting(db, "tor.proxy") or _DEFAULT_PROXY
        now_dt = self.clock()
        now_iso = now_dt.isoformat(timespec="seconds")

        probes = 0
        for monitor in monitors_db.list_monitors(db):
            if self.kill_switch.engaged.is_set():
                break
            # Re-read row in case the analyst disabled it mid-tick.
            current = monitors_db.get_monitor(db, int(monitor["id"]))
            if current is None or not current.get("enabled"):
                continue

            last = monitors_db.latest_probe(db, int(current["id"]))
            if last is not None:
                last_dt = _parse_iso(last["checked_at"])
                if last_dt is not None:
                    elapsed_hours = (
                        now_dt - last_dt
                    ).total_seconds() / 3600.0
                    if elapsed_hours < float(current["interval_hours"]):
                        continue

            # Track content only when the monitor asks for change alerts; an
            # uptime-only monitor stays a cheap HEAD probe.
            track_content = bool(current.get("alert_on_change", True))
            result = await self._probe(
                current["url"], proxy, track_content=track_content
            )
            # content_changed compares this probe's hash to the prior probe's.
            # No prior hash (first content probe / tracking just enabled) →
            # None ("unknown"), not a spurious "changed".
            prior_hash = last["body_hash"] if last is not None else None
            content_changed: int | None = None
            if result.body_hash is not None and prior_hash is not None:
                content_changed = 1 if result.body_hash != prior_hash else 0

            job_id = monitors_db.record_probe(
                db,
                int(current["id"]),
                url=current["url"],
                checked_at=now_iso,
                status_code=result.status_code,
                body_hash=result.body_hash,
                content_changed=content_changed,
            )
            self.event_bus.publish(
                "monitor.probed",
                {
                    "monitor_id": int(current["id"]),
                    "url": current["url"],
                    "status_code": result.status_code,
                    "content_changed": (
                        bool(content_changed) if content_changed is not None else None
                    ),
                    "checked_at": now_iso,
                },
            )
            # The probe is also a unit of work in the unified Activity view.
            self.event_bus.publish(
                "jobs.changed",
                {"job_id": job_id, "kind": "probe", "status": "done"},
            )
            probes += 1
        return probes

    async def _probe(
        self, url: str, proxy: str, *, track_content: bool = False
    ) -> _ProbeResult:
        """Probe ``url`` via Tor.

        Uptime monitors (``track_content=False``) issue a cheap HEAD and return
        just the status. Content monitors issue a GET, and on a 2xx parseable
        response hash the clean text (same hash as ``page_versions``) so the
        caller can detect drift. Any transport failure → status ``None``.
        """
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if not host:
            return _ProbeResult(None)
        try:
            timeout = aiohttp.ClientTimeout(total=self.probe_timeout)
            session_ctx = self.session_factory(host, proxy=proxy, timeout=timeout)
        except (EgressError, ValueError):
            return _ProbeResult(None)
        try:
            async with session_ctx as session:
                if not track_content:
                    async with session.head(url, allow_redirects=False) as resp:
                        return _ProbeResult(int(resp.status))
                async with session.get(url, allow_redirects=False) as resp:
                    status = int(resp.status)
                    if not (200 <= status < 300):
                        return _ProbeResult(status)
                    if not is_parseable_content_type(
                        resp.headers.get("Content-Type")
                    ):
                        return _ProbeResult(status)
                    raw = await resp.content.read(_MAX_PROBE_BODY_BYTES + 1)
                    if len(raw) > _MAX_PROBE_BODY_BYTES:
                        return _ProbeResult(status)  # oversized → status only
                    clean = parse_html(raw).body_text_clean
                    return _ProbeResult(status, versions_db.hash_clean_text(clean))
        except Exception as exc:  # noqa: BLE001 — any transport failure → None
            log.debug("monitor probe failed for %s: %s", url, exc)
            return _ProbeResult(None)

    # -- lifecycle --------------------------------------------------------

    async def _run(self) -> None:
        try:
            while not self._stopping:
                try:
                    await self._tick()
                except Exception:  # noqa: BLE001 — never let the loop die
                    log.exception("monitor daemon tick failed")
                await self.sleep_fn(self.tick_interval)
        except asyncio.CancelledError:
            return

    async def start(self) -> None:
        if self._loop_task is not None:
            return
        self._stopping = False
        self._loop_task = asyncio.create_task(self._run(), name="monitor_daemon")

    async def stop(self) -> None:
        self._stopping = True
        if self._loop_task is None:
            return
        self._loop_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._loop_task
        self._loop_task = None


__all__ = ["MonitorDaemon"]
