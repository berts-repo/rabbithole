"""Settings read/write + ``SETTING_VALIDATORS`` dispatch table.

The static ``SETTING_VALIDATORS`` covers every key whose validation is purely
local. Templated keys whose validation needs a DB lookup (today only
``search.engine.{id}.enabled``) are resolved through ``validators_for_key``;
``put_setting`` always goes through that resolver so the route handler never
has to special-case which kind of key it's writing.

Validators normalize on the way in: e.g. ``"True"`` → ``"true"``,
``1`` → ``"true"``. Anything stored in the DB is the canonical string form.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, TYPE_CHECKING

from ..security.net import (
    EgressError,
    validate_i2p_proxy,
    validate_network_url,
    validate_ollama_url,
    validate_tor_proxy,
)
from ..security.paths import validate_browser_path

if TYPE_CHECKING:
    from .core import CrawlDB


# --- Generic validators -----------------------------------------------------


def _bool_validator(value: Any) -> str:
    """Accept native ``bool``, ints ``0/1``, or string ``"true"/"false"``
    (case-insensitive). Return the canonical ``"true"``/``"false"`` string.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        if value == 1:
            return "true"
        if value == 0:
            return "false"
        raise ValueError(f"expected bool-coercible int (0/1), got {value!r}")
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes"):
            return "true"
        if lowered in ("false", "0", "no"):
            return "false"
    raise ValueError(f"expected bool-coercible value, got {value!r}")


def _enum_validator(*allowed: str) -> Callable[[Any], str]:
    """Build a validator that accepts only the given string values."""
    allowed_set = frozenset(allowed)

    def _validate(value: Any) -> str:
        if isinstance(value, str) and value.strip() in allowed_set:
            return value.strip()
        raise ValueError(
            f"value must be one of {sorted(allowed_set)}, got {value!r}"
        )

    return _validate


def _int_range_validator(lo: int, hi: int) -> Callable[[Any], str]:
    """Build a validator that accepts an int in ``[lo, hi]`` (inclusive)."""

    def _validate(value: Any) -> str:
        if isinstance(value, bool):
            raise ValueError(f"expected int in [{lo},{hi}], got bool {value!r}")
        if isinstance(value, int):
            n = value
        elif isinstance(value, str):
            try:
                n = int(value.strip())
            except ValueError as e:
                raise ValueError(
                    f"expected int in [{lo},{hi}], got {value!r}"
                ) from e
        else:
            raise ValueError(f"expected int in [{lo},{hi}], got {value!r}")
        if n < lo or n > hi:
            raise ValueError(f"value {n} out of range [{lo},{hi}]")
        return str(n)

    return _validate


def _float_range_validator(lo: float, hi: float) -> Callable[[Any], str]:
    """Build a validator that accepts a float in ``[lo, hi]`` (inclusive).

    Stored as a plain string so the canonical representation matches the
    rest of the settings table; callers parse with ``float()`` on read.
    """

    def _validate(value: Any) -> str:
        if isinstance(value, bool):
            raise ValueError(f"expected float in [{lo},{hi}], got bool {value!r}")
        if isinstance(value, (int, float)):
            x = float(value)
        elif isinstance(value, str):
            try:
                x = float(value.strip())
            except ValueError as e:
                raise ValueError(
                    f"expected float in [{lo},{hi}], got {value!r}"
                ) from e
        else:
            raise ValueError(f"expected float in [{lo},{hi}], got {value!r}")
        if x < lo or x > hi:
            raise ValueError(f"value {x} out of range [{lo},{hi}]")
        return repr(x)

    return _validate


def _browser_path_validator(value: Any) -> str:
    return str(validate_browser_path(value))


# --- Embedding model registry (lazy fastembed import) ----------------------


_fastembed_models: frozenset[str] | None = None


def _fastembed_supported_models() -> frozenset[str]:
    """Memoize fastembed's supported-model list.

    fastembed is heavy — importing it pulls onnxruntime, which costs ~hundreds
    of ms even with no work. We defer the import to the first validator call
    and then cache the result for the lifetime of the process. Tests can
    monkeypatch ``_fastembed_models`` to a deterministic fixture.
    """
    global _fastembed_models
    if _fastembed_models is None:
        from fastembed import TextEmbedding

        models = TextEmbedding.list_supported_models()
        # fastembed returns a list of dicts shaped like {"model": "name", ...}.
        _fastembed_models = frozenset(m["model"] for m in models if "model" in m)
    return _fastembed_models


def _embedding_model_validator(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"embedding.model must be a string, got {value!r}")
    name = value.strip()
    if name not in _fastembed_supported_models():
        raise ValueError(f"embedding.model not in fastembed registry: {name!r}")
    return name


def _llm_model_validator(value: Any) -> str:
    """Plain string check — Ollama tag names vary widely (``qwen2.5:3b``,
    ``llama3.2:3b-instruct-q4_K_M``, etc.). We can't validate against the
    Ollama registry here without an HTTP call, so trust the analyst and
    enforce only length + non-empty + no control chars.
    """
    if not isinstance(value, str):
        raise ValueError(f"llm.model must be a string, got {value!r}")
    name = value.strip()
    if not name:
        raise ValueError("llm.model must be non-empty")
    if len(name) > 128:
        raise ValueError(f"llm.model too long: {len(name)} chars (max 128)")
    if any(c == "\x00" or (c < " " and c not in "\t") for c in name):
        raise ValueError("llm.model contains control characters")
    return name


def _workspace_tabs_validator(value: Any) -> list:
    """Array of collection tab records — each item has kind='collection' and
    a positive integer collection_id. Global tab is implicit and not stored."""
    if not isinstance(value, list):
        raise ValueError("workspace.tabs must be an array")
    if len(value) > 50:
        raise ValueError("workspace.tabs: too many tabs (max 50)")
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("workspace.tabs: each item must be an object")
        if item.get("kind") != "collection":
            raise ValueError("workspace.tabs: kind must be 'collection'")
        cid = item.get("collection_id")
        if not isinstance(cid, int) or cid < 1:
            raise ValueError(
                "workspace.tabs: collection_id must be a positive integer"
            )
    return value


# The bottom-pane tab ids. Must stay in sync with the frontend `BottomTab`
# union in frontend/src/lib/stores/bottomTabs.ts — the two are separate
# languages and can't share a literal, so keep them aligned by hand.
_BOTTOM_TAB_VALUES = (
    "live_crawl",
    "activity",
    "scheduled_crawls",
    "monitors",
    "inventory",
    "domains",
    "flags",
    "fingerprints",
    "labels",
    "collection",
    "bookmarks",
    "find",
)


def _bottom_tabs_validator(value: Any) -> str:
    """The analyst's customised bottom-pane strip — an ordered set of
    BottomTab ids. Accepts a list or a comma-separated string; normalizes to a
    canonical CSV scalar (de-duped, known ids only, order preserved). Stored as
    a string because the settings store persists values via ``str()``, so a
    JSON array would not round-trip. Must be non-empty.
    """
    if isinstance(value, str):
        items = [s.strip() for s in value.split(",")]
    elif isinstance(value, list):
        items = value
    else:
        raise ValueError("workspace.bottomTabs must be a list or CSV string")
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            raise ValueError(f"workspace.bottomTabs: tab must be a string, got {item!r}")
        tab = item.strip()
        if not tab:
            continue
        if tab not in _BOTTOM_TAB_VALUES:
            raise ValueError(f"workspace.bottomTabs: unknown tab {tab!r}")
        seen.add(tab)
    if not seen:
        raise ValueError("workspace.bottomTabs must contain at least one tab")
    # Emit in canonical order (_BOTTOM_TAB_VALUES order), matching the
    # frontend's strip ordering regardless of the input order.
    return ",".join(t for t in _BOTTOM_TAB_VALUES if t in seen)


def _workspace_active_validator(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("workspace.active must be a string")
    s = value.strip()
    if not s or len(s) > 64:
        raise ValueError("workspace.active must be 1–64 chars")
    return s


# Cap mirrors a generous "Add all to Graph" of a full search-result page; well
# below the link-directory uncrawled counts the canvas already handles.
_PINNED_IDS_MAX = 5_000


def _pinned_ids_validator(value: Any) -> str:
    """Analyst-pinned graph node ids — resources kept visible regardless of the
    ``graph.show_uncrawled`` toggle. Accepts a list of ints or a CSV string;
    normalizes to a de-duped, ascending CSV scalar (settings persist via
    ``str()``, so a JSON array would not round-trip — same reasoning as
    ``workspace.bottomTabs``). Empty is allowed (no pins).
    """
    if isinstance(value, str):
        items: list[Any] = [s.strip() for s in value.split(",") if s.strip()]
    elif isinstance(value, list):
        items = value
    else:
        raise ValueError("graph.pinned_ids must be a list or CSV string")
    if len(items) > _PINNED_IDS_MAX:
        raise ValueError(f"graph.pinned_ids: too many pins (max {_PINNED_IDS_MAX})")
    ids: set[int] = set()
    for item in items:
        if isinstance(item, bool):
            raise ValueError(f"graph.pinned_ids: id must be an int, got {item!r}")
        if isinstance(item, int):
            n = item
        elif isinstance(item, str):
            try:
                n = int(item)
            except ValueError as e:
                raise ValueError(f"graph.pinned_ids: bad id {item!r}") from e
        else:
            raise ValueError(f"graph.pinned_ids: id must be an int, got {item!r}")
        if n < 1:
            raise ValueError(f"graph.pinned_ids: id must be positive, got {n}")
        ids.add(n)
    return ",".join(str(n) for n in sorted(ids))


def _id_csv_validator(key: str) -> "Callable[[Any], str]":
    """Validator factory for a de-duped, ascending CSV of positive int ids —
    the label include/exclude graph filters (item 11). Accepts a list of ints
    or a CSV string; empty allowed (filter off). Same round-trip reasoning as
    ``_pinned_ids_validator``: settings persist via ``str()``.
    """

    def _validate(value: Any) -> str:
        if isinstance(value, str):
            items: list[Any] = [s.strip() for s in value.split(",") if s.strip()]
        elif isinstance(value, list):
            items = value
        else:
            raise ValueError(f"{key} must be a list or CSV string")
        ids: set[int] = set()
        for item in items:
            if isinstance(item, bool):
                raise ValueError(f"{key}: id must be an int, got {item!r}")
            if isinstance(item, int):
                n = item
            elif isinstance(item, str):
                try:
                    n = int(item)
                except ValueError as e:
                    raise ValueError(f"{key}: bad id {item!r}") from e
            else:
                raise ValueError(f"{key}: id must be an int, got {item!r}")
            if n < 1:
                raise ValueError(f"{key}: id must be positive, got {n}")
            ids.add(n)
        return ",".join(str(n) for n in sorted(ids))

    return _validate


# Per-workspace-tab graph collapse state (item 11, Phase 3d / D8). One entry per
# tab id → the domains + label ids folded in that tab's view. Stored as a JSON
# string (the settings store persists via ``str()``, so a normalized dict would
# emit Python repr, not JSON — a string round-trips cleanly, same reasoning as
# the CSV validators). The folding is a per-tab *view arrangement*; the renames
# and labels it references stay durable in the DB regardless.
_GRAPH_COLLAPSE_MAX_TABS = 200
_GRAPH_COLLAPSE_MAX_PER_TAB = 5_000


def _graph_collapse_validator(value: Any) -> str:
    """Normalize the per-tab collapse map to a compact JSON string.

    Accepts the map object directly or a JSON string (idempotent round-trip).
    Each tab entry is ``{"domains": [host, ...], "labels": [id, ...]}``; empty
    entries are dropped so a fully-expanded tab leaves no residue.
    """
    if isinstance(value, str):
        try:
            value = json.loads(value) if value.strip() else {}
        except ValueError as e:
            raise ValueError("graph.collapse: invalid JSON") from e
    if not isinstance(value, dict):
        raise ValueError("graph.collapse must be an object")
    if len(value) > _GRAPH_COLLAPSE_MAX_TABS:
        raise ValueError(f"graph.collapse: too many tabs (max {_GRAPH_COLLAPSE_MAX_TABS})")
    out: dict[str, dict[str, list]] = {}
    for tab, entry in value.items():
        if not isinstance(tab, str) or not tab.strip() or len(tab) > 64:
            raise ValueError("graph.collapse: tab id must be 1–64 chars")
        if not isinstance(entry, dict):
            raise ValueError("graph.collapse: each tab must map to an object")
        raw_domains = entry.get("domains", [])
        raw_labels = entry.get("labels", [])
        if not isinstance(raw_domains, list) or not isinstance(raw_labels, list):
            raise ValueError("graph.collapse: domains and labels must be arrays")
        if len(raw_domains) > _GRAPH_COLLAPSE_MAX_PER_TAB or len(raw_labels) > _GRAPH_COLLAPSE_MAX_PER_TAB:
            raise ValueError(f"graph.collapse: too many entries (max {_GRAPH_COLLAPSE_MAX_PER_TAB})")
        domains: list[str] = []
        seen_d: set[str] = set()
        for d in raw_domains:
            if not isinstance(d, str):
                raise ValueError(f"graph.collapse: domain must be a string, got {d!r}")
            host = d.strip()
            if not host or host in seen_d:
                continue
            seen_d.add(host)
            domains.append(host)
        labels: set[int] = set()
        for lid in raw_labels:
            if isinstance(lid, bool):
                raise ValueError(f"graph.collapse: label id must be an int, got {lid!r}")
            if isinstance(lid, int):
                n = lid
            elif isinstance(lid, str):
                try:
                    n = int(lid)
                except ValueError as e:
                    raise ValueError(f"graph.collapse: bad label id {lid!r}") from e
            else:
                raise ValueError(f"graph.collapse: label id must be an int, got {lid!r}")
            if n < 1:
                raise ValueError(f"graph.collapse: label id must be positive, got {n}")
            labels.add(n)
        if domains or labels:
            out[tab] = {"domains": domains, "labels": sorted(labels)}
    return json.dumps(out, separators=(",", ":"))


# --- Static dispatch table --------------------------------------------------


SETTING_VALIDATORS: dict[str, Callable[[Any], Any]] = {
    "tor.proxy": validate_tor_proxy,
    "tor.kill_switch": _bool_validator,
    # I2P egress. ``i2p.proxy`` is the I2P SOCKS proxy (loopback socks5h, like
    # tor.proxy); ``i2p.enabled`` gates whether .i2p intake is accepted at all.
    "i2p.enabled": _bool_validator,
    "i2p.proxy": validate_i2p_proxy,
    "i2p.kill_switch": _bool_validator,
    # Crawl request cadence. `fast` = no delay, `polite` (default) = short
    # jittered delay, `stealth` = human-scale jittered think-time. Read by the
    # crawl runtime at crawl start. See crawler/runtime.py `_PACING_RANGES`.
    "crawl.pacing": _enum_validator("fast", "polite", "stealth"),
    # Durable crawl queue gate. True pauses dispatch (intake continues).
    "crawl.queue_paused": _bool_validator,
    "browser.path": _browser_path_validator,
    "browser.launch_mode": _enum_validator("fresh", "reuse"),
    "embedding.model": _embedding_model_validator,
    "embedding.auto_start": _bool_validator,
    "llm.model": _llm_model_validator,
    "llm.ollama_url": validate_ollama_url,
    "llm.auto_start": _bool_validator,
    # Worker concurrency: analysis jobs drained per tick (the single capacity
    # number surfaced in the Intel worker controls, item 7). Unset falls back
    # to LlmWorker.batch_limit; 1–50 keeps a bad value from stalling or
    # swamping the worker.
    "llm.batch_size": _int_range_validator(1, 50),
    "llm.auto_enqueue.summary": _bool_validator,
    "llm.auto_enqueue.category": _bool_validator,
    "llm.auto_enqueue.domain_label": _bool_validator,
    "llm.auto_enqueue.entities_llm": _bool_validator,
    "llm.auto_enqueue.risk_score": _bool_validator,
    "graph.color": _enum_validator(
        "none", "domain", "cluster", "depth", "category", "infra", "label"
    ),
    # Label include/exclude graph filters (item 11) — a separate visibility
    # dimension from the server-side ``graph_filters`` term-hide. Exclude wins;
    # a non-empty include is an allowlist.
    "graph.label_include": _id_csv_validator("graph.label_include"),
    "graph.label_exclude": _id_csv_validator("graph.label_exclude"),
    "graph.layout": _enum_validator(
        "force", "radial", "hierarchical", "concentric", "timeline"
    ),
    "graph.edges": _enum_validator("all", "cross-site", "same-site"),
    "graph.show_uncrawled": _bool_validator,
    "graph.hide_orphans": _bool_validator,
    "graph.mutual_only": _bool_validator,
    "graph.group_by_domain": _bool_validator,
    "graph.show_all_edges": _bool_validator,
    "graph.flagged_borders": _bool_validator,
    "graph.isolate": _bool_validator,
    "graph.bridge_highlight": _bool_validator,
    # max_hops: 0 means "no limit"; 1-10 caps the depth from the ego root
    # (or from any node when no ego-focus is active).
    "graph.max_hops": _int_range_validator(0, 10),
    "graph.bridge_betweenness_min": _float_range_validator(0.0, 1.0),
    "graph.bridge_in_degree_min": _int_range_validator(0, 1_000),
    "graph.pinned_ids": _pinned_ids_validator,
    # Per-workspace-tab collapse state (item 11, Phase 3d / D8).
    "graph.collapse": _graph_collapse_validator,
    # Job-history retention: delete terminal job-tracking rows finished more
    # than N days ago. 0 = keep forever (retention off, the default). Enforced
    # at backend startup and on the Settings → Retention "Run cleanup now"
    # button via db.jobs.prune_terminal_jobs. Only work-tracking bookkeeping is
    # pruned — page snapshots and analyses (the investigation record) are never
    # touched. 3650 = a 10-year ceiling so a fat-fingered value can't be absurd.
    "retention.jobs_days": _int_range_validator(0, 3650),
    "search.passive_mode": _bool_validator,
    "workspace.tabs": _workspace_tabs_validator,
    "workspace.active": _workspace_active_validator,
    # The active bottom tab and the customised strip both draw from
    # _BOTTOM_TAB_VALUES (kept in sync with the frontend `BottomTab` union).
    "workspace.bottomTab": _enum_validator(*_BOTTOM_TAB_VALUES),
    "workspace.bottomTabs": _bottom_tabs_validator,
    "nav.leftTab": _enum_validator("search", "intel", "crawl"),
}


# --- Templated key resolution ----------------------------------------------


SEARCH_ENGINE_ENABLED_RE = re.compile(r"^search\.engine\.(\d+)\.enabled$")


class UnknownSettingError(ValueError):
    """Raised when a setting key is not in any validator dispatch.

    Subclasses ``ValueError`` so existing callers using ``except ValueError``
    keep working; routes that want to differentiate unknown-key vs bad-value
    catch this sentinel explicitly first.
    """


def validators_for_key(key: str, db: "CrawlDB") -> Callable[[Any], Any]:
    """Return the validator for ``key``, consulting the DB for templated keys.

    Static keys are looked up in ``SETTING_VALIDATORS``. Templated keys
    (today only the ``search.engine.{id}.enabled`` family) are matched by
    regex; for those the engine id is cross-checked against
    ``search_engines`` and a ``ValueError`` is raised if it doesn't exist.

    Raises ``UnknownSettingError`` (a ``ValueError``) for any key not
    covered by either path.
    """
    if key in SETTING_VALIDATORS:
        return SETTING_VALIDATORS[key]
    m = SEARCH_ENGINE_ENABLED_RE.match(key)
    if m:
        engine_id = int(m.group(1))
        with db.read() as c:
            row = c.execute(
                "SELECT 1 FROM search_engines WHERE id = ?", (engine_id,)
            ).fetchone()
        if row is None:
            raise ValueError(f"unknown search engine id: {engine_id}")
        return _bool_validator
    raise UnknownSettingError(f"unknown setting: {key}")


# --- Read/write surface -----------------------------------------------------


def put_setting(db: "CrawlDB", key: str, value: Any) -> str:
    """Validate, normalize, and persist a setting. Returns the stored value.

    Raises ``UnknownSettingError`` for unknown keys, ``ValueError`` for any
    validator rejection. Both are ``ValueError`` subclasses — callers that
    only need "rejected with 400" can ``except ValueError`` once.
    """
    validator = validators_for_key(key, db)
    normalized = validator(value)
    stored = str(normalized)
    with db.transaction(immediate=True) as c:
        c.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, stored),
        )
    return stored


def get_setting(db: "CrawlDB", key: str) -> str | None:
    """Read a single settings row. Returns ``None`` if absent."""
    with db.read() as c:
        row = c.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    return None if row is None else row[0]


def i2p_enabled(db: "CrawlDB") -> bool:
    """Whether .i2p crawling/intake is turned on for the active project."""
    return (get_setting(db, "i2p.enabled") or "false").strip().lower() == "true"


def validate_intake_url(db: "CrawlDB", url: object) -> str:
    """Validate a crawl-intake URL for the supported networks, honouring the
    ``i2p.enabled`` gate.

    Returns the normalised URL. Raises ``EgressError`` for clearnet, malformed
    ``.onion``/``.i2p`` URLs, or a ``.i2p`` URL while I2P is disabled — so every
    intake site keeps its existing ``except EgressError`` handling. Replaces the
    bare ``validate_onion_url`` gate now that two networks are accepted.
    """
    network, normalised = validate_network_url(url)
    if network == "i2p" and not i2p_enabled(db):
        raise EgressError("i2p crawling is disabled (enable i2p.enabled)")
    return normalised


__all__ = [
    "SETTING_VALIDATORS",
    "SEARCH_ENGINE_ENABLED_RE",
    "UnknownSettingError",
    "validators_for_key",
    "put_setting",
    "get_setting",
    "i2p_enabled",
    "validate_intake_url",
]
