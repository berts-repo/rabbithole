"""Per-crawl link frontier + watchlist matcher.

Pure data structures — no I/O, no DB access at runtime. ``Frontier.enqueue``
takes pre-validated URLs (the runtime calls ``validate_network_url`` before
handing anything to the frontier) and the frontier does its own host
extraction + dedup.

"Frontier" is the standard crawler-literature term for the in-memory set of
unvisited URLs a single crawl is ordering. The durable, project-wide crawl
queue is a separate concern — crawl jobs on the unified ``jobs`` table
(``kind='crawl'``); see ``db/jobs.py``.

The five modes (PLAN.md:285):

* **BFS** — depth-major FIFO. Sibling links are visited before grandchildren.
* **DFS** — LIFO. Each newly-discovered link is consumed before older
  frontier entries.
* **Cross-site** — FIFO that prefers cross-host edges. Same-host links get
  parked; once the cross-host fringe is empty we drain the same-host bucket
  so we don't deadlock on a seed with no outbound links.
* **Diverse** — round-robin across hosts. One URL per host per rotation
  keeps the crawl from camping inside a single site.
* **Focused** — FIFO, but a child is only enqueued if its parent fetch
  matched the watchlist (the runtime computes the bool and hands it in).

``WatchlistMatcher`` wraps ``pyahocorasick`` for O(n) multi-term matching
against ``body_text_clean``. Both terms and corpus are lower-cased before
matching — PLAN.md:38 mandates case-insensitive comparison.
"""
from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import ahocorasick

if TYPE_CHECKING:
    from ..db.core import CrawlDB


# --- watchlist matcher ------------------------------------------------------


class WatchlistMatcher:
    """Aho-Corasick automaton over a list of literal terms.

    Built once per crawl (and rebuilt on ``watchlist.changed`` events).
    Empty term sets are valid — ``match`` always returns ``[]``.
    """

    def __init__(self, terms: list[str]) -> None:
        # Preserve the original casing of each term in the returned matches
        # so the auto-flag note (PLAN.md:286) is readable for the analyst.
        self._terms: list[str] = []
        self._automaton: ahocorasick.Automaton | None = None
        cleaned: list[str] = []
        seen_lower: set[str] = set()
        for term in terms:
            if not isinstance(term, str):
                continue
            stripped = term.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if lowered in seen_lower:
                continue
            seen_lower.add(lowered)
            cleaned.append(stripped)
        if not cleaned:
            return
        self._terms = cleaned
        auto = ahocorasick.Automaton()
        for original in cleaned:
            auto.add_word(original.lower(), original)
        auto.make_automaton()
        self._automaton = auto

    @classmethod
    def from_db(cls, db: "CrawlDB") -> "WatchlistMatcher":
        from ..db.watchlist import list_terms

        terms = [row["term"] for row in list_terms(db)]
        return cls(terms)

    @property
    def empty(self) -> bool:
        return self._automaton is None

    def match(self, body_text_clean: str | None) -> list[str]:
        """Return the *distinct* matched terms, in first-occurrence order."""
        if not body_text_clean or self._automaton is None:
            return []
        haystack = body_text_clean.lower()
        seen: set[str] = set()
        out: list[str] = []
        for _end_index, original in self._automaton.iter(haystack):
            if original in seen:
                continue
            seen.add(original)
            out.append(original)
        return out


# --- frontier ---------------------------------------------------------------


def _host_of(url: str) -> str:
    """Return the host (without port) for grouping. Lowercased."""
    return urlsplit(url).hostname or ""


@dataclass
class _Entry:
    url: str
    depth: int
    parent_id: int | None
    anchor_text: str | None
    host: str
    focused_eligible: bool


@dataclass
class Frontier:
    """Per-mode link frontier. Not thread-safe — the runtime is single-threaded."""

    mode: str
    seed_host: str
    max_depth: int | None = None

    _seen: set[str] = field(default_factory=set)

    # BFS / Cross-site cross-host: FIFO.
    _fifo: deque[_Entry] = field(default_factory=deque)
    # Cross-site same-host parking lot — drained only when ``_fifo`` is empty.
    _cross_parked: deque[_Entry] = field(default_factory=deque)
    # DFS: LIFO.
    _stack: list[_Entry] = field(default_factory=list)
    # Diverse: ordered per-host buckets, popped round-robin.
    _diverse: "OrderedDict[str, deque[_Entry]]" = field(default_factory=OrderedDict)

    # --- public surface ----------------------------------------------------

    def enqueue(
        self,
        url: str,
        *,
        depth: int,
        parent_id: int | None = None,
        anchor_text: str | None = None,
        focused_eligible: bool = True,
    ) -> bool:
        """Add ``url`` to the frontier. Returns ``False`` if filtered out.

        Reasons a URL gets dropped:

        * already seen (cross-crawl dedup happens at the DB level via the
          ``resources.url`` UNIQUE constraint; this set is the per-frontier copy);
        * over ``max_depth``;
        * mode is Focused and the parent didn't match the watchlist.
        """
        if url in self._seen:
            return False
        if self.max_depth is not None and depth > self.max_depth:
            return False
        if self.mode == "Focused" and not focused_eligible:
            return False
        self._seen.add(url)

        entry = _Entry(
            url=url,
            depth=depth,
            parent_id=parent_id,
            anchor_text=anchor_text,
            host=_host_of(url),
            focused_eligible=focused_eligible,
        )

        if self.mode == "DFS":
            self._stack.append(entry)
            return True
        if self.mode == "Diverse":
            self._diverse.setdefault(entry.host, deque()).append(entry)
            return True
        if self.mode == "Cross-site":
            if entry.host == self.seed_host or not self.seed_host:
                self._cross_parked.append(entry)
            else:
                self._fifo.append(entry)
            return True
        # BFS / Focused both use FIFO insertion.
        self._fifo.append(entry)
        return True

    def pop(self) -> _Entry | None:
        """Return the next entry per the active mode, or ``None`` if drained."""
        if self.mode == "DFS":
            return self._stack.pop() if self._stack else None
        if self.mode == "Diverse":
            return self._pop_diverse()
        if self.mode == "Cross-site":
            if self._fifo:
                return self._fifo.popleft()
            if self._cross_parked:
                return self._cross_parked.popleft()
            return None
        if self._fifo:
            return self._fifo.popleft()
        return None

    def _pop_diverse(self) -> _Entry | None:
        while self._diverse:
            host, bucket = next(iter(self._diverse.items()))
            entry = bucket.popleft()
            # Rotate: pop the bucket and re-insert at the tail (if non-empty)
            # so the next pop comes from a different host.
            del self._diverse[host]
            if bucket:
                self._diverse[host] = bucket
            return entry
        return None

    def __len__(self) -> int:
        return (
            len(self._fifo)
            + len(self._cross_parked)
            + len(self._stack)
            + sum(len(b) for b in self._diverse.values())
        )

    def seen(self, url: str) -> bool:
        return url in self._seen


__all__ = ["Frontier", "WatchlistMatcher"]
