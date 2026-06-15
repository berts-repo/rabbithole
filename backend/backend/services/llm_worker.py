"""Background LLM analysis worker.

PLAN.md:336–342. Single asyncio task per process. Each tick:

  1. ``llm_db.claim_next_batch(model, limit=5)`` — atomically promotes the
     5 highest-priority pending jobs to ``running``.
  2. For each job, build prompts via ``prompts.PROMPTS[type]`` and POST to
     Ollama's ``/api/generate``.
  3. Run the response through the per-type ``output_validator``. Validation
     failure → ``mark_done(result="<dropped:invalid_output>")`` per spec
     ("dropped, not stored").
  4. ``_persist`` writes back per-type: ``Entities (LLM)`` → ``findings``
     with ``source='llm'``; ``Category`` → ``pages.set_category``;
     ``Domain Label`` → ``domains.alias`` (skipped when an analyst alias
     already exists); ``Summary`` → ``pages.set_summary``; everything else
     stays in ``analyses.result`` only.
  5. Each tick also walks one ``collection_analyses`` synthesis job, using
     ``prompts.render_multi`` with a fresh per-request UUID delimiter and
     a 64 KB total input cap.

Ollama unavailable → 30 s sleep + retry per spec line 336. The session is
built through ``security/net.py::make_ollama_session`` so the B0 grep
guard's allowlist for direct aiohttp session construction stays a single file.

Module-level helper ``auto_enqueue_for_node`` is the import target for
``crawler/runtime.py`` — lives here (not in routes) so the crawler can
call it without an import cycle.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, TYPE_CHECKING
from urllib.parse import urlparse

import aiohttp

from ..db import auto_rules as auto_rules_db
from ..db import collections as collections_db
from ..db import domains as domains_db
from ..db import findings as findings_db
from ..db import llm as llm_db
from ..db import page_versions as page_versions_db
from ..db import pages as pages_db
from ..db.settings import get_setting
from ..prompts import (
    OutputValidationError,
    PROMPTS,
    render,
    render_multi,
)
from ..security.net import make_ollama_session
from .event_bus import EventBus

if TYPE_CHECKING:
    from ..db.core import CrawlDB
    from .kill_switch import KillSwitch
    from .project_state import ProjectState


log = logging.getLogger(__name__)


_TICK_INTERVAL_SECONDS = 2.0
_BATCH_LIMIT = 5
_OLLAMA_RETRY_SECONDS = 30.0
_OLLAMA_REQUEST_TIMEOUT = 120.0  # cold-load headroom for ~3B models on 8GB VMs
_DEFAULT_MODEL = "qwen2.5:3b"
_DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
_DROPPED_RESULT = "<dropped:invalid_output>"
_OLLAMA_DOWN_RESULT = "<dropped:ollama_unreachable>"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SessionFactory = Callable[..., aiohttp.ClientSession]


def _default_session_factory(
    ollama_url: str, *, timeout: aiohttp.ClientTimeout
) -> aiohttp.ClientSession:
    return make_ollama_session(ollama_url, timeout=timeout)


# --- module-level auto-enqueue helper --------------------------------------


def auto_enqueue_for_node(db: "CrawlDB", node_id: int) -> list[int]:
    """Crawler hook: enqueue analyses for the enabled ``crawl`` auto-analysis rules.

    ``node_id`` is a ``resources.id`` (the crawler calls this right after the
    page is recorded, so the resource is ``crawled`` and has a page row).
    No-op when the page has ``analysis_excluded=true`` (the analyst's mute
    button still wins). Returns the new analysis ids — empty list when nothing
    fired. The signature/name are unchanged so ``crawler/runtime.py`` keeps
    calling it without an import cycle.

    (item 7, D4) The crawl trigger reads typed ``auto_analysis_rules`` rows
    (``trigger_kind='crawl'``) — the single home for auto-analysis — instead of
    the legacy ``llm.auto_enqueue.*`` settings. ``db.core`` seeds those rules
    from the settings on first open, so behavior is unchanged before/after. A
    rule's ``model`` falls back to the ``llm.model`` setting when unset.
    """
    if pages_db.get_analysis_excluded(db, node_id):
        return []
    rules = auto_rules_db.list_rules(db, trigger_kind="crawl", enabled_only=True)
    if not rules:
        return []
    default_model = get_setting(db, "llm.model") or _DEFAULT_MODEL
    new_ids: list[int] = []
    for rule in rules:
        model = rule.get("model") or default_model
        try:
            new_id = llm_db.enqueue(
                db,
                resource_id=node_id,
                analysis_type=str(rule["analysis_type"]),
                model=model,
                priority=0,
            )
        except ValueError:
            continue
        new_ids.append(new_id)
    return new_ids


def auto_enqueue_for_collection_add(
    db: "CrawlDB", collection_id: int, resource_ids: list[int]
) -> list[int]:
    """Collection hook: enqueue analyses for ``collection_add`` rules (item 7, D4).

    Called right after one or more resources are added to ``collection_id``. For
    each enabled rule targeting this collection, queues the rule's analyzer once
    per added crawled resource (the analyst's per-page exclude still wins). The
    rule's ``model`` falls back to the ``llm.model`` setting when unset. Returns
    the new analysis ids — empty list when no rule matches or nothing fires.
    """
    rules = auto_rules_db.rules_for_collection_add(db, collection_id)
    if not rules:
        return []
    default_model = get_setting(db, "llm.model") or _DEFAULT_MODEL
    new_ids: list[int] = []
    for rule in rules:
        model = rule.get("model") or default_model
        for resource_id in resource_ids:
            if pages_db.get_analysis_excluded(db, resource_id):
                continue
            try:
                new_id = llm_db.enqueue(
                    db,
                    resource_id=resource_id,
                    analysis_type=str(rule["analysis_type"]),
                    model=model,
                    priority=0,
                )
            except ValueError:
                continue
            new_ids.append(new_id)
    return new_ids


# --- LlmWorker -------------------------------------------------------------


@dataclass
class LlmWorker:
    project_state: "ProjectState"
    kill_switch: "KillSwitch"
    event_bus: EventBus
    session_factory: SessionFactory = field(default=_default_session_factory)
    sleep_fn: Callable[[float], Awaitable[None]] = field(default=asyncio.sleep)
    tick_interval: float = _TICK_INTERVAL_SECONDS
    batch_limit: int = _BATCH_LIMIT
    request_timeout: float = _OLLAMA_REQUEST_TIMEOUT

    _status: str = "stopped"
    _ollama_down_until: float = 0.0
    _processed: int = 0
    _failures: int = 0
    _paused: bool = False
    _loop_task: Optional[asyncio.Task] = None
    _stopping: bool = False

    # -- snapshot --------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        db = self.project_state.active_db
        counts = llm_db.queue_counts(db) if db is not None else {}
        return {
            "status": self._status,
            "paused": self._paused,
            "model": (get_setting(db, "llm.model") if db is not None else None) or _DEFAULT_MODEL,
            "ollama_url": (get_setting(db, "llm.ollama_url") if db is not None else None) or _DEFAULT_OLLAMA_URL,
            "processed": self._processed,
            "failures": self._failures,
            "queue": counts,
            # Worker load/capacity for the Intel worker controls (item 7).
            # capacity = jobs drained per tick (the single concurrency number);
            # in_flight / queue_depth are derived from the live job counts.
            "capacity": self._effective_batch_limit(db),
            "in_flight": int(counts.get("running", 0)),
            "queue_depth": int(counts.get("pending", 0)),
        }

    def _effective_batch_limit(self, db: "CrawlDB | None") -> int:
        """Per-tick claim size, from the ``llm.batch_size`` setting (item 7).

        Falls back to the dataclass default when unset or unparseable so a bad
        setting can never stall the worker.
        """
        if db is None:
            return self.batch_limit
        raw = get_setting(db, "llm.batch_size")
        if raw is None:
            return self.batch_limit
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            return self.batch_limit
        return value if value > 0 else self.batch_limit

    # -- single tick -----------------------------------------------------

    async def _tick(self) -> int:
        db = self.project_state.active_db
        if db is None:
            self._status = "idle"
            return 0
        if self._paused:
            self._status = "paused"
            return 0

        # Crash recovery is the single boot sweep in core.py (running → failed);
        # the worker no longer reconciles mid-flight rows itself.
        loop = asyncio.get_running_loop()
        if loop.time() < self._ollama_down_until:
            self._status = "ollama_down"
            return 0

        model = get_setting(db, "llm.model") or _DEFAULT_MODEL
        ollama_url = get_setting(db, "llm.ollama_url") or _DEFAULT_OLLAMA_URL

        # Per-node jobs first — keep the analyst's interactive queue moving.
        batch = llm_db.claim_next_batch(
            db, model=model, limit=self._effective_batch_limit(db)
        )
        if batch:
            self._status = "running"
            for row in batch:
                await self._process_node_job(db, row, model, ollama_url)
            return len(batch)

        # Idle on per-node jobs → pick up at most one synthesis job per tick.
        col_job = llm_db.claim_next_collection(db, model=model)
        if col_job is not None:
            self._status = "running"
            await self._process_collection_job(db, col_job, model, ollama_url)
            return 1

        # Cluster synthesis shares the once-per-tick synthesis budget, after
        # collections, so neither starves the other.
        cluster_job = llm_db.claim_next_cluster(db, model=model)
        if cluster_job is not None:
            self._status = "running"
            await self._process_cluster_job(db, cluster_job, model, ollama_url)
            return 1

        self._status = "idle"
        return 0

    # -- per-node job dispatch ------------------------------------------

    async def _process_node_job(
        self,
        db: "CrawlDB",
        row: dict[str, Any],
        model: str,
        ollama_url: str,
    ) -> None:
        job_id = int(row["job_id"])
        analysis_id = int(row["analysis_id"])
        analysis_type = str(row["analysis_type"])
        resource_id = int(row["resource_id"])

        spec = PROMPTS.get(analysis_type)
        if spec is None:
            log.warning(
                "llm worker: unknown analysis_type %r — dropping job %d",
                analysis_type,
                job_id,
            )
            llm_db.mark_done(
                db, job_id=job_id, analysis_id=analysis_id,
                result_text="<dropped:unknown_type>",
            )
            self._failures += 1
            return

        page = pages_db.get_page_detail(db, resource_id)
        if page is None or not page.get("body_text_clean"):
            llm_db.mark_done(
                db, job_id=job_id, analysis_id=analysis_id,
                result_text="<dropped:no_content>",
            )
            self._failures += 1
            return

        try:
            system_prompt, user_prompt = render(
                spec,
                str(page["body_text_clean"]),
                question=row.get("question"),
            )
        except Exception:  # noqa: BLE001
            log.exception("llm worker: render failed for job %d", job_id)
            llm_db.mark_done(
                db, job_id=job_id, analysis_id=analysis_id,
                result_text=_DROPPED_RESULT,
            )
            self._failures += 1
            return

        raw = await self._call_ollama(
            model=row.get("model") or model,
            ollama_url=ollama_url,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        if raw is None:
            # Transient — push back to pending, sleep until the down-window expires.
            llm_db.mark_failed_back_to_pending(db, job_id)
            return
        if raw == _OLLAMA_DOWN_RESULT:
            llm_db.mark_failed_back_to_pending(db, job_id)
            return

        try:
            validated = spec.output_validator(raw)
        except OutputValidationError as exc:
            log.info(
                "llm worker: validator dropped job %d (%s): %s",
                job_id,
                analysis_type,
                exc,
            )
            llm_db.mark_done(
                db, job_id=job_id, analysis_id=analysis_id,
                result_text=_DROPPED_RESULT,
            )
            self._failures += 1
            return

        try:
            self._persist(db, analysis_type, page, validated)
        except Exception:  # noqa: BLE001
            log.exception(
                "llm worker: persist failed for job %d (%s)",
                job_id,
                analysis_type,
            )

        llm_db.mark_done(
            db, job_id=job_id, analysis_id=analysis_id,
            result_text=_result_text_for(validated),
        )
        self._processed += 1
        self.event_bus.publish(
            "llm.job_done",
            {
                "analysis_id": analysis_id,
                "node_id": resource_id,
                "analysis_type": analysis_type,
            },
        )

    # -- collection synthesis dispatch ----------------------------------

    async def _process_collection_job(
        self,
        db: "CrawlDB",
        row: dict[str, Any],
        model: str,
        ollama_url: str,
    ) -> None:
        job_id = int(row["job_id"])
        analysis_id = int(row["analysis_id"])
        analysis_type = str(row["analysis_type"])
        collection_id = int(row["collection_id"])

        spec = PROMPTS.get(analysis_type)
        if spec is None or not spec.multi_page:
            llm_db.mark_collection_done(
                db, job_id=job_id, analysis_id=analysis_id,
                result_text="<dropped:unknown_type>",
            )
            self._failures += 1
            return

        items = collections_db.list_items(db, collection_id)
        crawled = [it for it in items if it.get("state") == "crawled"]
        if not crawled:
            llm_db.mark_collection_done(
                db, job_id=job_id, analysis_id=analysis_id,
                result_text="<dropped:no_pages>",
            )
            return
        bodies = self._collect_bodies(db, [int(it["id"]) for it in crawled])
        if not bodies:
            llm_db.mark_collection_done(
                db, job_id=job_id, analysis_id=analysis_id,
                result_text="<dropped:no_content>",
            )
            return

        try:
            system_prompt, user_prompt, _delim = render_multi(spec, bodies)
        except Exception:  # noqa: BLE001
            log.exception("collection synthesis render failed for job %d", job_id)
            llm_db.mark_collection_done(
                db, job_id=job_id, analysis_id=analysis_id,
                result_text=_DROPPED_RESULT,
            )
            return

        if len(bodies) > 0 and len(bodies) < len(crawled):
            self.event_bus.publish(
                "llm.synthesis.truncated",
                {
                    "analysis_id": analysis_id,
                    "kept": len(bodies),
                    "dropped": len(crawled) - len(bodies),
                },
            )

        raw = await self._call_ollama(
            model=row.get("model") or model,
            ollama_url=ollama_url,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        if raw is None or raw == _OLLAMA_DOWN_RESULT:
            llm_db.mark_collection_failed_back_to_pending(db, job_id)
            return

        try:
            validated = spec.output_validator(raw)
        except OutputValidationError:
            llm_db.mark_collection_done(
                db, job_id=job_id, analysis_id=analysis_id,
                result_text=_DROPPED_RESULT,
            )
            self._failures += 1
            return

        llm_db.mark_collection_done(
            db, job_id=job_id, analysis_id=analysis_id,
            result_text=_result_text_for(validated),
        )
        self._processed += 1
        self.event_bus.publish(
            "llm.collection_done",
            {
                "analysis_id": analysis_id,
                "collection_id": collection_id,
                "analysis_type": analysis_type,
            },
        )

    # -- cluster synthesis dispatch -------------------------------------

    async def _process_cluster_job(
        self,
        db: "CrawlDB",
        row: dict[str, Any],
        model: str,
        ollama_url: str,
    ) -> None:
        job_id = int(row["job_id"])
        analysis_id = int(row["analysis_id"])
        analysis_type = str(row["analysis_type"])
        resource_ids = [int(r) for r in row.get("resource_ids") or []]
        question = row.get("question")

        # Cluster analyses are synthesis over the membership snapshot, so the
        # type must be multi-page (Cluster Q&A, Cluster Summary, …).
        spec = PROMPTS.get(analysis_type)
        if spec is None or not spec.multi_page:
            llm_db.mark_cluster_done(
                db, job_id=job_id, analysis_id=analysis_id,
                result_text="<dropped:unknown_type>",
            )
            self._failures += 1
            return

        if not resource_ids:
            llm_db.mark_cluster_done(
                db, job_id=job_id, analysis_id=analysis_id,
                result_text="<dropped:no_pages>",
            )
            return
        bodies = self._collect_bodies(db, resource_ids)
        if not bodies:
            llm_db.mark_cluster_done(
                db, job_id=job_id, analysis_id=analysis_id,
                result_text="<dropped:no_content>",
            )
            return

        try:
            system_prompt, user_prompt, _delim = render_multi(
                spec, bodies, question=question
            )
        except Exception:  # noqa: BLE001
            log.exception("cluster synthesis render failed for job %d", job_id)
            llm_db.mark_cluster_done(
                db, job_id=job_id, analysis_id=analysis_id,
                result_text=_DROPPED_RESULT,
            )
            return

        raw = await self._call_ollama(
            model=row.get("model") or model,
            ollama_url=ollama_url,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        if raw is None or raw == _OLLAMA_DOWN_RESULT:
            llm_db.mark_cluster_failed_back_to_pending(db, job_id)
            return

        try:
            validated = spec.output_validator(raw)
        except OutputValidationError:
            llm_db.mark_cluster_done(
                db, job_id=job_id, analysis_id=analysis_id,
                result_text=_DROPPED_RESULT,
            )
            self._failures += 1
            return

        llm_db.mark_cluster_done(
            db, job_id=job_id, analysis_id=analysis_id,
            result_text=_result_text_for(validated),
        )
        self._processed += 1
        self.event_bus.publish(
            "llm.cluster_done",
            {
                "analysis_id": analysis_id,
                "fingerprint": row.get("fingerprint"),
                "analysis_type": analysis_type,
            },
        )

    def _collect_bodies(self, db: "CrawlDB", resource_ids: list[int]) -> list[str]:
        """Current-version clean text per resource — order matches the input list.

        The caller already filtered to ``state='crawled'`` members; this pulls
        each resource's current ``page_versions`` clean text and drops the ones
        with no current version / empty body.
        """
        bodies = page_versions_db.current_clean_text(db, resource_ids)
        return [bodies[i] for i in resource_ids if bodies.get(i)]

    # -- Ollama HTTP ----------------------------------------------------

    async def _call_ollama(
        self,
        *,
        model: str,
        ollama_url: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str | None:
        """POST to ``/api/generate`` with ``stream:false``. Returns the text response.

        Returns ``None`` on transient HTTP error (caller pushes the job back
        to pending). Returns ``_OLLAMA_DOWN_RESULT`` when the connection
        itself fails (caller also pushes back, then we sleep 30 s before
        the next tick).
        """
        timeout = aiohttp.ClientTimeout(total=self.request_timeout)
        try:
            session_ctx = self.session_factory(ollama_url, timeout=timeout)
        except Exception:  # noqa: BLE001
            log.exception("llm worker: bad ollama_url %s", ollama_url)
            self._enter_ollama_down()
            return _OLLAMA_DOWN_RESULT

        url = ollama_url.rstrip("/") + "/api/generate"
        payload = {
            "model": model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
        }
        try:
            async with session_ctx as session:
                task = asyncio.current_task()
                if task is not None:
                    self.kill_switch.register_task(task)
                async with session.post(url, json=payload) as resp:
                    if resp.status >= 500:
                        log.warning(
                            "ollama %s returned %d", url, resp.status
                        )
                        return None
                    if resp.status >= 400:
                        log.warning(
                            "ollama %s rejected request: %d", url, resp.status
                        )
                        return None
                    body_text = await resp.text()
        except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError):
            log.info("ollama unreachable at %s", ollama_url)
            self._enter_ollama_down()
            return _OLLAMA_DOWN_RESULT
        except asyncio.TimeoutError:
            log.warning("ollama timed out at %s", url)
            return None
        except Exception:  # noqa: BLE001
            log.exception("ollama call failed at %s", url)
            return None

        try:
            data = json.loads(body_text)
        except json.JSONDecodeError:
            log.warning("ollama returned non-JSON body (truncated): %.200s", body_text)
            return None
        response = data.get("response")
        if not isinstance(response, str):
            log.warning("ollama response missing 'response' field")
            return None
        return response

    def _enter_ollama_down(self) -> None:
        loop = asyncio.get_running_loop()
        self._ollama_down_until = loop.time() + _OLLAMA_RETRY_SECONDS
        self._status = "ollama_down"

    # -- write-back -----------------------------------------------------

    def _persist(
        self,
        db: "CrawlDB",
        analysis_type: str,
        node: dict[str, Any],
        validated: Any,
    ) -> None:
        """Per-type write-back per PLAN.md:337–342.

        ``node`` is the ``pages.get_page_detail`` dict for the analysed
        resource: ``id`` is the resource id, ``current_version_id`` the version
        whose text was analysed (so LLM entities link back to it).
        """
        resource_id = int(node["id"])
        if analysis_type == "Summary":
            pages_db.set_summary(db, resource_id, str(validated))
            return
        if analysis_type == "Category":
            pages_db.set_category(db, resource_id, str(validated))
            return
        if analysis_type == "Entities (LLM)":
            entries: list[tuple[str, str]] = [
                ("blob", value) for value in validated
            ]
            findings_db.insert_entities(
                db,
                resource_id,
                entries,
                source="llm",
                page_version_id=node.get("current_version_id"),
                now=_now_iso(),
            )
            return
        if analysis_type == "Domain Label":
            host = self._host_for_node(node)
            if not host:
                return
            existing = self._existing_alias(db, host)
            if existing:
                self.event_bus.publish(
                    "llm.domain_label.skipped",
                    {"node_id": resource_id, "host": host, "alias": existing},
                )
                return
            try:
                domains_db.rename_alias(db, host, str(validated))
            except ValueError:
                # Duplicate alias / too long — drop silently; the validator
                # already enforced max length but races are possible.
                pass
            return
        # Risk Score / Q&A / anything else: result-only.

    def _host_for_node(self, node: dict[str, Any]) -> str | None:
        host = node.get("domain")
        if isinstance(host, str) and host:
            return host
        url = node.get("url")
        if not isinstance(url, str):
            return None
        return urlparse(url).hostname

    def _existing_alias(self, db: "CrawlDB", host: str) -> str | None:
        with db.read() as c:
            row = c.execute(
                "SELECT alias FROM domains WHERE host = ?", (host,)
            ).fetchone()
        if row is None:
            return None
        alias = row["alias"]
        return alias if isinstance(alias, str) and alias else None

    # -- loop -----------------------------------------------------------

    async def _run(self) -> None:
        try:
            while not self._stopping:
                try:
                    await self._tick()
                except Exception:  # noqa: BLE001
                    log.exception("llm worker tick failed")
                # If Ollama is in the down window, sleep until it expires.
                loop = asyncio.get_running_loop()
                if loop.time() < self._ollama_down_until:
                    await self.sleep_fn(
                        max(0.0, self._ollama_down_until - loop.time())
                    )
                else:
                    await self.sleep_fn(self.tick_interval)
        except asyncio.CancelledError:
            return

    # -- lifecycle ------------------------------------------------------

    async def start(self) -> None:
        self._paused = False
        if self._loop_task is not None:
            return
        self._stopping = False
        self._status = "starting"
        self._loop_task = asyncio.create_task(self._run(), name="llm_worker")

    async def stop(self) -> None:
        self._stopping = True
        if self._loop_task is None:
            self._status = "stopped"
            return
        self._loop_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._loop_task
        self._loop_task = None
        self._status = "stopped"

    def pause(self) -> None:
        self._paused = True
        self._status = "paused"

    def resume(self) -> None:
        self._paused = False
        if self._loop_task is not None:
            self._status = "running"


def _result_text_for(validated: Any) -> str:
    """How the queue UI renders the output of each type."""
    if isinstance(validated, list):
        return "\n".join(str(v) for v in validated)
    return str(validated)


__all__ = [
    "LlmWorker",
    "auto_enqueue_for_collection_add",
    "auto_enqueue_for_node",
]
