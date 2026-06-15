"""Shared kill switch.

PLAN.md:291 — Tor health is probed every 5 s. When ``tor.kill_switch`` is on
and the probe trips three times in a row, the switch engages: every
registered in-flight task (crawl fetches, monitor probes, harvest probes) is
cancelled via ``Task.cancel()`` so the underlying ``aiohttp`` request aborts
mid-stream. When the setting is off, engagement emits the banner event and
skips that cancellation — in-flight requests are left to finish or fail on
their own. Either way the ``engaged`` event is set, so the crawl loop still
exits (it checks the shared flag between pages); enforcement only controls
whether the in-flight request is aborted mid-stream or allowed to drain.

The switch lives on ``app.state.kill_switch``. Workers in B5d/B7/B8 grab the
shared instance, register their request task, and check ``engaged`` between
units of work (the loop also cancels long-running tasks immediately so they
don't have to poll).

Constructor signature is dependency-injectable: ``probe_fn``, ``sleep_fn``,
and ``settings_reader`` can all be overridden in tests so the loop runs
deterministically with no real sockets and no real wall clock.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional, TYPE_CHECKING

from ..db.settings import get_setting
from .event_bus import EventBus
from ..crawler.tor import probe_tor, TorProbeResult

if TYPE_CHECKING:
    from .project_state import ProjectState


log = logging.getLogger(__name__)

_DEFAULT_PROXY = "socks5h://127.0.0.1:9050"
_DEFAULT_I2P_PROXY = "socks5h://127.0.0.1:4447"
_FAIL_THRESHOLD = 3
_PROBE_INTERVAL_SECONDS = 5.0


@dataclass
class _ProjectSettings:
    proxy: str
    kill_switch_active: bool
    # I2P is only probed when enabled; defaults keep the Tor-only path (and the
    # existing tests that construct this with two args) unchanged.
    i2p_enabled: bool = False
    i2p_proxy: str = _DEFAULT_I2P_PROXY
    i2p_kill_switch_active: bool = True


def _read_settings(project_state: "ProjectState") -> Optional[_ProjectSettings]:
    """Read the relevant settings under the project-state read lock.

    Returns ``None`` if no project is currently active — the switch idles
    until a project comes online. We read synchronously here because
    ``CrawlDB`` is sync; the surrounding async loop yields between ticks.
    """
    db = project_state.active_db
    if db is None:
        return None
    proxy = get_setting(db, "tor.proxy") or _DEFAULT_PROXY
    kill = get_setting(db, "tor.kill_switch")
    i2p_kill = get_setting(db, "i2p.kill_switch")
    return _ProjectSettings(
        proxy=proxy,
        kill_switch_active=(kill or "true").lower() == "true",
        i2p_enabled=(get_setting(db, "i2p.enabled") or "false").lower() == "true",
        i2p_proxy=get_setting(db, "i2p.proxy") or _DEFAULT_I2P_PROXY,
        i2p_kill_switch_active=(i2p_kill or "true").lower() == "true",
    )


@dataclass
class KillSwitch:
    """Shared kill switch + Tor health monitor.

    Test-friendly: construct, drive ``_tick`` directly, inspect ``engaged``
    and ``last_probe``. ``start()``/``stop()`` are only needed for the
    production lifespan path.
    """

    project_state: "ProjectState"
    event_bus: EventBus
    probe_fn: Callable[[str], Awaitable[TorProbeResult]] = field(default=probe_tor)
    sleep_fn: Callable[[float], Awaitable[None]] = field(default=asyncio.sleep)
    probe_interval: float = _PROBE_INTERVAL_SECONDS
    fail_threshold: int = _FAIL_THRESHOLD
    settings_reader: Callable[
        ["ProjectState"], Optional[_ProjectSettings]
    ] = field(default=_read_settings)

    engaged: asyncio.Event = field(default_factory=asyncio.Event)
    last_probe: Optional[TorProbeResult] = None
    last_i2p_probe: Optional[TorProbeResult] = None
    _consec_failures: int = 0
    _i2p_consec_failures: int = 0
    _registered: set[asyncio.Task] = field(default_factory=set)
    _loop_task: Optional[asyncio.Task] = None
    _stopping: bool = False

    # -- registration -----------------------------------------------------

    def register_task(self, task: asyncio.Task) -> None:
        """Track an in-flight network task. Done tasks self-evict."""
        if task.done():
            return
        self._registered.add(task)
        task.add_done_callback(self._registered.discard)

    def _cancel_registered(self) -> int:
        cancelled = 0
        for task in list(self._registered):
            if not task.done():
                task.cancel()
                cancelled += 1
        return cancelled

    # -- snapshot for the route ------------------------------------------

    def snapshot(self) -> dict[str, object]:
        """JSON-shaped view for ``GET /api/tor/status``.

        The top-level fields describe Tor (unchanged shape). When I2P has been
        probed (only happens while ``i2p.enabled`` is on) an ``i2p`` sub-object
        is added; it is absent on a Tor-only project so the existing payload is
        untouched.
        """
        probe = self.last_probe or {"ok": False, "latency_ms": None, "error": "no_probe"}
        snap: dict[str, object] = {
            "ok": bool(probe["ok"]),
            "latency_ms": probe["latency_ms"],
            "error": probe["error"],
            "engaged": self.engaged.is_set(),
            "consecutive_failures": self._consec_failures,
        }
        if self.last_i2p_probe is not None:
            snap["i2p"] = {
                "ok": bool(self.last_i2p_probe["ok"]),
                "latency_ms": self.last_i2p_probe["latency_ms"],
                "error": self.last_i2p_probe["error"],
                "consecutive_failures": self._i2p_consec_failures,
            }
        return snap

    # -- on-demand probe --------------------------------------------------

    async def probe_now(self) -> dict[str, object]:
        """Run a single probe immediately and return the resulting snapshot.

        Exposed via ``POST /api/tor/probe`` so the UI can force a state
        transition (especially the ``kill_switch.clear`` event on recovery)
        without waiting for the next ``_PROBE_INTERVAL_SECONDS`` background
        tick. Safe to call concurrently with the background loop — a
        coincident tick will just overwrite ours with a fresher probe.
        """
        await self._tick()
        return self.snapshot()

    # -- loop --------------------------------------------------------------

    async def _tick(self) -> None:
        """Single iteration: probe Tor, update engagement state.

        Public-ish — tests call this directly to drive the state machine
        without spinning the background loop.
        """
        settings = self.settings_reader(self.project_state)
        if settings is None:
            # No active project → no proxy to probe. Clear any stale state.
            if self.engaged.is_set():
                self._clear()
            self._consec_failures = 0
            self._i2p_consec_failures = 0
            self.last_probe = None
            self.last_i2p_probe = None
            return

        # Tor is always probed. I2P is probed only when the project has it on;
        # otherwise its state is reset so a later disable can't leave the switch
        # stuck engaged on a stale I2P failure.
        tor_result = await self.probe_fn(settings.proxy)
        self.last_probe = tor_result
        self._consec_failures = (
            0 if tor_result["ok"] else self._consec_failures + 1
        )

        if settings.i2p_enabled:
            i2p_result = await self.probe_fn(settings.i2p_proxy)
            self.last_i2p_probe = i2p_result
            self._i2p_consec_failures = (
                0 if i2p_result["ok"] else self._i2p_consec_failures + 1
            )
        else:
            self.last_i2p_probe = None
            self._i2p_consec_failures = 0

        tor_down = self._consec_failures >= self.fail_threshold
        i2p_down = self._i2p_consec_failures >= self.fail_threshold

        if tor_down or i2p_down:
            if not self.engaged.is_set():
                # Tor takes priority in the reason when both trip at once.
                if tor_down:
                    self._engage("tor_down", settings.kill_switch_active)
                else:
                    self._engage("i2p_down", settings.i2p_kill_switch_active)
        elif self.engaged.is_set():
            # Engaged only clears once every monitored network is healthy.
            self._clear()

    def _engage(self, reason: str, cancel: bool) -> None:
        self.engaged.set()
        if cancel:
            cancelled = self._cancel_registered()
            self.event_bus.publish(
                "kill_switch.engaged",
                {"cancelled_tasks": cancelled, "reason": reason},
            )
        else:
            self.event_bus.publish(
                "kill_switch.banner",
                {"reason": reason},
            )

    def _clear(self) -> None:
        self.engaged.clear()
        self.event_bus.publish("kill_switch.clear", {})

    async def _run(self) -> None:
        try:
            while not self._stopping:
                try:
                    await self._tick()
                except Exception:  # noqa: BLE001 — never let the loop die
                    log.exception("kill switch tick failed")
                await self.sleep_fn(self.probe_interval)
        except asyncio.CancelledError:
            return

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        if self._loop_task is not None:
            return
        self._stopping = False
        self._loop_task = asyncio.create_task(self._run(), name="kill_switch")

    async def stop(self) -> None:
        self._stopping = True
        if self._loop_task is None:
            return
        self._loop_task.cancel()
        try:
            await self._loop_task
        except asyncio.CancelledError:
            pass
        self._loop_task = None


__all__ = ["KillSwitch"]
