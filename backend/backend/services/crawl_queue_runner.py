"""Crawl-job runner — schedule producer + dispatcher over the unified jobs table.

Owns two cooperating steps on one safety tick:

1. **Producer** — ``produce_scheduled_rows`` polls ``crawl_schedules`` and
   creates a ``jobs`` row (``kind='crawl'``, ``status='pending'``,
   ``payload.source='schedule'``) for any schedule whose ``interval_hours``
   has elapsed since its last fire. Always runs; never gated by the kill
   switch or pause flag (those are *dispatch* gates, not intake gates).
2. **Dispatcher** — ``try_advance`` claims the next pending crawl job under
   the one-active-crawl rule, creates the per-run ``crawls`` detail row, links
   it into the job payload, builds a :class:`CrawlRunner` (which owns the
   job's status transitions), and hands it to the registry.

The schema reset folded the old ``crawl_queue`` table into ``jobs``: a pending
crawl job *is* the queue entry, and its terminal status is written by the
runner itself — this dispatcher no longer writes terminal status, it just
advances to the next job when one finishes.

Sibling to ``MonitorDaemon`` / ``EmbedWorker`` / ``LlmWorker``; wired into
``main.py``'s lifespan and stopped before ``crawl_runners.stop()`` so any
in-flight runner gets stopped cleanly.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional, TYPE_CHECKING

from ..crawler.runtime import CrawlRunner, CrawlRunnerRegistry
from ..db import crawl as crawl_db
from ..db import jobs as jobs_db
from ..db.settings import get_setting
from .event_bus import EventBus

if TYPE_CHECKING:
    from .kill_switch import KillSwitch
    from .project_state import ProjectState


log = logging.getLogger(__name__)


_SAFETY_TICK_SECONDS = 10.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@dataclass
class CrawlQueueRunner:
    """Single-instance crawl-job dispatcher.

    Test-friendly: drive ``try_advance`` directly; the safety-tick loop is
    only spun up by ``start()`` / stopped by ``stop()`` for the production
    lifespan path.
    """

    project_state: "ProjectState"
    kill_switch: "KillSwitch"
    event_bus: EventBus
    registry: CrawlRunnerRegistry
    safety_tick: float = _SAFETY_TICK_SECONDS
    sleep_fn: Callable[[float], Awaitable[None]] = field(default=asyncio.sleep)
    clock: Callable[[], datetime] = field(default=_now)

    _loop_task: Optional[asyncio.Task] = None
    _stopping: bool = False
    # The crawl job currently dispatched (the registry holds at most one
    # runner). Used by request_cancel to target the right job.
    _active_job_id: Optional[int] = None

    # -- schedule producer -------------------------------------------------

    def _last_schedule_fire(self, db, url: str) -> str | None:
        """``created_at`` of the most recent schedule-sourced crawl job for ``url``."""
        with db.read() as c:
            row = c.execute(
                "SELECT MAX(created_at) AS last FROM jobs "
                "WHERE kind='crawl' "
                "  AND json_extract(payload, '$.source') = 'schedule' "
                "  AND json_extract(payload, '$.url') = ?",
                (url,),
            ).fetchone()
        return row["last"] if row is not None else None

    def _active_schedule_job_exists(self, db, url: str) -> bool:
        """True if a non-terminal schedule crawl job for ``url`` is outstanding."""
        placeholders = ",".join("?" * len(jobs_db.ACTIVE_STATUSES))
        with db.read() as c:
            row = c.execute(
                f"SELECT 1 FROM jobs WHERE kind='crawl' "
                f"  AND status IN ({placeholders}) "
                f"  AND json_extract(payload, '$.source') = 'schedule' "
                f"  AND json_extract(payload, '$.url') = ? LIMIT 1",
                (*jobs_db.ACTIVE_STATUSES, url),
            ).fetchone()
        return row is not None

    def produce_scheduled_rows(self) -> int:
        """Create a pending crawl job for any schedule whose interval elapsed.

        Returns the number created (0 or 1 per call). Not gated by the kill
        switch or pause flag — schedules keep producing during a Tor outage
        and the queue drains FIFO when dispatch resumes. "Last fire" reads the
        most recent schedule-sourced crawl job's ``created_at`` so a paused or
        kill-switched queue never double-fires.
        """
        db = self.project_state.active_db
        if db is None:
            return 0

        now = self.clock()
        fired = 0
        for schedule in crawl_db.list_active_schedules(db):
            last = _parse_iso(self._last_schedule_fire(db, schedule["url"]))
            if last is not None:
                elapsed_hours = (now - last).total_seconds() / 3600.0
                if elapsed_hours < float(schedule["interval_hours"]):
                    continue
            if self._active_schedule_job_exists(db, schedule["url"]):
                # Previous fire hasn't run yet — don't double-enqueue.
                continue

            job_id = jobs_db.create_job(
                db,
                kind="crawl",
                target_type="url",
                target_id=0,
                status="pending",
                payload={
                    "url": schedule["url"],
                    "mode": schedule["mode"],
                    "source": "schedule",
                    "collection_id": schedule["collection_id"],
                    "crawl_schedule_id": schedule["url"],
                    # Schedules pre-date the depth-cap feature; unlimited until
                    # the analyst attaches a cap on the schedule itself.
                    "max_depth": None,
                },
            )
            self.event_bus.publish(
                "jobs.changed",
                {"job_id": job_id, "kind": "crawl", "status": "pending",
                 "source": "schedule", "url": schedule["url"]},
            )
            fired += 1
            # One fire per tick keeps cadence predictable; dispatch drains FIFO.
            break

        return fired

    # -- dispatch ----------------------------------------------------------

    def try_advance(self) -> Optional[int]:
        """Claim and dispatch the next pending crawl job.

        Returns the dispatched ``jobs.id`` or ``None``. Gates, in order:
        no active project → paused setting → kill switch → registry already
        running → no pending crawl job.
        """
        db = self.project_state.active_db
        if db is None:
            return None
        if (get_setting(db, "crawl.queue_paused") or "false").lower() == "true":
            return None
        if self.kill_switch.engaged.is_set():
            return None
        if self.registry.is_running():
            return None

        claimed = jobs_db.claim_next_crawl(db)  # flips the job to 'running'
        if claimed is None:
            return None
        job_id = int(claimed["id"])
        payload = claimed.get("payload") or {}
        url = str(payload.get("url"))
        mode = str(payload.get("mode"))
        collection_id = payload.get("collection_id")
        max_depth = payload.get("max_depth")

        try:
            crawl_id = crawl_db.create_crawl(
                db,
                seed_url=url,
                mode=mode,
                collection_id=collection_id,
                max_depth=max_depth,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("create_crawl failed for job %s", job_id)
            jobs_db.set_status(db, job_id, "failed", error=f"create_crawl: {exc}")
            self._publish_change(job_id, "failed")
            return None

        # Link the per-run detail row into the job payload so crawls ↔ jobs
        # stay joined (find_active / list_crawls read status through this).
        payload["crawl_id"] = crawl_id
        jobs_db.update_payload(db, job_id, payload)

        runner = CrawlRunner(
            crawl_id=crawl_id,
            job_id=job_id,
            db=db,
            event_bus=self.event_bus,
            kill_switch=self.kill_switch,
            seed_url=url,
            mode=mode,
            max_depth=max_depth,
            collection_id=collection_id,
            graph_cache=self.project_state.graph_cache,
        )

        self._active_job_id = job_id
        try:
            self.registry.start(runner, on_finish=self._on_runner_finish)
        except RuntimeError:
            # Lost the race against another start path. Fail the claim so the
            # next pass can re-attempt without a phantom 'running' job.
            log.warning("registry.start lost race for job %s; rolling back", job_id)
            self._active_job_id = None
            jobs_db.set_status(db, job_id, "failed", error="dispatch_race")
            self._publish_change(job_id, "failed")
            return None

        self._publish_change(job_id, "running")
        return job_id

    # -- cancellation ------------------------------------------------------

    def request_cancel(self, job_id: int) -> bool:
        """Stop the active runner; the runner writes the ``cancelled`` status.

        Returns ``True`` if a stop was issued, ``False`` if the job isn't the
        one currently running. Idempotent.
        """
        if self._active_job_id != job_id:
            return False
        # Request the cooperative stop synchronously so the sync test path
        # observes it; the runner maps its 'stopped' exit to a 'cancelled'
        # job status on its own.
        runner = self.registry.current
        if runner is not None:
            runner.request_stop()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Synchronous test path — caller awaits registry.stop() itself.
            return True
        loop.create_task(self.registry.stop(), name=f"crawl_cancel_{job_id}")
        return True

    # -- runner completion hook -------------------------------------------

    def _on_runner_finish(
        self,
        runner: CrawlRunner,
        result: str | None,
        exc: BaseException | None,
    ) -> None:
        """Advance to the next job. The runner already wrote its terminal
        ``jobs`` status (done / cancelled / failed) on exit, so this hook only
        clears the active slot, emits a change event, and kicks dispatch.
        """
        job_id = self._active_job_id
        self._active_job_id = None
        db = self.project_state.active_db
        if db is None or job_id is None:
            log.warning(
                "crawl runner completion fired with no job context "
                "(crawl_id=%s, result=%s, exc=%s)",
                runner.crawl_id, result, type(exc).__name__ if exc else None,
            )
            self._schedule_advance()
            return
        job = jobs_db.get_job(db, job_id)
        status = job["status"] if job else "done"
        self._publish_change(job_id, status)
        self._schedule_advance()

    def _schedule_advance(self) -> None:
        """Fire ``try_advance`` from a fresh event-loop slot so the registry
        can finish self-eviction before we ask it for another dispatch."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.call_soon(self.try_advance)

    # -- SSE ---------------------------------------------------------------

    def _publish_change(self, job_id: int, status: str) -> None:
        self.event_bus.publish(
            "jobs.changed", {"job_id": job_id, "kind": "crawl", "status": status}
        )

    # -- lifecycle ---------------------------------------------------------

    async def _run(self) -> None:
        try:
            while not self._stopping:
                try:
                    self.produce_scheduled_rows()
                except Exception:  # noqa: BLE001 — never let the loop die
                    log.exception("crawl runner schedule-producer tick failed")
                try:
                    self.try_advance()
                except Exception:  # noqa: BLE001
                    log.exception("crawl runner dispatch tick failed")
                await self.sleep_fn(self.safety_tick)
        except asyncio.CancelledError:
            return

    async def start(self) -> None:
        if self._loop_task is not None:
            return
        self._stopping = False
        try:
            self.produce_scheduled_rows()
        except Exception:  # noqa: BLE001
            log.exception("crawl runner startup schedule-producer failed")
        try:
            self.try_advance()
        except Exception:  # noqa: BLE001
            log.exception("crawl runner startup advance failed")
        self._loop_task = asyncio.create_task(self._run(), name="crawl_queue_runner")

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


__all__ = ["CrawlQueueRunner"]
