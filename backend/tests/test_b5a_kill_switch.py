"""Phase B5a — Tor probe + event bus + kill switch.

These tests drive ``KillSwitch`` synchronously via ``_tick`` rather than the
background loop, so engagement / clear / cancellation behavior is fully
deterministic. The route-level test uses the ``auth_client`` fixture and
asserts ``snapshot()`` returns the right shape — we don't need lifespan to
have run, because ``create_app()`` constructs the kill switch eagerly.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

import pytest

from backend.crawler.tor import probe_tor
from backend.services.event_bus import EventBus
from backend.services.kill_switch import KillSwitch, _ProjectSettings


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


async def _collect(bus: EventBus, channel: str, count: int) -> list[dict]:
    out: list[dict] = []
    async for event in bus.subscribe(channel):
        out.append(event)
        if len(out) >= count:
            break
    return out


async def test_event_bus_publishes_to_subscribers():
    bus = EventBus()
    sub = asyncio.create_task(_collect(bus, "crawl.log", 2))
    await asyncio.sleep(0.01)
    bus.publish("crawl.log", {"message": "a"})
    bus.publish("crawl.log", {"message": "b"})
    events = await asyncio.wait_for(sub, timeout=1.0)
    assert [e["message"] for e in events] == ["a", "b"]
    # Every envelope carries the channel + a timestamp.
    assert all(e["channel"] == "crawl.log" for e in events)
    assert all("ts" in e for e in events)


async def test_event_bus_drops_oldest_on_overflow_and_emits_dropped_sentinel():
    """A slow consumer never blocks the producer; oldest events fall off."""
    bus = EventBus()

    received: list[dict] = []

    async def slow_consumer():
        async for event in bus.subscribe("crawl.log"):
            received.append(event)
            # Two real events + one _dropped sentinel between them.
            if sum(1 for e in received if e.get("type") == "_dropped") >= 1 and len(received) >= 3:
                return

    consumer = asyncio.create_task(slow_consumer())
    await asyncio.sleep(0.01)  # let the subscribe set up

    # Fill past the cap. _QUEUE_MAX = 256; push 260.
    for i in range(260):
        bus.publish("crawl.log", {"message": f"m{i}"})

    await asyncio.wait_for(consumer, timeout=2.0)

    dropped_events = [e for e in received if e.get("type") == "_dropped"]
    assert dropped_events, "consumer never saw the _dropped sentinel"
    assert dropped_events[0]["count"] >= 1


async def test_event_bus_log_buffer_caps_at_200():
    bus = EventBus()
    for i in range(500):
        bus.publish("crawl.log", {"message": f"line-{i}"})
    snap = bus.log_buffer_snapshot()
    assert len(snap) == 200
    # Newest entries are retained, oldest fall off.
    assert snap[-1]["message"] == "line-499"
    assert snap[0]["message"] == "line-300"


async def test_event_bus_other_channels_are_not_buffered():
    bus = EventBus()
    bus.publish("crawl.status", {"pages_crawled": 1})
    # ``crawl.status`` is live-only; only ``crawl.log`` populates the buffer.
    assert bus.log_buffer_snapshot() == []


# ---------------------------------------------------------------------------
# probe_tor
# ---------------------------------------------------------------------------


async def test_probe_tor_succeeds_on_listening_socket():
    """Spin up an ephemeral loopback listener and confirm probe_tor connects."""

    async def _noop(_reader, writer):
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(_noop, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        result = await probe_tor(f"socks5h://127.0.0.1:{port}")
        assert result["ok"] is True
        assert result["error"] is None
        assert isinstance(result["latency_ms"], int)
    finally:
        server.close()
        await server.wait_closed()


async def test_probe_tor_reports_failure_when_nothing_listens():
    # Pick a port that's almost certainly closed. We can't guarantee zero
    # collision, but 1 is a safe choice on unprivileged hosts.
    result = await probe_tor("socks5h://127.0.0.1:1")
    assert result["ok"] is False
    assert result["error"] is not None


async def test_probe_tor_rejects_non_loopback_proxy():
    result = await probe_tor("socks5h://10.0.0.1:9050")
    assert result["ok"] is False
    assert result["error"] is not None
    assert "bad_proxy" in result["error"]


# ---------------------------------------------------------------------------
# KillSwitch
# ---------------------------------------------------------------------------


@dataclass
class _FakeState:
    """Stand-in for ProjectState that only exposes what KillSwitch reads."""

    active_db: Optional[object] = None


def _make_switch(
    *,
    settings: Optional[_ProjectSettings],
    probe_results: list[dict],
) -> KillSwitch:
    bus = EventBus()
    results_iter = iter(probe_results)

    async def fake_probe(_proxy: str) -> dict:
        try:
            return next(results_iter)
        except StopIteration:
            # Once we're out of canned results, keep returning the last one.
            return probe_results[-1]

    async def fake_sleep(_seconds: float) -> None:
        # We never enter the production loop in tests; this is just for safety.
        return None

    return KillSwitch(
        project_state=_FakeState(active_db=object()),  # type: ignore[arg-type]
        event_bus=bus,
        probe_fn=fake_probe,
        sleep_fn=fake_sleep,
        settings_reader=lambda _state: settings,
    )


async def test_kill_switch_does_not_engage_before_threshold():
    ks = _make_switch(
        settings=_ProjectSettings(proxy="socks5h://127.0.0.1:9050", kill_switch_active=True),
        probe_results=[
            {"ok": False, "latency_ms": None, "error": "x"},
            {"ok": False, "latency_ms": None, "error": "x"},
        ],
    )
    await ks._tick()
    await ks._tick()
    assert not ks.engaged.is_set()


async def test_kill_switch_engages_after_three_failures_and_cancels_tasks():
    ks = _make_switch(
        settings=_ProjectSettings(proxy="socks5h://127.0.0.1:9050", kill_switch_active=True),
        probe_results=[{"ok": False, "latency_ms": None, "error": "x"}] * 3,
    )

    long_task = asyncio.create_task(asyncio.sleep(60))
    ks.register_task(long_task)

    await ks._tick()
    await ks._tick()
    await ks._tick()
    assert ks.engaged.is_set()

    # The registered task must be cancelled within a tick.
    await asyncio.sleep(0)  # yield so cancellation propagates
    assert long_task.cancelled() or long_task.done()
    with pytest.raises(asyncio.CancelledError):
        await long_task


async def test_kill_switch_banner_only_when_setting_off():
    """tor.kill_switch=false → engaged is set but tasks are NOT cancelled."""
    ks = _make_switch(
        settings=_ProjectSettings(proxy="socks5h://127.0.0.1:9050", kill_switch_active=False),
        probe_results=[{"ok": False, "latency_ms": None, "error": "x"}] * 3,
    )

    long_task = asyncio.create_task(asyncio.sleep(0.2))
    ks.register_task(long_task)

    banner_events: list[dict] = []

    async def watch():
        async for event in ks.event_bus.subscribe("kill_switch.banner"):
            banner_events.append(event)
            return

    watcher = asyncio.create_task(watch())
    await asyncio.sleep(0.01)

    await ks._tick()
    await ks._tick()
    await ks._tick()

    await asyncio.wait_for(watcher, timeout=1.0)
    assert banner_events and banner_events[0]["reason"] == "tor_down"

    # Task continues to run.
    assert not long_task.cancelled()
    await long_task


async def test_kill_switch_clears_on_recovery():
    ks = _make_switch(
        settings=_ProjectSettings(proxy="socks5h://127.0.0.1:9050", kill_switch_active=True),
        probe_results=[
            {"ok": False, "latency_ms": None, "error": "x"},
            {"ok": False, "latency_ms": None, "error": "x"},
            {"ok": False, "latency_ms": None, "error": "x"},
            {"ok": True, "latency_ms": 5, "error": None},
        ],
    )

    clear_seen = asyncio.Event()

    async def watch():
        async for _ in ks.event_bus.subscribe("kill_switch.clear"):
            clear_seen.set()
            return

    watcher = asyncio.create_task(watch())
    await asyncio.sleep(0.01)

    await ks._tick()
    await ks._tick()
    await ks._tick()
    assert ks.engaged.is_set()

    await ks._tick()  # recovery
    assert not ks.engaged.is_set()
    await asyncio.wait_for(clear_seen.wait(), timeout=1.0)
    await watcher


async def test_kill_switch_idles_when_no_active_project():
    ks = _make_switch(
        settings=None,
        probe_results=[{"ok": False, "latency_ms": None, "error": "x"}],
    )
    await ks._tick()
    assert not ks.engaged.is_set()
    assert ks.last_probe is None


async def test_kill_switch_resets_failure_counter_on_success():
    """Two failures + one success + two more failures → still not engaged."""
    ks = _make_switch(
        settings=_ProjectSettings(proxy="socks5h://127.0.0.1:9050", kill_switch_active=True),
        probe_results=[
            {"ok": False, "latency_ms": None, "error": "x"},
            {"ok": False, "latency_ms": None, "error": "x"},
            {"ok": True, "latency_ms": 5, "error": None},
            {"ok": False, "latency_ms": None, "error": "x"},
            {"ok": False, "latency_ms": None, "error": "x"},
        ],
    )
    for _ in range(5):
        await ks._tick()
    assert not ks.engaged.is_set()


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


def test_tor_status_route_returns_snapshot(auth_client, app):
    app.state.kill_switch.last_probe = {"ok": True, "latency_ms": 12, "error": None}
    resp = auth_client.get("/api/tor/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "ok": True,
        "latency_ms": 12,
        "error": None,
        "engaged": False,
        "consecutive_failures": 0,
    }


def test_tor_status_route_defaults_when_no_probe_run_yet(auth_client, app):
    # Fresh app — kill_switch hasn't probed (lifespan didn't run under TestClient).
    resp = auth_client.get("/api/tor/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"] == "no_probe"


def test_tor_status_route_requires_auth(client):
    # No cookie → middleware rejects. GET is a safe method so Origin is
    # not required; the cookie is the gate.
    resp = client.get("/api/tor/status")
    assert resp.status_code == 401
