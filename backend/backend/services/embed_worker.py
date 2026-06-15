"""Background embedding worker.

PLAN.md:344. Single asyncio task per process. Each tick:

  1. Read ``embedding.model`` from settings; if it changed since the last
     tick, ``delete_all_embeddings`` and reload the fastembed model in a
     thread (model load is heavy — onnxruntime spin-up).
  2. ``embed.pending(model, limit=50)`` — pages not yet embedded under the
     active model (returns ``page_id`` + ``resource_id`` pairs).
  3. Encode each current-version body in a thread, ``upsert_embedding`` per
     result (keyed by ``page_id``).
  4. Per-page failure increments a counter; at 3 the page is permanently
     excluded (``pages.embed_excluded=true``) and ``embed.poison_pill`` published.
  5. Loop-level circuit breaker: 5 consecutive whole-loop failures → idle
     until ``POST /api/embed/start`` clears the breaker.

Public surface mirrors ``MonitorDaemon``: ``start/stop/pause/resume`` plus
a ``snapshot()`` for the status route and an ``encode(text)`` helper used
by ``routes/search.py`` for semantic queries (returns serialized bytes,
raises ``EmbedNotReady`` when the model hasn't loaded yet).
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, TYPE_CHECKING

from ..db import embed as embed_db
from ..db import page_versions as page_versions_db
from ..db import pages as pages_db
from ..db.settings import get_setting
from .event_bus import EventBus

if TYPE_CHECKING:
    from .project_state import ProjectState
    from .kill_switch import KillSwitch


log = logging.getLogger(__name__)


_TICK_INTERVAL_SECONDS = 2.0
_BATCH_LIMIT = 50
_POISON_THRESHOLD = 3       # consecutive same-node failures → exclude
_LOOP_FAILURE_THRESHOLD = 5  # consecutive whole-loop failures → trip breaker
_BACKOFF_LADDER = (5, 10, 30, 60, 300)  # seconds, indexed by failure count
_DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"


class EmbedNotReady(RuntimeError):
    """Raised by ``EmbedWorker.encode`` before fastembed has loaded."""


# Default model loader: lazy-imports fastembed so tests using a stub never
# pay the onnxruntime startup cost. The first real call pulls the model
# weights from the fastembed cache (downloaded on first use).
def _default_model_loader(model_name: str) -> Any:
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=model_name)


@dataclass
class EmbedWorker:
    """Dataclass holds mutable state; lifecycle methods are async."""

    project_state: "ProjectState"
    kill_switch: "KillSwitch"
    event_bus: EventBus
    sleep_fn: Callable[[float], Awaitable[None]] = field(default=asyncio.sleep)
    model_loader: Callable[[str], Any] = field(default=_default_model_loader)
    tick_interval: float = _TICK_INTERVAL_SECONDS
    batch_limit: int = _BATCH_LIMIT

    _model: Any = None
    _loaded_model_name: str | None = None
    _status: str = "stopped"
    _processed: int = 0
    _failures: int = 0
    _consec_node_failures: dict[int, int] = field(default_factory=dict)
    _consec_loop_failures: int = 0
    _circuit_open: bool = False
    _paused: bool = False
    _loop_task: Optional[asyncio.Task] = None
    _stopping: bool = False

    # -- snapshot --------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        db = self.project_state.active_db
        eligible = embed_db.count_eligible_pages(db) if db is not None else 0
        embedded = embed_db.count_embeddings(db) if db is not None else 0
        return {
            "status": self._status,
            "paused": self._paused,
            "circuit_open": self._circuit_open,
            "model": self._loaded_model_name,
            "processed": self._processed,
            "failures": self._failures,
            "consec_loop_failures": self._consec_loop_failures,
            "embedded": embedded,
            "eligible": eligible,
            "queue_size": max(eligible - embedded, 0),
        }

    def encode(self, text: str) -> bytes:
        """Synchronous one-shot encode for the search route. Raises if not ready."""
        if self._model is None:
            raise EmbedNotReady("embed model not loaded")
        vectors = list(self._model.embed([text]))
        if not vectors:
            raise EmbedNotReady("embed model produced no output")
        first = vectors[0]
        return embed_db.serialize_vector([float(x) for x in first])

    # -- model handling --------------------------------------------------

    async def _ensure_model(self, name: str) -> bool:
        """Load (or reload) the fastembed model. Returns True on (re)load.

        On model swap, drops every existing embedding so the worker re-fills
        the table under the new model on subsequent ticks.
        """
        if self._loaded_model_name == name and self._model is not None:
            return False
        log.info("embed worker loading model: %s", name)
        try:
            model = await asyncio.to_thread(self.model_loader, name)
        except Exception:  # noqa: BLE001 — propagated as a tick-level failure
            log.exception("embed worker failed to load model %s", name)
            raise

        # Swap detected → wipe stale embeddings before installing the new model.
        db = self.project_state.active_db
        if (
            db is not None
            and self._loaded_model_name is not None
            and self._loaded_model_name != name
        ):
            wiped = embed_db.delete_all_embeddings(db)
            log.info(
                "embed model swap: %s → %s (deleted %d existing embeddings)",
                self._loaded_model_name,
                name,
                wiped,
            )
            self.event_bus.publish(
                "embed.model_swap",
                {
                    "from": self._loaded_model_name,
                    "to": name,
                    "deleted": wiped,
                },
            )

        self._model = model
        self._loaded_model_name = name
        return True

    # -- single tick -----------------------------------------------------

    async def _tick(self) -> int:
        """One pass. Returns the number of embeddings written."""
        db = self.project_state.active_db
        if db is None:
            self._status = "idle"
            return 0
        if self._paused:
            self._status = "paused"
            return 0
        if self._circuit_open:
            self._status = "circuit_open"
            return 0

        model_name = (
            get_setting(db, "embedding.model") or _DEFAULT_EMBED_MODEL
        )
        await self._ensure_model(model_name)
        self._status = "running"

        batch = embed_db.pending(
            db, model=model_name, limit=self.batch_limit
        )
        if not batch:
            return 0

        # Embedded text is the current page version's clean body — fetch by
        # resource id (the content reader the synthesis path shares), then map
        # back to the page id that keys the vec0 row.
        texts = page_versions_db.current_clean_text(
            db, [p["resource_id"] for p in batch]
        )
        written = 0
        for entry in batch:
            page_id = entry["page_id"]
            resource_id = entry["resource_id"]
            text = texts.get(resource_id, "")
            if not text:
                continue
            try:
                vec_bytes = await asyncio.to_thread(self._encode_one, text)
            except Exception as exc:  # noqa: BLE001
                self._failures += 1
                count = self._consec_node_failures.get(page_id, 0) + 1
                self._consec_node_failures[page_id] = count
                log.warning(
                    "embed encode failed for page %d (attempt %d): %s",
                    page_id,
                    count,
                    exc,
                )
                if count >= _POISON_THRESHOLD:
                    # The poison-pill flag lives on the page; key it by resource.
                    pages_db.set_embed_excluded(db, resource_id, True)
                    self._consec_node_failures.pop(page_id, None)
                    self.event_bus.publish(
                        "embed.poison_pill",
                        {"node_id": resource_id, "failures": count},
                    )
                continue
            embed_db.upsert_embedding(
                db, page_id=page_id, vector=vec_bytes, model=model_name
            )
            self._processed += 1
            written += 1
            self._consec_node_failures.pop(page_id, None)

        if written > 0:
            self.event_bus.publish(
                "embed.progress",
                {
                    "processed": self._processed,
                    "embedded": embed_db.count_embeddings(db),
                    "eligible": embed_db.count_eligible_pages(db),
                },
            )
        return written

    def _encode_one(self, text: str) -> bytes:
        """Sync helper invoked via to_thread — keeps the main loop responsive."""
        if self._model is None:
            raise EmbedNotReady("model not loaded")
        vectors = list(self._model.embed([text]))
        if not vectors:
            raise RuntimeError("fastembed produced no output")
        return embed_db.serialize_vector([float(x) for x in vectors[0]])

    # -- loop ------------------------------------------------------------

    async def _run(self) -> None:
        try:
            while not self._stopping:
                try:
                    await self._tick()
                    if self._consec_loop_failures > 0:
                        self._consec_loop_failures = 0
                except Exception:  # noqa: BLE001 — tick-level failure
                    log.exception("embed worker tick failed")
                    self._consec_loop_failures += 1
                    if self._consec_loop_failures >= _LOOP_FAILURE_THRESHOLD:
                        self._circuit_open = True
                        self._status = "circuit_open"
                        self.event_bus.publish(
                            "embed.circuit_open",
                            {"failures": self._consec_loop_failures},
                        )
                        # Idle in place — only `start` (which clears the
                        # breaker) gets us moving again.
                        while not self._stopping and self._circuit_open:
                            await self.sleep_fn(self.tick_interval)
                        continue
                # Backoff scales with the loop-failure count when transient.
                idx = min(self._consec_loop_failures, len(_BACKOFF_LADDER) - 1)
                delay = _BACKOFF_LADDER[idx] if self._consec_loop_failures else self.tick_interval
                await self.sleep_fn(delay)
        except asyncio.CancelledError:
            return

    # -- lifecycle -------------------------------------------------------

    async def start(self) -> None:
        # Clear the circuit breaker on explicit start, per spec.
        self._circuit_open = False
        self._consec_loop_failures = 0
        self._paused = False
        if self._loop_task is not None:
            return
        self._stopping = False
        self._status = "starting"
        self._loop_task = asyncio.create_task(self._run(), name="embed_worker")

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


__all__ = ["EmbedNotReady", "EmbedWorker"]
