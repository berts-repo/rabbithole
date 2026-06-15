# Schema Reset — Consolidated Schema Artifact

## Purpose

This is the single reviewable schema for the Schema Reset Milestone
(`schema-reset.md`), satisfying that spec's "Implementation Order Within
the Reset" **step 1**: *"Design the full new schema as one artifact.
Review before any code."*

It gathers DDL scattered across `schema-reset.md` and
`unified-activity-view.md` into one CREATE script in dependency order,
maps every current column to its new home, records the internal-shape
decisions made while consolidating, and flags one genuine contradiction
between the two source specs.

**This artifact is a design review target, not implementation.** It lands
as queue item 6, after the four frontend packages
(`pane-responsibility-reset.md`, `shared-ui-primitives.md`,
`graphcanvas-decomposition.md`, `list-to-graph-tabs.md`) per `NEXT.md`.
Nothing here should be built before those land — but it is reviewable now,
and review is order-independent.

Current schema baseline read from `backend/backend/db/core.py`
(`SCHEMA_VERSION = 2`). New schema is seeded fresh at `SCHEMA_VERSION = 3`
via DB-delete; no migration path (see `schema-reset.md` → "Migration
Approach").

---

## Full CREATE Script (dependency order)

Ordered so every FK target is created first. The one exception is the
`pages` ↔ `page_versions` cycle (`pages.current_version_id` →
`page_versions(id)` and `page_versions.page_id` → `pages(id)`): SQLite
records a forward FK reference to a not-yet-created table and only enforces
it at row-modification time, so `pages` is declared before `page_versions`
and the cycle resolves at insert time (`pages.current_version_id` starts
`NULL`, set after the first version row exists).

```sql
-- ============================================================
-- versioning
-- ============================================================
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY CHECK (version > 0)
);

-- ============================================================
-- config / curated tables (survive in shape, FK-independent first)
-- ============================================================
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE search_engines (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT,
    url   TEXT UNIQUE NOT NULL
);

CREATE TABLE watchlist (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT    UNIQUE NOT NULL
);

-- graph_filters: explicitly OUT OF SCOPE for this reset (schema-reset.md).
-- Unchanged term-based hide list; the label-system work owns its future.
CREATE TABLE graph_filters (
    term TEXT PRIMARY KEY
);

CREATE TABLE domains (
    host      TEXT PRIMARY KEY,
    alias     TEXT,
    last_seen TEXT
);

-- bookmarks
CREATE TABLE seeds (
    url      TEXT PRIMARY KEY,
    label    TEXT,
    added_at TEXT
);

CREATE TABLE collections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT
);

-- ============================================================
-- core lifecycle: resource / page / version split
-- ============================================================
CREATE TABLE resources (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    url               TEXT    UNIQUE NOT NULL,
    host              TEXT    NOT NULL,
    state             TEXT    NOT NULL CHECK (state IN
                          ('unknown','known','crawled','dead')),
    first_seen        TEXT    NOT NULL,
    last_seen         TEXT,
    last_state_change TEXT,
    FOREIGN KEY (host) REFERENCES domains(host) ON DELETE CASCADE
);

CREATE TABLE pages (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id        INTEGER NOT NULL UNIQUE
                         REFERENCES resources(id) ON DELETE CASCADE,
    current_version_id INTEGER REFERENCES page_versions(id),
    summary            TEXT,
    category           TEXT,
    reviewed           INTEGER NOT NULL DEFAULT 0,  -- D4 revised: boolean, not free-text review_state
    analysis_excluded  INTEGER NOT NULL DEFAULT 0,
    embed_excluded     INTEGER NOT NULL DEFAULT 0,
    opened_at          TEXT,
    created_at         TEXT
);

CREATE TABLE page_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id         INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    fetched_at      TEXT    NOT NULL,
    http_status     INTEGER,
    body_text       TEXT,   -- raw extracted text
    body_text_clean TEXT,   -- normalized text for FTS / embedding / diff
    body_hash       TEXT,   -- hash of body_text_clean for change detection
    title           TEXT,
    content_changed INTEGER -- 1 if body_hash differs from previous version
);

-- ============================================================
-- graph metadata
-- ============================================================
CREATE TABLE graph_nodes (
    resource_id INTEGER PRIMARY KEY REFERENCES resources(id) ON DELETE CASCADE,
    x           REAL,
    y           REAL,
    cluster     INTEGER,
    pagerank    REAL,
    betweenness REAL
);

-- ============================================================
-- headers — current page version only (per schema-reset.md)
-- ============================================================
CREATE TABLE response_headers (
    page_version_id INTEGER NOT NULL,
    key             TEXT    NOT NULL,
    value           TEXT,
    PRIMARY KEY (page_version_id, key),
    FOREIGN KEY (page_version_id) REFERENCES page_versions(id) ON DELETE CASCADE
);

-- ============================================================
-- edges — re-pointed to resources
-- ============================================================
CREATE TABLE edges (
    from_id     INTEGER NOT NULL,
    to_id       INTEGER NOT NULL,
    anchor_text TEXT,
    source      TEXT    NOT NULL CHECK (source IN ('crawl', 'analyst')),
    label       TEXT,
    PRIMARY KEY (from_id, to_id),
    FOREIGN KEY (from_id) REFERENCES resources(id) ON DELETE CASCADE,
    FOREIGN KEY (to_id)   REFERENCES resources(id) ON DELETE CASCADE
);

-- ============================================================
-- findings — absorbs entities + notes
-- ============================================================
CREATE TABLE findings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id     INTEGER REFERENCES resources(id) ON DELETE CASCADE,
    page_version_id INTEGER REFERENCES page_versions(id) ON DELETE SET NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('entity','note')),
    value           TEXT NOT NULL,
    metadata        TEXT,  -- JSON; entity type+source live here
    created_at      TEXT
);

-- ============================================================
-- collections membership — re-pointed to resources
-- ============================================================
CREATE TABLE collection_items (
    collection_id INTEGER NOT NULL,
    node_id       INTEGER NOT NULL,  -- references resources(id)
    PRIMARY KEY (collection_id, node_id),
    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
    FOREIGN KEY (node_id)       REFERENCES resources(id)   ON DELETE CASCADE
);

-- ============================================================
-- crawl execution detail (typed, linked from jobs) — status column DROPPED
-- ============================================================
CREATE TABLE crawls (
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
);

CREATE TABLE crawl_nodes (
    crawl_id INTEGER NOT NULL,
    node_id  INTEGER NOT NULL,  -- references resources(id)
    depth    INTEGER,
    PRIMARY KEY (crawl_id, node_id),
    FOREIGN KEY (crawl_id) REFERENCES crawls(id)     ON DELETE CASCADE,
    FOREIGN KEY (node_id)  REFERENCES resources(id)  ON DELETE CASCADE
);

-- ============================================================
-- recipe tables (spawn jobs when they fire)
-- ============================================================
CREATE TABLE crawl_schedules (
    url            TEXT PRIMARY KEY,
    label          TEXT,
    interval_hours REAL NOT NULL,
    mode           TEXT NOT NULL CHECK (mode IN
                     ('Cross-site','BFS','DFS','Diverse','Focused')),
    active         INTEGER NOT NULL DEFAULT 1,
    collection_id  INTEGER,
    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE SET NULL
);

-- last_status DROPPED (read latest from probes / jobs)
CREATE TABLE monitors (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    url                       TEXT    UNIQUE NOT NULL,
    label                     TEXT,
    interval_hours            REAL    NOT NULL,
    enabled                   INTEGER NOT NULL DEFAULT 1,
    alert_on_change           INTEGER NOT NULL DEFAULT 1,
    alert_on_restore          INTEGER NOT NULL DEFAULT 1,
    downtime_threshold_hours  REAL    NOT NULL DEFAULT 48
);

-- monitor history / uptime time series (typed). body_hash + content_changed
-- added in SCHEMA_VERSION 4 (Phase 5, Task 3): a content monitor hashes the
-- fetched clean text (same hash as page_versions) and flags drift vs the prior
-- probe. Uptime-only monitors leave both NULL.
CREATE TABLE probes (
    monitor_id      INTEGER NOT NULL,
    checked_at      TEXT    NOT NULL,
    status_code     INTEGER,
    body_hash       TEXT,
    content_changed INTEGER,
    PRIMARY KEY (monitor_id, checked_at),
    FOREIGN KEY (monitor_id) REFERENCES monitors(id) ON DELETE CASCADE
);

-- ============================================================
-- analyses (typed, retained) — status column DROPPED (see "Resolved
-- inconsistency"); target FK follows the resource split
-- ============================================================
CREATE TABLE analyses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id   INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    analysis_type TEXT    NOT NULL,
    model         TEXT,
    result        TEXT,
    question      TEXT,
    priority      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT,
    updated_at    TEXT
);

CREATE TABLE collection_analyses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    analysis_type TEXT    NOT NULL,
    model         TEXT,
    result        TEXT,
    created_at    TEXT,
    updated_at    TEXT
);

-- ============================================================
-- flags (typed, retained) — own workflow vocabulary, node_id → resources
-- ============================================================
CREATE TABLE flags (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id  INTEGER NOT NULL,  -- references resources(id)
    status   TEXT    NOT NULL CHECK (status IN
                ('pending','flagged','investigating','done','dismissed')),
    source   TEXT    NOT NULL DEFAULT 'analyst' CHECK (source IN
                ('watchlist','analyst')),
    priority INTEGER NOT NULL CHECK (priority IN (1,2,3)),
    note     TEXT,
    FOREIGN KEY (node_id) REFERENCES resources(id) ON DELETE CASCADE
);

-- ============================================================
-- unified work-tracking
-- ============================================================
CREATE TABLE jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT    NOT NULL CHECK (kind IN
                  ('crawl','schedule','analysis','probe','live-crawl','batch')),
    target_type TEXT    NOT NULL CHECK (target_type IN
                  ('url','domain','collection','cluster')),
    target_id   INTEGER NOT NULL,
    status      TEXT    NOT NULL CHECK (status IN
                  ('pending','running','done','failed','cancelled','paused')),
    payload     TEXT,   -- JSON, kind-specific config + back-references
    result      TEXT,   -- JSON, completion data
    error       TEXT,
    created_at  TEXT,
    started_at  TEXT,
    finished_at TEXT
);
```

### Indexes

```sql
CREATE INDEX idx_resources_host        ON resources(host);
CREATE INDEX idx_resources_state       ON resources(state);
CREATE INDEX idx_resources_last_seen   ON resources(last_seen);
CREATE INDEX page_versions_page_idx    ON page_versions(page_id, fetched_at DESC);
CREATE INDEX idx_graph_nodes_cluster   ON graph_nodes(cluster);
CREATE INDEX idx_response_headers_kv   ON response_headers(key, value);
CREATE INDEX idx_edges_from            ON edges(from_id);
CREATE INDEX idx_edges_to              ON edges(to_id);
CREATE INDEX idx_findings_resource     ON findings(resource_id);
CREATE INDEX idx_findings_kind         ON findings(kind);
CREATE INDEX idx_collection_items_node ON collection_items(node_id);
CREATE INDEX idx_crawl_nodes_node      ON crawl_nodes(node_id);
CREATE INDEX idx_probes_monitor        ON probes(monitor_id, checked_at);
CREATE INDEX idx_analyses_resource     ON analyses(resource_id);
CREATE INDEX idx_flags_status          ON flags(status);
CREATE INDEX idx_flags_node            ON flags(node_id);
CREATE INDEX jobs_status_idx           ON jobs(status);
CREATE INDEX jobs_kind_idx             ON jobs(kind);
```

### FTS5 + embeddings — current version only, no triggers

Both index the **current** page version's text, keyed per page
(`rowid = pages.id`). The old `nodes_fts` triggers are removed; maintenance
moves into the crawl write transaction (drop the stale row, insert the new
current text) because the indexed text now lives in `page_versions`, not in
the keyed table.

```sql
-- contentless: text is supplied on insert, source row lives in page_versions
CREATE VIRTUAL TABLE pages_fts USING fts5(
    body_text_clean,
    content=''
);

CREATE VIRTUAL TABLE embeddings USING vec0(
    page_id    INTEGER PRIMARY KEY,
    vector     FLOAT[384],   -- EMBED_DIM
    +model     TEXT,
    +created_at TEXT
);
```

Crawl-write maintenance (replaces the four `nodes_*` triggers), all inside
the same `CrawlDB.transaction()` that advances `pages.current_version_id`:

```
-- on a re-crawl where current_version_id advances:
INSERT INTO pages_fts(pages_fts, rowid, body_text_clean)
  VALUES('delete', :page_id, :old_clean);      -- drop stale current
INSERT INTO pages_fts(rowid, body_text_clean)
  VALUES(:page_id, :new_clean);                -- index new current
-- embeddings row for :page_id re-queued / re-written by the embed worker
```

---

## Column Mapping — current `nodes` → new homes

Every column on today's god-table `nodes` has an explicit destination. None
silently drops.

| `nodes` column      | New home                                  | Notes |
| ------------------- | ----------------------------------------- | ----- |
| `id`                | `resources.id` (+ `pages.resource_id`, `graph_nodes.resource_id`) | one URL → one resource |
| `url`               | `resources.url`                           | |
| `title`             | `page_versions.title`                     | now per-version |
| `domain`            | `resources.host`                          | renamed `domain` → `host` |
| `depth`             | `crawl_nodes.depth`                        | already per-crawl; denormalized `nodes.depth` drops |
| `status_code`       | `page_versions.http_status`               | per-version; current via `current_version_id` |
| `category`          | `pages.category`                          | |
| `summary`           | `pages.summary`                           | |
| `body_text`         | `page_versions.body_text`                 | per-version |
| `body_text_clean`   | `page_versions.body_text_clean`           | per-version; FTS/embed source |
| `response_headers`  | `response_headers` table → `page_version_id` | legacy JSON column gone; normalized table re-pointed |
| `first_seen`        | `resources.first_seen`                    | |
| `last_seen`         | `resources.last_seen`                     | |
| `reviewed` (0/1)    | `pages.reviewed` (0/1)                    | see decision D4 (revised) |
| `analysis_excluded` | `pages.analysis_excluded`                 | carried forward (decision D2) |
| `opened_at`         | `pages.opened_at`                         | carried forward (decision D2) |
| `stub` (0/1)        | **removed** → `resources.state`           | `stub=1` → `known`; `stub=0` → `crawled` |
| `embed_excluded`    | `pages.embed_excluded`                    | |

---

## Table-by-table delta vs current schema

**New tables:** `resources`, `pages`, `graph_nodes`, `findings`, `jobs`.
(`page_versions` exists today but is redesigned — see below.)

**Dropped tables:**
- `nodes` — split into `resources` / `pages` / `page_versions` / `graph_nodes`.
- `crawl_queue` — folds into `jobs` (`kind='crawl'`, `status='pending'`);
  per-row config moves to `jobs.payload`.
- `entities` — folds into `findings` (`kind='entity'`; type + source preserved
  in `findings.metadata` JSON; the CHECK enum becomes write-path validation).
- `notes` — folds into `findings` (`kind='note'`; body in `findings.value`).

**Redesigned:**
- `page_versions` — FK re-pointed `nodes(id)` → `pages(id)`; composite PK
  `(node_id, crawled_at)` swapped for surrogate `id`; content columns added
  (`body_text`, `body_text_clean`, `body_hash`, `title`, `content_changed`);
  `crawled_at` → `fetched_at`, `status_code` → `http_status`.

**Re-pointed FK / dropped column (shape otherwise intact):**
- `edges.from_id` / `to_id` → `resources(id)`.
- `response_headers` → keyed by `page_version_id` (current version only).
- `collection_items.node_id` → `resources(id)`.
- `crawls` — **drops `status`** (read from linked `jobs` row); else intact.
- `crawl_nodes.node_id` → `resources(id)`.
- `monitors` — **drops `last_status`** (read latest from `probes` / `jobs`).
- `analyses` — `node_id` → `resource_id` (`resources(id)`); **drops `status`**
  (see "Resolved inconsistency").
- `collection_analyses` — **drops `status`** (same).
- `flags.node_id` → `resources(id)`; workflow vocabulary unchanged.

**Unchanged in shape:** `schema_version` (seeded at 3), `settings`,
`search_engines`, `watchlist`, `graph_filters`, `domains`, `seeds`,
`collections`, `crawl_schedules`, `probes`.

---

## State Vocabularies

**`resources.state`** (canonical URL/page lifecycle):
```
unknown  -- referenced but never fetched, never tried
known    -- recorded with metadata (e.g. from search), not yet crawled
crawled  -- successfully fetched at least once (page exists)
dead     -- repeatedly failed; terminal (auto after N failures, or manual)
```

**`jobs.status`** (unified work vocabulary, every kind):
```
pending | running | done | failed | cancelled | paused
```

**`flags.status`** keeps its **own** analyst-workflow vocabulary — it is
*not* merged into the job vocabulary (`pending`/`flagged`/`investigating`/
`done`/`dismissed`).

---

## Fill-in decisions (made while consolidating — for review)

These are internal shape choices not spelled out in the source specs.
Defaults chosen for correctness/consistency; flag any to revisit.

- **D1 — `AUTOINCREMENT` on all surrogate PKs.** `resources`, `pages`,
  `page_versions`, `findings`, `jobs` use `INTEGER PRIMARY KEY AUTOINCREMENT`
  (spec DDL wrote plain `INTEGER PRIMARY KEY`). Reason: `resources.id` is
  referenced by `edges`, `collection_items`, `crawl_nodes`, `graph_nodes`,
  `analyses`, `flags`, `findings`, and by persisted workspace/tab state;
  rowid reuse after a delete could silently rebind a stale reference.
  Matches the current `nodes` convention.
- **D2 — carry `analysis_excluded` + `opened_at` onto `pages`.** Both are
  live page-level columns on today's `nodes` (LLM-exclusion toggle;
  last-opened UI state) that the spec's `pages` DDL omitted. Kept rather than
  dropped.
- **D3 — CHECK constraints on `jobs`.** `kind`, `target_type`, `status` get
  CHECK enums, matching the house style ("bad statuses never reach disk").
  `kind` uses the fuller `unified-activity-view.md` set
  (`crawl/schedule/analysis/probe/live-crawl/batch`).
- **D4 — REVISED (owner-confirmed 2026-06-04): keep `pages.reviewed`
  boolean, do not introduce a free-text `review_state`.** The original D4
  proposed an un-CHECKed free-text `review_state` "for now," tightened later by
  item 7. Owner rejected the deferral: an un-validated column with no consuming
  workflow has neither an integrity guard nor a feature. Resolution: the reset
  keeps today's `reviewed` (`INTEGER NOT NULL DEFAULT 0`), preserving exact
  current behavior. The typed, `CHECK`-constrained `review_state` machine is
  built **whole by item 7** (`analysis-intel-pane.md`) as an additive migration
  when it designs the review workflow — states and their driving UI together.
  No half-built column ships here. See the package `decisions.md`.
- **D5 — `response_headers` keyed by `page_version_id`, current-version
  rows only.** On a version advance the prior version's header rows are
  deleted in the crawl txn (CASCADE also covers version deletion). Honors
  "only the current fetch's headers are retained for clustering."
- **D6 — `findings` indexed on `resource_id` and `kind`** (mirrors the
  old `idx_entities_node` / `idx_notes_node`, plus kind filtering).

---

## Resolved inconsistency between source specs

**`analyses` / `collection_analyses` `status` column — drop vs keep.**

- `schema-reset.md` ("Analyses — typed tables retained") says they *"get the
  new state vocabulary on their `status` column"* — implies **keep**.
- `unified-activity-view.md` ("What Gets Deleted") lists *"Source-specific
  status columns in `crawls`, `crawl_queue`, `analyses`,
  `collection_analyses`, `monitors`"* — implies **drop**.

**Resolution taken here: DROP**, status read from the linked `jobs` row.
Rationale: this is exactly how `schema-reset.md` resolved the same tension
for `crawls` (*"loses its own `status` column ... so the two never
drift"*). Applying the identical rule to `analyses`/`collection_analyses`
keeps one source of truth for work state and matches the deletion list.
The "typed tables retained" point still holds — the *tables* are retained
(not collapsed into a polymorphic `analyses`); only the redundant `status`
*column* goes.

**Owner CONFIRMED 2026-06-04: DROP.** Status is read from the linked `jobs`
row. If analyses ever need a result-level state distinct from job state, it
returns as a differently-named column — never as `status` — to avoid
re-introducing the drift `crawls` was fixed to prevent. See the package
`decisions.md`.

---

## `core.py` changes beyond DDL

- **Bump `SCHEMA_VERSION` to 3.** New schema seeded fresh; no upgrade path.
- **Delete the v1/v2 migration + backfill helpers** — they migrate the old
  schema and have no meaning after a DB-delete cutover:
  `_migrate_flags_table`, `_migrate_to_v2`, `_backfill_response_headers`.
- **Collapse the two boot sweeps into one `jobs` sweep.** `_sweep_stale_crawls`
  (keyed on `crawls.status`) and `_sweep_stale_queue_rows` (keyed on
  `crawl_queue`) both vanish with those status columns/tables; replace with a
  single pass that fails out `jobs` left `running`/`pending`-claimed from a
  prior process (`UPDATE jobs SET status='failed', error='process restarted'
  WHERE status='running'`). Live-crawl/queue recovery now derives from `jobs`.
- **`DEFAULT_SETTINGS`** — `crawl.queue_paused` stays meaningful (now gates
  dispatch of `jobs` with `kind='crawl' AND status='pending'`). New Retention
  settings (dead-state failure threshold, version-retention policy) are added
  by `settings-modal.md` / `analysis-intel-pane.md`, not here.

---

## Affected db/ module reshape (from schema-reset.md, confirmed against tree)

- `db/nodes.py` → split into `resources.py`, `pages.py`, `page_versions.py`,
  `graph_nodes.py`.
- New: `db/findings.py`, `db/jobs.py`.
- Removed: `db/crawl_queue.py` (folds into `jobs`), `db/entities.py` and
  `db/notes.py` (fold into `findings`).
- Re-pointed/edited: `db/edges.py`, `db/collections.py`, `db/crawl.py`
  (`crawls` loses `status`; `crawl_nodes`/`crawl_schedules` FK re-points),
  `db/monitors.py` (drops `last_status`), `db/analyses.py` +
  `db/collection_analyses.py` (drop `status`, target FK), `db/flags.py`
  (FK re-point), `db/fingerprints.py` (reads current-version headers),
  `db/embed.py` (keyed per page), `db/core.py` (schema + FTS/vec + sweeps).

---

## Open decisions inherited from `schema-reset.md` (not resolved here)

These remain owned by the milestone / downstream specs, listed so the
schema review is complete:

- Job retention policy and whether the table reads better as `jobs` vs
  `activity` (`unified-activity-view.md` deferred decisions).
- Dead-state auto-threshold default (5 failures / 7 days) — surfaced in the
  Retention tab (`settings-modal.md`).
- No `page_diffs` cache table — diffs computed on demand.
- `findings.page_version_id` nullable semantics (NULL = resource-general;
  set = came from that crawl's content) — already specced.
