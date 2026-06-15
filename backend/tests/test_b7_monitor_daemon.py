"""Phase B7g — monitor daemon tick semantics."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from backend.db import monitors as monitors_db
from backend.db.core import CrawlDB
from backend.services.event_bus import EventBus
from backend.services.graph_cache import GraphCache
from backend.services.monitor_daemon import MonitorDaemon


URL_A = "http://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.onion/"
URL_B = "http://bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.onion/"
URL_C = "http://cccccccccccccccccccccccccccccccccccccccccccccccccccccccc.onion/"


class _FakeKillSwitch:
    def __init__(self) -> None:
        self.engaged = asyncio.Event()


class _FakeProjectState:
    def __init__(self, db: CrawlDB | None) -> None:
        self.active_db = db
        self.graph_cache = GraphCache()


class _FakeContent:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self, n: int = -1) -> bytes:
        return self._data


class _FakeResponse:
    def __init__(
        self, status: int, *, body: bytes = b"", content_type: str = "text/html"
    ) -> None:
        self.status = status
        self.headers = {"Content-Type": content_type}
        self.content = _FakeContent(body)

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class _FakeSession:
    """Captures every probe + mimics aiohttp's async context manager shape.

    Content monitors (``alert_on_change`` true, the default) issue GET and read
    the body; uptime-only monitors issue HEAD. Both are recorded.
    """

    def __init__(
        self,
        *,
        status_map: dict[str, int] | None = None,
        body_map: dict[str, bytes] | None = None,
        raise_for: set[str] | None = None,
        on_probe: Any = None,
    ) -> None:
        self.status_map = status_map or {}
        self.body_map = body_map or {}
        self.raise_for = raise_for or set()
        self.on_probe = on_probe  # optional callable for mid-loop hooks
        self.probes: list[str] = []
        self.gets: list[str] = []
        self.heads: list[str] = []

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def _record(self, url: str) -> None:
        self.probes.append(url)
        if self.on_probe is not None:
            self.on_probe(url)
        if url in self.raise_for:
            raise RuntimeError("probe blew up")

    def head(self, url: str, *, allow_redirects: bool = False):
        self.heads.append(url)
        self._record(url)
        return _FakeResponse(self.status_map.get(url, 200))

    def get(self, url: str, *, allow_redirects: bool = False):
        self.gets.append(url)
        self._record(url)
        return _FakeResponse(
            self.status_map.get(url, 200),
            body=self.body_map.get(url, b"<html><body>default</body></html>"),
        )


@pytest.fixture
def db(tmp_path: Path):
    instance = CrawlDB(tmp_path / "monitor_daemon.db")
    try:
        yield instance
    finally:
        instance.close()


def _daemon(
    db: CrawlDB | None,
    *,
    clock_value: datetime,
    session: _FakeSession,
    event_bus: EventBus | None = None,
):
    bus = event_bus or EventBus()

    def factory(target_host, *, proxy, timeout):
        return session

    daemon = MonitorDaemon(
        project_state=_FakeProjectState(db),  # type: ignore[arg-type]
        kill_switch=_FakeKillSwitch(),  # type: ignore[arg-type]
        event_bus=bus,
        session_factory=factory,
        clock=lambda: clock_value,
    )
    return daemon, bus


async def test_tick_skips_when_no_active_db():
    session = _FakeSession()
    daemon, _ = _daemon(
        None, clock_value=datetime.now(timezone.utc), session=session
    )
    fired = await daemon._tick()
    assert fired == 0
    assert session.probes == []


async def test_tick_skips_when_kill_switch_engaged(db):
    monitors_db.create_monitor(
        db, url=URL_A, label=None, interval_hours=0.25
    )
    session = _FakeSession()
    daemon, _ = _daemon(
        db, clock_value=datetime.now(timezone.utc), session=session
    )
    daemon.kill_switch.engaged.set()  # type: ignore[attr-defined]
    fired = await daemon._tick()
    assert fired == 0
    assert session.probes == []


async def test_tick_skips_disabled_monitor(db):
    mid = monitors_db.create_monitor(
        db, url=URL_A, label=None, interval_hours=0.25
    )
    monitors_db.update_monitor(db, mid, enabled=False)
    session = _FakeSession()
    daemon, _ = _daemon(
        db, clock_value=datetime.now(timezone.utc), session=session
    )
    fired = await daemon._tick()
    assert fired == 0


async def test_tick_skips_monitor_within_interval(db):
    mid = monitors_db.create_monitor(
        db, url=URL_A, label=None, interval_hours=4.0
    )
    last_probe = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
    monitors_db.record_probe(
        db, mid, url=URL_A, checked_at=last_probe.isoformat(), status_code=200
    )
    # Tick fires 1 hour later — still within the 4-hour interval.
    session = _FakeSession()
    daemon, _ = _daemon(
        db,
        clock_value=last_probe + timedelta(hours=1),
        session=session,
    )
    fired = await daemon._tick()
    assert fired == 0
    assert session.probes == []


async def test_probes_due_monitor_records_row_and_event(db):
    mid = monitors_db.create_monitor(
        db, url=URL_A, label=None, interval_hours=0.25
    )
    now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
    session = _FakeSession(status_map={URL_A: 200})
    daemon, bus = _daemon(db, clock_value=now, session=session)

    received: list[dict[str, Any]] = []

    async def collector():
        async for envelope in bus.subscribe("monitor.probed"):
            received.append(envelope)

    listener = asyncio.create_task(collector())
    # Yield once so the subscriber registers before publish runs.
    await asyncio.sleep(0)
    fired = await daemon._tick()
    # Yield so the queued events drain into the collector.
    await asyncio.sleep(0)
    listener.cancel()
    try:
        await listener
    except asyncio.CancelledError:
        pass

    assert fired == 1
    monitor = monitors_db.get_monitor(db, mid)
    assert monitor["last_status"] == 200
    latest = monitors_db.latest_probe(db, mid)
    assert latest["status_code"] == 200
    # Event published with the right payload.
    assert any(
        env["monitor_id"] == mid and env["status_code"] == 200
        for env in received
    )


async def test_records_none_on_request_exception(db):
    mid = monitors_db.create_monitor(
        db, url=URL_A, label=None, interval_hours=0.25
    )
    session = _FakeSession(raise_for={URL_A})
    daemon, _ = _daemon(
        db, clock_value=datetime.now(timezone.utc), session=session
    )
    fired = await daemon._tick()
    assert fired == 1
    latest = monitors_db.latest_probe(db, mid)
    assert latest["status_code"] is None
    assert monitors_db.get_monitor(db, mid)["last_status"] is None


async def test_disable_stops_probes_mid_loop(db):
    """Toggling a monitor's ``enabled`` to False between probes must stop it
    from being probed even if it's already in the iteration list."""
    mid_a = monitors_db.create_monitor(
        db, url=URL_A, label=None, interval_hours=0.25
    )
    mid_b = monitors_db.create_monitor(
        db, url=URL_B, label=None, interval_hours=0.25
    )
    mid_c = monitors_db.create_monitor(
        db, url=URL_C, label=None, interval_hours=0.25
    )

    def on_probe(url: str) -> None:
        # list_monitors returns rows id DESC (newest first) → iteration order
        # is C, B, A. After C is probed, disable B so the daemon's per-row
        # re-read catches the change before its turn comes.
        if url == URL_C:
            monitors_db.update_monitor(db, mid_b, enabled=False)

    session = _FakeSession(on_probe=on_probe)
    daemon, _ = _daemon(
        db, clock_value=datetime.now(timezone.utc), session=session
    )
    fired = await daemon._tick()

    # A and C were probed; B was skipped.
    assert URL_A in session.probes
    assert URL_C in session.probes
    assert URL_B not in session.probes
    assert fired == 2
    # No probe row written for B.
    assert monitors_db.latest_probe(db, mid_b) is None
    # last_status untouched on B.
    assert monitors_db.get_monitor(db, mid_b)["last_status"] is None
    # A and C did write probes.
    assert monitors_db.latest_probe(db, mid_a) is not None
    assert monitors_db.latest_probe(db, mid_c) is not None


async def test_content_change_detected_across_probes(db):
    """A second probe whose body differs from the first flags content_changed."""
    mid = monitors_db.create_monitor(
        db, url=URL_A, label=None, interval_hours=0.25
    )
    t0 = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)

    # First probe — body v1. No prior hash → content_changed is None.
    s1 = _FakeSession(body_map={URL_A: b"<html><body>version one</body></html>"})
    d1, _ = _daemon(db, clock_value=t0, session=s1)
    await d1._tick()
    assert s1.gets == [URL_A] and s1.heads == []  # content monitor uses GET
    p1 = monitors_db.latest_probe(db, mid)
    assert p1["body_hash"] is not None
    assert p1["content_changed"] is None

    # Second probe an hour later — body v2 differs → content_changed True.
    s2 = _FakeSession(body_map={URL_A: b"<html><body>version TWO</body></html>"})
    d2, _ = _daemon(db, clock_value=t0 + timedelta(hours=1), session=s2)
    await d2._tick()
    p2 = monitors_db.latest_probe(db, mid)
    assert p2["content_changed"] is True
    assert monitors_db.get_monitor(db, mid)["last_content_changed"] is True


async def test_content_unchanged_across_probes(db):
    """Identical bodies across two probes report content_changed False."""
    mid = monitors_db.create_monitor(
        db, url=URL_A, label=None, interval_hours=0.25
    )
    t0 = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
    body = b"<html><body>steady</body></html>"

    d1, _ = _daemon(db, clock_value=t0, session=_FakeSession(body_map={URL_A: body}))
    await d1._tick()
    d2, _ = _daemon(
        db,
        clock_value=t0 + timedelta(hours=1),
        session=_FakeSession(body_map={URL_A: body}),
    )
    await d2._tick()
    assert monitors_db.latest_probe(db, mid)["content_changed"] is False
    assert monitors_db.get_monitor(db, mid)["last_content_changed"] is False


async def test_uptime_only_monitor_uses_head(db):
    """A monitor with alert_on_change off stays a status-only HEAD probe."""
    mid = monitors_db.create_monitor(
        db, url=URL_A, label=None, interval_hours=0.25, alert_on_change=False
    )
    session = _FakeSession(status_map={URL_A: 200})
    daemon, _ = _daemon(
        db, clock_value=datetime.now(timezone.utc), session=session
    )
    await daemon._tick()
    assert session.heads == [URL_A] and session.gets == []
    latest = monitors_db.latest_probe(db, mid)
    assert latest["status_code"] == 200
    assert latest["body_hash"] is None
    assert latest["content_changed"] is None


async def test_tick_skips_when_session_factory_raises(db):
    """A misconfigured proxy (validate_tor_proxy raises) must not crash the loop."""
    monitors_db.create_monitor(
        db, url=URL_A, label=None, interval_hours=0.25
    )

    def bad_factory(target_host, *, proxy, timeout):
        raise ValueError("bad proxy")

    daemon = MonitorDaemon(
        project_state=_FakeProjectState(db),  # type: ignore[arg-type]
        kill_switch=_FakeKillSwitch(),  # type: ignore[arg-type]
        event_bus=EventBus(),
        session_factory=bad_factory,
        clock=lambda: datetime.now(timezone.utc),
    )
    fired = await daemon._tick()
    # The probe attempt still counts (we wrote None) — that's expected; the
    # important thing is the loop didn't crash.
    assert fired == 1
