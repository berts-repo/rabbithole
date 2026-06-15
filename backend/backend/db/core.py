"""CrawlDB — the single source of truth for the project database.

This module owns:
  * the `sqlite3` connection (sync, WAL, FK on, sqlite-vec resident),
  * the full schema (every table, index, FTS5 trigger, vec0 virtual table),
  * a reentrant transaction context manager used by every writer in B5–B8,
  * one-shot init steps: defaults seed, response-headers backfill, crash sweep.

Per the locked decision in the B2 plan, this is the only file in `db/` that
ships real logic in B2. Sibling modules (`nodes.py`, `crawl.py`, etc.) are
stubs that B5–B8 will populate alongside the routes that use them.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import sqlite_vec


SCHEMA_VERSION = 7

# Default fastembed model is BAAI/bge-small-en-v1.5 (384 dims). The embed
# worker in B8 handles drop+recreate of the vec0 table if the user picks a
# model with a different dimension.
EMBED_DIM = 384
DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"

DEFAULT_SETTINGS: dict[str, str] = {
    "tor.proxy": "socks5h://127.0.0.1:9050",
    "tor.kill_switch": "true",
    # I2P egress (eepsite crawling). Off by default — a project behaves exactly
    # like a Tor-only project until the analyst enables it. Routing reuses the
    # Tor SOCKS model via I2P's SOCKS proxy (i2pd default 4447); see
    # security/net.py. ``i2p.kill_switch`` mirrors ``tor.kill_switch``.
    "i2p.enabled": "false",
    "i2p.proxy": "socks5h://127.0.0.1:4447",
    "i2p.kill_switch": "true",
    "browser.launch_mode": "fresh",
    # When "true", the Search tab queries configured engines and emits their
    # discovered URLs but skips the per-URL probe stage that fetches
    # title/description from each unknown onion. Default off keeps the
    # active-preview UX; analysts who want a quieter Tor footprint flip it on.
    "search.passive_mode": "false",
    "embedding.model": DEFAULT_EMBED_MODEL,
    "embedding.auto_start": "true",
    # B8 LLM defaults: lightweight Qwen variant that fits 8 GB VMs alongside
    # the embedding model. Analyst can swap to qwen2.5:7b or similar via
    # Settings → Engines once they have headroom.
    "llm.model": "qwen2.5:3b",
    "llm.ollama_url": "http://127.0.0.1:11434",
    "llm.auto_start": "false",
    "llm.auto_enqueue.summary": "true",
    "llm.auto_enqueue.category": "false",
    "llm.auto_enqueue.domain_label": "false",
    "llm.auto_enqueue.entities_llm": "false",
    "llm.auto_enqueue.risk_score": "false",
    # LLM worker batch size — how many pending analysis jobs the worker claims
    # and drains per tick (item 7 "worker capacity"; a single concurrency
    # number, not a per-analyzer pool). Surfaced in the Intel worker controls.
    "llm.batch_size": "5",
    # Durable crawl queue gate. When "true", the queue runner stops dispatching
    # new rows; intake surfaces continue to enqueue (paused = "loaded but not
    # running"). Mirrors the kill-switch insert-allowed-dispatch-blocked shape.
    "crawl.queue_paused": "false",
}


# ---------------------------------------------------------------------------
# Schema DDL  (SCHEMA_VERSION = 7 — resources.network discriminant; see
#              _migrate_schema for the non-destructive forward upgrade)
# ---------------------------------------------------------------------------
#
# Layout choices that matter for correctness:
#   * The god table `nodes` is gone. URL identity (`resources`), crawled
#     content + analyst page state (`pages`), per-crawl snapshots
#     (`page_versions`), and render/layout metadata (`graph_nodes`) are
#     separate tables. One URL → one `resources` row → one `pages` row → many
#     `page_versions` rows.
#   * One canonical lifecycle vocabulary lives on `resources.state`
#     (unknown / known / crawled / dead). There is no more `stub` boolean and
#     no `crawl_queue.lookup_state`.
#   * All work/queue tracking is one `jobs` table with one status vocabulary
#     (pending / running / done / failed / cancelled / paused). `crawl_queue`
#     is gone — pending crawl work is a `jobs` row with kind='crawl'.
#   * Tables that keep durable identity stay typed and link to their `jobs`
#     row rather than carrying their own status: `crawls`, `analyses`,
#     `collection_analyses` lose their `status` column; `monitors` loses
#     `last_status`. Recipe tables (`crawl_schedules`, `monitors`) spawn jobs
#     when they fire.
#   * Tables are declared in FK-dependency order. The one cycle
#     (`pages.current_version_id` → `page_versions(id)` and
#     `page_versions.page_id` → `pages(id)`) is fine: SQLite resolves FK
#     targets at row-modification time, not at CREATE. `pages` is declared
#     first; `current_version_id` starts NULL and is set after the first
#     version row exists.
#   * Every child table FKs its parent with ON DELETE CASCADE unless the spec
#     calls for SET NULL (collection bindings) — `findings.page_version_id`
#     uses SET NULL so a finding survives version pruning.
#   * CHECK constraints encode every enum the spec defines — bad values never
#     reach disk.
#   * Bools are stored as INTEGER (0/1) — sqlite's native idiom.
#   * FTS5 is contentless `pages_fts`, keyed per page (rowid = pages.id), over
#     the *current* version's clean text. The old `nodes_fts` triggers are
#     gone; maintenance moves into the crawl write transaction (drop the stale
#     current row, insert the new current text) because the indexed text now
#     lives in `page_versions`, not in the keyed table.

_SCHEMA_STATEMENTS: tuple[str, ...] = (
    # --- versioning -------------------------------------------------------
    """CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY CHECK (version > 0)
    )""",

    # =====================================================================
    # config / curated tables (survive in shape, FK-independent first)
    # =====================================================================
    """CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    )""",

    """CREATE TABLE IF NOT EXISTS search_engines (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        label   TEXT,
        url     TEXT UNIQUE NOT NULL,
        network TEXT NOT NULL DEFAULT 'tor'
            CHECK (network IN ('tor','i2p'))
    )""",

    """CREATE TABLE IF NOT EXISTS watchlist (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        term TEXT    UNIQUE NOT NULL
    )""",

    # graph_filters: explicitly OUT OF SCOPE for the reset. Unchanged
    # term-based hide list; label-system.md (item 11) owns its future.
    """CREATE TABLE IF NOT EXISTS graph_filters (
        term TEXT PRIMARY KEY
    )""",

    """CREATE TABLE IF NOT EXISTS domains (
        host      TEXT PRIMARY KEY,
        alias     TEXT,
        last_seen TEXT
    )""",

    # bookmarks
    """CREATE TABLE IF NOT EXISTS seeds (
        url      TEXT PRIMARY KEY,
        label    TEXT,
        added_at TEXT
    )""",

    # ``name`` uses ``COLLATE NOCASE`` so lazy find-or-create can't fragment
    # "Investigations" and "investigations". Stored values keep the user's
    # casing; only comparisons are case-insensitive.
    """CREATE TABLE IF NOT EXISTS collections (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    NOT NULL UNIQUE COLLATE NOCASE,
        description TEXT
    )""",

    # =====================================================================
    # core lifecycle: resource / page / version split
    # =====================================================================
    """CREATE TABLE IF NOT EXISTS resources (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        url               TEXT    UNIQUE NOT NULL,
        host              TEXT    NOT NULL,
        network           TEXT    NOT NULL DEFAULT 'tor'
            CHECK (network IN ('tor','i2p')),
        state             TEXT    NOT NULL CHECK (state IN
            ('unknown','known','crawled','dead')),
        first_seen        TEXT    NOT NULL,
        last_seen         TEXT,
        last_state_change TEXT,
        FOREIGN KEY (host) REFERENCES domains(host) ON DELETE CASCADE
    )""",

    # current_version_id is a cached pointer into page_versions, advanced in
    # the same transaction as a new version insert. The forward FK reference
    # to page_versions resolves at insert time (see header note).
    """CREATE TABLE IF NOT EXISTS pages (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        resource_id        INTEGER NOT NULL UNIQUE
            REFERENCES resources(id) ON DELETE CASCADE,
        current_version_id INTEGER REFERENCES page_versions(id),
        summary            TEXT,
        category           TEXT,
        reviewed           INTEGER NOT NULL DEFAULT 0,
        analysis_excluded  INTEGER NOT NULL DEFAULT 0,
        embed_excluded     INTEGER NOT NULL DEFAULT 0,
        opened_at          TEXT,
        created_at         TEXT,
        alias              TEXT
    )""",

    """CREATE TABLE IF NOT EXISTS page_versions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        page_id         INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
        fetched_at      TEXT    NOT NULL,
        http_status     INTEGER,
        body_text       TEXT,
        body_text_clean TEXT,
        body_hash       TEXT,
        title           TEXT,
        content_changed INTEGER
    )""",

    # =====================================================================
    # graph metadata
    # =====================================================================
    """CREATE TABLE IF NOT EXISTS graph_nodes (
        resource_id INTEGER PRIMARY KEY
            REFERENCES resources(id) ON DELETE CASCADE,
        x           REAL,
        y           REAL,
        cluster     INTEGER,
        pagerank    REAL,
        betweenness REAL
    )""",

    # =====================================================================
    # headers — current page version only
    # =====================================================================
    """CREATE TABLE IF NOT EXISTS response_headers (
        page_version_id INTEGER NOT NULL,
        key             TEXT    NOT NULL,
        value           TEXT,
        PRIMARY KEY (page_version_id, key),
        FOREIGN KEY (page_version_id) REFERENCES page_versions(id) ON DELETE CASCADE
    )""",

    # =====================================================================
    # edges — re-pointed to resources
    # =====================================================================
    """CREATE TABLE IF NOT EXISTS edges (
        from_id     INTEGER NOT NULL,
        to_id       INTEGER NOT NULL,
        anchor_text TEXT,
        source      TEXT    NOT NULL CHECK (source IN ('crawl', 'analyst')),
        label       TEXT,
        PRIMARY KEY (from_id, to_id),
        FOREIGN KEY (from_id) REFERENCES resources(id) ON DELETE CASCADE,
        FOREIGN KEY (to_id)   REFERENCES resources(id) ON DELETE CASCADE
    )""",

    # =====================================================================
    # findings — absorbs entities + notes. page_version_id NULL = applies to
    # the resource generally; set = came from that crawl's content. Entity
    # type + source live in metadata JSON (the old entities CHECK enum is now
    # write-path validation in db/findings.py).
    # =====================================================================
    """CREATE TABLE IF NOT EXISTS findings (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        resource_id     INTEGER REFERENCES resources(id) ON DELETE CASCADE,
        page_version_id INTEGER REFERENCES page_versions(id) ON DELETE SET NULL,
        kind            TEXT NOT NULL CHECK (kind IN ('entity','note')),
        value           TEXT NOT NULL,
        metadata        TEXT,
        created_at      TEXT
    )""",

    # =====================================================================
    # collection membership — re-pointed to resources
    # =====================================================================
    """CREATE TABLE IF NOT EXISTS collection_items (
        collection_id INTEGER NOT NULL,
        node_id       INTEGER NOT NULL,
        PRIMARY KEY (collection_id, node_id),
        FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
        FOREIGN KEY (node_id)       REFERENCES resources(id)   ON DELETE CASCADE
    )""",

    # =====================================================================
    # crawl execution detail (typed, linked from jobs) — no status column;
    # work-tracking status lives on the linked jobs row.
    # =====================================================================
    """CREATE TABLE IF NOT EXISTS crawls (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        seed_url        TEXT    NOT NULL,
        mode            TEXT    NOT NULL CHECK (mode IN
            ('Cross-site','BFS','DFS','Diverse','Focused')),
        collection_id   INTEGER,
        pages_crawled   INTEGER NOT NULL DEFAULT 0,
        pages_failed    INTEGER NOT NULL DEFAULT 0,
        pages_queued    INTEGER NOT NULL DEFAULT 0,
        pages_skipped   INTEGER NOT NULL DEFAULT 0,
        max_depth       INTEGER,
        started_at      TEXT,
        completed_at    TEXT,
        paused_at       TEXT,
        error           TEXT,
        FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE SET NULL
    )""",

    """CREATE TABLE IF NOT EXISTS crawl_nodes (
        crawl_id INTEGER NOT NULL,
        node_id  INTEGER NOT NULL,
        depth    INTEGER,
        PRIMARY KEY (crawl_id, node_id),
        FOREIGN KEY (crawl_id) REFERENCES crawls(id)    ON DELETE CASCADE,
        FOREIGN KEY (node_id)  REFERENCES resources(id) ON DELETE CASCADE
    )""",

    # =====================================================================
    # recipe tables (spawn jobs when they fire)
    # =====================================================================
    """CREATE TABLE IF NOT EXISTS crawl_schedules (
        url            TEXT PRIMARY KEY,
        label          TEXT,
        interval_hours REAL NOT NULL,
        mode           TEXT NOT NULL CHECK (mode IN
            ('Cross-site','BFS','DFS','Diverse','Focused')),
        active         INTEGER NOT NULL DEFAULT 1,
        collection_id  INTEGER,
        FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE SET NULL
    )""",

    # last_status dropped — read latest from probes / jobs.
    """CREATE TABLE IF NOT EXISTS monitors (
        id                        INTEGER PRIMARY KEY AUTOINCREMENT,
        url                       TEXT    UNIQUE NOT NULL,
        label                     TEXT,
        interval_hours            REAL    NOT NULL,
        enabled                   INTEGER NOT NULL DEFAULT 1,
        alert_on_change           INTEGER NOT NULL DEFAULT 1,
        alert_on_restore          INTEGER NOT NULL DEFAULT 1,
        downtime_threshold_hours  REAL    NOT NULL DEFAULT 48
    )""",

    # monitor history / uptime time series (typed). ``body_hash`` +
    # ``content_changed`` (schema v4) let a probe detect meaningful content
    # drift, not just an HTTP status — the daemon hashes the fetched clean text
    # (same hash as page_versions) and flags a change vs the prior probe.
    """CREATE TABLE IF NOT EXISTS probes (
        monitor_id      INTEGER NOT NULL,
        checked_at      TEXT    NOT NULL,
        status_code     INTEGER,
        body_hash       TEXT,
        content_changed INTEGER,
        PRIMARY KEY (monitor_id, checked_at),
        FOREIGN KEY (monitor_id) REFERENCES monitors(id) ON DELETE CASCADE
    )""",

    # =====================================================================
    # analyses (typed, retained) — status column dropped; target FK follows
    # the resource split.
    # =====================================================================
    # The `prompt_id` columns (added at v5) are nullable FKs to
    # `prompt_templates`: NULL = the ad-hoc free-form prompt that has always
    # been the only mode; a set id = an analysis run from a saved template.
    # Fresh DBs get the column here; existing DBs get it via _migrate_schema's
    # guarded ALTER (item 7, decision D3).
    """CREATE TABLE IF NOT EXISTS analyses (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        resource_id   INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
        analysis_type TEXT    NOT NULL,
        model         TEXT,
        result        TEXT,
        question      TEXT,
        priority      INTEGER NOT NULL DEFAULT 0,
        prompt_id     INTEGER REFERENCES prompt_templates(id) ON DELETE SET NULL,
        created_at    TEXT,
        updated_at    TEXT
    )""",

    """CREATE TABLE IF NOT EXISTS collection_analyses (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
        analysis_type TEXT    NOT NULL,
        model         TEXT,
        result        TEXT,
        prompt_id     INTEGER REFERENCES prompt_templates(id) ON DELETE SET NULL,
        created_at    TEXT,
        updated_at    TEXT
    )""",

    # =====================================================================
    # analysis-intel tables (item 7, added at SCHEMA_VERSION 5). Additive on
    # top of the post-reset schema — created IF NOT EXISTS so an existing v4
    # DB grows them on next open with no data loss.
    # =====================================================================
    #
    # prompt_templates: named analyzer prompts. Built-in presets ship with
    # builtin=1 — they can be hidden (hidden=1) but not deleted; analyst
    # templates are builtin=0 and fully editable. Project-local (decision D3).
    """CREATE TABLE IF NOT EXISTS prompt_templates (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT    NOT NULL,
        analysis_type TEXT    NOT NULL,
        body          TEXT    NOT NULL,
        builtin       INTEGER NOT NULL DEFAULT 0 CHECK (builtin IN (0, 1)),
        hidden        INTEGER NOT NULL DEFAULT 0 CHECK (hidden IN (0, 1)),
        created_at    TEXT,
        updated_at    TEXT
    )""",

    # auto_analysis_rules: the single typed home for auto-analysis (decision
    # D4). trigger_kind 'crawl' = run analyzer on every newly crawled page;
    # 'collection_add' = run analyzer when a page is added to the collection
    # named in target_filter JSON ({"collection_id": N}). model NULL → fall
    # back to the llm.model setting at fire time. prompt_id NULL → free-form.
    """CREATE TABLE IF NOT EXISTS auto_analysis_rules (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        trigger_kind  TEXT    NOT NULL CHECK (trigger_kind IN
            ('crawl','collection_add')),
        analysis_type TEXT    NOT NULL,
        model         TEXT,
        prompt_id     INTEGER REFERENCES prompt_templates(id) ON DELETE SET NULL,
        target_filter TEXT,
        enabled       INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
        created_at    TEXT,
        updated_at    TEXT
    )""",

    # cluster_analyses: cluster Q&A and cluster-scoped analyses (decision D1).
    # Clusters drift across layout/algorithm runs, so the durable key is a
    # cluster *fingerprint* (sorted member resource_ids hashed), plus a
    # denormalized label snapshot the analyst saw at compose time. The
    # `resource_ids` JSON array is the membership snapshot taken at compose
    # time: the fingerprint is one-way, so the worker needs the concrete ids
    # to fetch each member's page body for the synthesis. Mirrors `analyses`
    # so the typed-row + linked-job pattern in db/llm.py carries over
    # (target_type='cluster', target_id = a synthetic per-row id).
    """CREATE TABLE IF NOT EXISTS cluster_analyses (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        fingerprint   TEXT    NOT NULL,
        resource_ids  TEXT    NOT NULL DEFAULT '[]',
        label         TEXT,
        analysis_type TEXT    NOT NULL,
        model         TEXT,
        result        TEXT,
        question      TEXT,
        prompt_id     INTEGER REFERENCES prompt_templates(id) ON DELETE SET NULL,
        priority      INTEGER NOT NULL DEFAULT 0,
        created_at    TEXT,
        updated_at    TEXT
    )""",

    # =====================================================================
    # flags (typed, retained) — own workflow vocabulary, node_id → resources.
    # status is an analyst workflow, NOT the unified job vocabulary.
    # =====================================================================
    """CREATE TABLE IF NOT EXISTS flags (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id  INTEGER NOT NULL,
        status   TEXT    NOT NULL CHECK (status IN
            ('pending','flagged','investigating','done','dismissed')),
        source   TEXT    NOT NULL DEFAULT 'analyst' CHECK (source IN
            ('watchlist','analyst')),
        priority INTEGER NOT NULL CHECK (priority IN (1,2,3)),
        note     TEXT,
        FOREIGN KEY (node_id) REFERENCES resources(id) ON DELETE CASCADE
    )""",

    # =====================================================================
    # unified work-tracking. One row per piece of work across every source;
    # kind-specific config + back-references live in payload (JSON).
    # =====================================================================
    """CREATE TABLE IF NOT EXISTS jobs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        kind        TEXT    NOT NULL CHECK (kind IN
            ('crawl','schedule','analysis','probe','live-crawl','batch')),
        target_type TEXT    NOT NULL CHECK (target_type IN
            ('url','domain','collection','cluster')),
        target_id   INTEGER NOT NULL,
        status      TEXT    NOT NULL CHECK (status IN
            ('pending','running','done','failed','cancelled','paused')),
        payload     TEXT,
        result      TEXT,
        error       TEXT,
        created_at  TEXT,
        started_at  TEXT,
        finished_at TEXT
    )""",

    # =====================================================================
    # label system (item 11, added at SCHEMA_VERSION 6). Additive on top of
    # the post-reset schema — created IF NOT EXISTS so an existing v5 DB grows
    # them on next open with no data loss. Two *typed* join tables, not one
    # polymorphic (target_type, target_id) table, because resources(id) is
    # INTEGER and domains(host) is TEXT — typed FKs give clean cascade-on-delete
    # (decision D2). Labels are deliberately NOT a `findings` kind: they need a
    # managed taxonomy (preset palette, color, builtin) and referential
    # integrity a stringly-typed findings row loses.
    # =====================================================================
    #
    # `rank` is the single analyst-controlled ordering (decision D5) that
    # resolves collapse-home, dominant-label color, and picker order — lower
    # number ranks higher (warnings seeded at the top). `hidden` is the preset
    # hide-from-picker toggle (decision D3); presets can be recolored/hidden but
    # never deleted.
    """CREATE TABLE IF NOT EXISTS labels (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    UNIQUE NOT NULL,
        color       TEXT,
        description TEXT,
        builtin     INTEGER NOT NULL DEFAULT 0 CHECK (builtin IN (0, 1)),
        rank        INTEGER NOT NULL DEFAULT 0,
        hidden      INTEGER NOT NULL DEFAULT 0 CHECK (hidden IN (0, 1)),
        created_at  TEXT
    )""",

    """CREATE TABLE IF NOT EXISTS resource_labels (
        label_id    INTEGER NOT NULL REFERENCES labels(id)    ON DELETE CASCADE,
        resource_id INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
        PRIMARY KEY (label_id, resource_id)
    )""",

    """CREATE TABLE IF NOT EXISTS domain_labels (
        label_id INTEGER NOT NULL REFERENCES labels(id)    ON DELETE CASCADE,
        host     TEXT    NOT NULL REFERENCES domains(host)  ON DELETE CASCADE,
        PRIMARY KEY (label_id, host)
    )""",
)

_INDEX_STATEMENTS: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_resources_host        ON resources(host)",
    "CREATE INDEX IF NOT EXISTS idx_resources_state       ON resources(state)",
    "CREATE INDEX IF NOT EXISTS idx_resources_last_seen   ON resources(last_seen)",
    "CREATE INDEX IF NOT EXISTS page_versions_page_idx    ON page_versions(page_id, fetched_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_graph_nodes_cluster   ON graph_nodes(cluster)",
    "CREATE INDEX IF NOT EXISTS idx_response_headers_kv   ON response_headers(key, value)",
    "CREATE INDEX IF NOT EXISTS idx_edges_from            ON edges(from_id)",
    "CREATE INDEX IF NOT EXISTS idx_edges_to              ON edges(to_id)",
    "CREATE INDEX IF NOT EXISTS idx_findings_resource     ON findings(resource_id)",
    "CREATE INDEX IF NOT EXISTS idx_findings_kind         ON findings(kind)",
    "CREATE INDEX IF NOT EXISTS idx_collection_items_node ON collection_items(node_id)",
    "CREATE INDEX IF NOT EXISTS idx_crawl_nodes_node      ON crawl_nodes(node_id)",
    "CREATE INDEX IF NOT EXISTS idx_probes_monitor        ON probes(monitor_id, checked_at)",
    "CREATE INDEX IF NOT EXISTS idx_analyses_resource     ON analyses(resource_id)",
    "CREATE INDEX IF NOT EXISTS idx_flags_status          ON flags(status)",
    "CREATE INDEX IF NOT EXISTS idx_flags_node            ON flags(node_id)",
    "CREATE INDEX IF NOT EXISTS jobs_status_idx           ON jobs(status)",
    "CREATE INDEX IF NOT EXISTS jobs_kind_idx             ON jobs(kind)",
    "CREATE INDEX IF NOT EXISTS idx_cluster_analyses_fp   ON cluster_analyses(fingerprint)",
    "CREATE INDEX IF NOT EXISTS idx_auto_rules_trigger    ON auto_analysis_rules(trigger_kind, enabled)",
    "CREATE INDEX IF NOT EXISTS idx_prompt_templates_type ON prompt_templates(analysis_type)",
    "CREATE INDEX IF NOT EXISTS idx_resource_labels_resource ON resource_labels(resource_id)",
    "CREATE INDEX IF NOT EXISTS idx_domain_labels_host      ON domain_labels(host)",
    "CREATE INDEX IF NOT EXISTS idx_labels_rank             ON labels(rank)",
)

# FTS5 contentless index over the *current* page version's clean text, keyed
# per page (rowid = pages.id). No triggers — the indexed text lives in
# page_versions, so maintenance happens in the crawl write transaction
# (delete the stale current row, insert the new current text) when
# pages.current_version_id advances.
_FTS_STATEMENTS: tuple[str, ...] = (
    """CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
        body_text_clean,
        content=''
    )""",
)

_VEC_STATEMENT = f"""CREATE VIRTUAL TABLE IF NOT EXISTS embeddings USING vec0(
    page_id    INTEGER PRIMARY KEY,
    vector     FLOAT[{EMBED_DIM}],
    +model     TEXT,
    +created_at TEXT
)"""


# Tables that legitimately exist after init. Used by tests + sanity checks.
EXPECTED_TABLES: frozenset[str] = frozenset({
    "schema_version",
    "settings",
    "search_engines",
    "watchlist",
    "graph_filters",
    "domains",
    "seeds",
    "collections",
    "resources",
    "pages",
    "page_versions",
    "graph_nodes",
    "response_headers",
    "edges",
    "findings",
    "collection_items",
    "crawls",
    "crawl_nodes",
    "crawl_schedules",
    "monitors",
    "probes",
    "analyses",
    "collection_analyses",
    "prompt_templates",
    "auto_analysis_rules",
    "cluster_analyses",
    "flags",
    "jobs",
    "labels",
    "resource_labels",
    "domain_labels",
})


# Built-in analyzer prompt presets seeded into `prompt_templates` (builtin=1).
# These mirror the analysis types the LLM worker already understands; the body
# is the analyst-editable instruction text. A NULL `analyses.prompt_id` still
# means "free-form / engine default" — presets are an opt-in convenience, not a
# behavior change. Seeded idempotently by (name) so re-running init is a no-op.
PRESET_PROMPTS: tuple[tuple[str, str, str], ...] = (
    ("Summary", "Summary",
     "Summarise the page content in clear, concise prose."),
    ("Risk Score", "Risk Score",
     "Rate the danger/sensitivity of this page and justify the score."),
    ("Entities", "Entities (LLM)",
     "Extract the people, organisations, and locations named on this page."),
    ("Category", "Category",
     "Classify the subject area of this page in a few words."),
    ("Domain Label", "Domain Label",
     "Infer a short human-readable label for this .onion domain."),
    ("Q&A", "Q&A",
     "Answer the analyst's question using only this page's content."),
)


# Built-in label presets seeded into `labels` (builtin=1) — the locked starter
# taxonomy (decision D3). `rank` is the single analyst ordering (decision D5):
# lower number ranks higher, so the warning tags (`Avoid`, `Scam`) seed at the
# top and stay the *complete* set when a page also carries a weaker label.
# Presets recolor/redescribe and hide but never delete; custom labels (builtin=0)
# are fully editable. Colors are dark-theme swatches (see `--bg: #0a0f0d`).
# Tuple shape: (name, color, description, rank).
PRESET_LABELS: tuple[tuple[str, str, str, int], ...] = (
    ("Avoid",     "#ff5470", "Analyst exclusion tag — drives the avoidance filter.", 0),
    ("Scam",      "#ff8c42", "Known scam / phishing site.",                          1),
    ("Market",    "#00d4aa", "Commerce / vendor listings.",                          2),
    ("Forum",     "#4d9fff", "Discussion boards.",                                   3),
    ("Directory", "#b07cff", "Link indexes.",                                        4),
    ("Blog",      "#ffd166", "Single-author content.",                               5),
    ("Service",   "#5fd0c4", "Paste, mail, search, util.",                           6),
)


class CrawlDB:
    """Sync sqlite3 wrapper. One instance owns one DB file.

    Threading: a single `sqlite3.Connection` is shared across threads
    (`check_same_thread=False`) and guarded by an `RLock`. The transaction
    context manager is reentrant so callers can compose helpers safely.

    Concurrency model for the rest of the backend: route handlers declared
    as plain `def` (not `async def`) are dispatched on Starlette's thread
    pool, which keeps the FastAPI event loop responsive while sync queries
    run. See B2 plan.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._conn = sqlite3.connect(
            self.path,
            check_same_thread=False,
            # autocommit mode — we manage transactions explicitly via the
            # context manager. Pragmas and DDL run outside a transaction.
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._depth = threading.local()

        self._configure_connection()
        self._init_schema()
        self._seed_defaults()
        self._seed_auto_rules()
        self._sweep_stale_jobs()

    # -- connection setup --------------------------------------------------

    def _configure_connection(self) -> None:
        c = self._conn
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA busy_timeout=5000")
        # Load sqlite-vec, then immediately re-disable extension loading so
        # nothing else can load arbitrary extensions through this handle.
        c.enable_load_extension(True)
        sqlite_vec.load(c)
        c.enable_load_extension(False)

    # -- schema init -------------------------------------------------------

    def _init_schema(self) -> None:
        with self.transaction(immediate=True) as c:
            for stmt in _SCHEMA_STATEMENTS:
                c.execute(stmt)
            for stmt in _INDEX_STATEMENTS:
                c.execute(stmt)
            for stmt in _FTS_STATEMENTS:
                c.execute(stmt)
            c.execute(_VEC_STATEMENT)
            self._migrate_schema(c)
            self._seed_preset_prompts(c)
            self._seed_preset_labels(c)

    @staticmethod
    def _ensure_column(
        c: sqlite3.Connection, table: str, column: str, decl: str
    ) -> None:
        """Idempotently ``ALTER TABLE ... ADD COLUMN`` when the column is absent.

        The guard reads ``PRAGMA table_info`` so re-running init never errors.
        SQLite only allows ``ADD COLUMN`` with a ``REFERENCES`` clause when the
        default is NULL, which is exactly the shape of every column we add here.
        """
        cols = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")

    def _migrate_schema(self, c: sqlite3.Connection) -> None:
        """Non-destructive forward migration of an existing DB to ``SCHEMA_VERSION``.

        The schema-reset cutover (→ v4) was a DB delete with no in-place path.
        Every step since (→ v5 analysis-intel, → v6 label system) is
        deliberately additive: new tables are created by ``_SCHEMA_STATEMENTS``
        (CREATE IF NOT EXISTS) and seeded idempotently in ``_init_schema``; the
        only in-place changes are backfilling nullable columns onto pre-existing
        tables (``prompt_id`` at v5, ``pages.alias`` at v6). No data is read,
        rewritten, or dropped. A fresh DB seeds the version row; an older DB is
        upgraded and its version stamped forward. The ``_ensure_column`` calls
        are idempotent, so re-running every step on each open is harmless.
        """
        row = c.execute(
            "SELECT version FROM schema_version LIMIT 1"
        ).fetchone()
        if row is None:
            c.execute(
                "INSERT INTO schema_version(version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
            return
        current = int(row["version"])
        if current >= SCHEMA_VERSION:
            return
        # v4 → v5: additive analysis-intel columns. The tables themselves are
        # already present (CREATE IF NOT EXISTS ran above).
        fk = "INTEGER REFERENCES prompt_templates(id) ON DELETE SET NULL"
        self._ensure_column(c, "analyses", "prompt_id", fk)
        self._ensure_column(c, "collection_analyses", "prompt_id", fk)
        # cluster_analyses gained a membership snapshot after its initial v5
        # shape (the fingerprint alone can't be reversed to fetch pages).
        self._ensure_column(
            c, "cluster_analyses", "resource_ids", "TEXT NOT NULL DEFAULT '[]'"
        )
        # v5 → v6: page rename column. The label tables are created + seeded by
        # _init_schema; this is the only in-place change.
        self._ensure_column(c, "pages", "alias", "TEXT")
        # v6 → v7: network discriminant on resources. Every pre-v7 row is an
        # onion crawl, so the constant 'tor' default backfills correctly; new
        # rows get their network from network_of_host at upsert time.
        self._ensure_column(
            c,
            "resources",
            "network",
            "TEXT NOT NULL DEFAULT 'tor' CHECK (network IN ('tor','i2p'))",
        )
        # search_engines also gains a network discriminant; every pre-v7 engine
        # is an onion search engine, so the 'tor' default backfills correctly.
        self._ensure_column(
            c,
            "search_engines",
            "network",
            "TEXT NOT NULL DEFAULT 'tor' CHECK (network IN ('tor','i2p'))",
        )
        c.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))

    @staticmethod
    def _seed_preset_prompts(c: sqlite3.Connection) -> None:
        """Insert the built-in analyzer presets once, idempotently by name."""
        when = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for name, analysis_type, body in PRESET_PROMPTS:
            c.execute(
                "INSERT INTO prompt_templates"
                "(name, analysis_type, body, builtin, hidden, created_at, updated_at) "
                "SELECT ?, ?, ?, 1, 0, ?, ? "
                "WHERE NOT EXISTS "
                "(SELECT 1 FROM prompt_templates WHERE name = ? AND builtin = 1)",
                (name, analysis_type, body, when, when, name),
            )

    @staticmethod
    def _seed_preset_labels(c: sqlite3.Connection) -> None:
        """Insert the built-in label presets once, idempotently by name.

        Seeded with ``builtin=1`` so they can be recolored/hidden but never
        deleted. The ``WHERE NOT EXISTS`` guard keeps a re-run migration (and a
        re-open of an already-seeded DB) a no-op without disturbing an
        analyst's edits to a preset's color/description/rank.
        """
        when = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for name, color, description, rank in PRESET_LABELS:
            c.execute(
                "INSERT INTO labels"
                "(name, color, description, builtin, rank, hidden, created_at) "
                "SELECT ?, ?, ?, 1, ?, 0, ? "
                "WHERE NOT EXISTS (SELECT 1 FROM labels WHERE name = ?)",
                (name, color, description, rank, when, name),
            )

    def _seed_defaults(self) -> None:
        with self.transaction(immediate=True) as c:
            for key, value in DEFAULT_SETTINGS.items():
                c.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                    (key, value),
                )

    def _seed_auto_rules(self) -> None:
        """Seed the crawl-kind auto-analysis rules from the legacy settings.

        Runs after ``_seed_defaults`` so the ``llm.auto_enqueue.*`` rows the
        seed reads are present (item 7, D4). Idempotent — a no-op once the rules
        exist, so it is safe to run on every open.
        """
        from . import auto_rules as auto_rules_db

        auto_rules_db.seed_crawl_rules(self)

    def _sweep_stale_jobs(self) -> None:
        """Fail out any job left ``running`` by a prior process.

        Replaces the old ``_sweep_stale_crawls`` + ``_sweep_stale_queue_rows``
        pair: with the unified ``jobs`` table, all in-flight work-tracking
        lives in one place. ``pending`` jobs are the queue and survive the
        restart untouched (they get re-dispatched); only ``running`` jobs —
        which had a live worker that no longer exists — are reconciled to
        ``failed``. Live-crawl / queue recovery derives from ``jobs``.

        Runs at every DB open so the invariant "no row in ``running`` outside
        an active process" holds regardless of which subsystem starts first.
        """
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.transaction(immediate=True) as c:
            c.execute(
                "UPDATE jobs SET status='failed', "
                "error='process restarted', finished_at=? "
                "WHERE status='running'",
                (now,),
            )

    # -- read primitive ---------------------------------------------------

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        """Lock-guarded, SELECT-only access to the connection.

        Mirrors :meth:`transaction` but issues no ``BEGIN``/``COMMIT`` — for
        read paths that only run ``SELECT``s. Holding the lock across several
        statements yields a consistent snapshot relative to other threads'
        writes (writers acquire the same lock via :meth:`transaction`).

        ``_lock`` is an ``RLock``, so ``read()`` composes safely inside an
        open ``transaction()`` and vice versa. This is the read counterpart
        of the DB-access seam: ``db/`` modules call ``read()`` rather than
        reaching into the private connection.
        """
        with self._lock:
            yield self._conn

    # -- transaction primitive --------------------------------------------

    @contextmanager
    def transaction(self, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        """Reentrant transaction. Outermost level commits or rolls back;
        nested levels are no-ops (savepoints aren't worth the complexity
        for our access patterns).

        ``immediate=True`` issues ``BEGIN IMMEDIATE`` so the writer lock is
        acquired up front — needed for queue-claim flows that do
        SELECT-then-UPDATE atomically.
        """
        with self._lock:
            depth = getattr(self._depth, "depth", 0)
            self._depth.depth = depth + 1
            if depth == 0:
                self._conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            try:
                yield self._conn
            except Exception:
                if depth == 0:
                    self._conn.execute("ROLLBACK")
                raise
            else:
                if depth == 0:
                    self._conn.execute("COMMIT")
            finally:
                self._depth.depth = depth

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "CrawlDB":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
