# Schema Reset Milestone

## Status

Implementation-ready breaking schema cutover. Accepts **DB delete** as the
migration strategy — no in-place migration, no adapter layer maintaining both
old and new schemas. One sharp transition.

This is the largest single package in the cleanup sequence. Bundles three
schema-touching cleanups that ship together because they redesign overlapping
tables and any partial cutover wastes the disruption budget.

## Bundled Items

1. **State vocabulary consolidation** — one canonical state machine for URL /
   page lifecycle. Replaces `nodes.stub`, `crawl_queue.lookup_state`, and the
   analysis `waiting` derivation.
2. **Resource / page data model split** — break `nodes` into `resources`,
   `pages`, `graph_nodes`, `page_versions`, `findings`. Unlocks page
   versioning.
3. **Unified jobs table + Activity tab UI** — single `jobs` table replacing
   per-source status/history columns, plus the new bottom-pane
   `ActivityTab.svelte` that consumes `GET /api/jobs`. Specced in full in
   `unified-activity-view.md`; this milestone delivers both the table and
   the consuming UI in one cutover (no separate frontend-only adapter
   phase). `crawl_queue` is dropped (folds entirely into `jobs`); `crawls`
   and `crawl_nodes` survive as typed per-run execution detail linked to
   their `jobs` row; `crawl_schedules` and `monitors` survive as typed
   **recipe** tables that spawn jobs when they fire — see "Source-Table
   Linkages" below.

## Explicitly Out of Scope

- **`graph_filters`** — stays exactly as it is today (term-based hide list,
  graph-specific). The extend-or-replace decision for label-based filtering
  belongs to the label-system work (item 11, now archived at
  [`../2026-06-10-label-system/`](../2026-06-10-label-system/)), which owns the "Avoid
  these sites" workflow and will decide whether to extend `graph_filters`
  rows or introduce a parallel mechanism.
- **Polymorphic analyses table** — `analyses` and `collection_analyses` stay
  as separate typed tables. The earlier proposal to collapse them into a
  single `analyses(target_type, target_id, …)` table was shape-cleanliness
  with no user-facing payoff; typed tables keep FK cascades intact and add
  no friction to the Intel pane work in `analysis-intel-pane.md` (item 7).
  If Cluster Q&A is built later it gets a third typed table
  (`cluster_analyses`), not a polymorphic merger.
- **Typed settings table** — settled in `additions/settings-modal.md`
  (item 8): no new table. Settings stay in the existing `settings`
  key/value table with a typed
  Pydantic / Zod validation layer on top.
- **Prompt templates and auto-analysis rules tables** — owned by
  `../2026-06-05-analysis-intel-pane/source-spec.md` (item 7) as an additive
  non-destructive migration on top of the post-reset schema. Not
  bundled here because they're scoped to item 7 and would inflate this
  cutover.

## Goal

Replace the current "god table" `nodes` schema with a properly normalized
design that:

- Separates URL registry from crawled content from graph metadata.
- Supports multi-snapshot page versioning (crawl the same URL twice, keep
  both versions, diff them).
- Uses one state vocabulary across the whole data model.
- Stores work/activity in one table with one status vocabulary.

The current schema fails on all four counts. The mismatch radiates outward —
every status check, every analysis route, every "is this a stub?" question
multiplies the duplication.

## New Schema

### Core lifecycle tables

```sql
CREATE TABLE resources (
    id          INTEGER PRIMARY KEY,
    url         TEXT    UNIQUE NOT NULL,
    host        TEXT    NOT NULL,
    state       TEXT    NOT NULL CHECK (state IN
                  ('unknown','known','crawled','dead')),
    first_seen  TEXT    NOT NULL,
    last_seen   TEXT,
    last_state_change TEXT,
    FOREIGN KEY (host) REFERENCES domains(host) ON DELETE CASCADE
);

CREATE TABLE pages (
    id              INTEGER PRIMARY KEY,
    resource_id     INTEGER NOT NULL UNIQUE REFERENCES resources(id) ON DELETE CASCADE,
    current_version_id INTEGER REFERENCES page_versions(id),
    summary         TEXT,
    category        TEXT,
    review_state    TEXT,
    embed_excluded  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT
);

CREATE TABLE page_versions (
    id          INTEGER PRIMARY KEY,
    page_id     INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    fetched_at  TEXT    NOT NULL,
    http_status INTEGER,
    body_text       TEXT,   -- raw extracted text
    body_text_clean TEXT,   -- normalized text used for FTS / embedding / diff
    body_hash       TEXT,   -- hash of body_text_clean for fast change detection
    title           TEXT,
    content_changed INTEGER -- 1 if body_hash differs from previous version
);

-- Note: no body_html column. Page versioning stores text only. The HTML
-- bytes are not retained beyond the in-flight crawl — see "Body storage"
-- below.

CREATE INDEX page_versions_page_idx ON page_versions(page_id, fetched_at DESC);
```

`page_versions` is **not a new table** — a minimal one exists today
(`node_id`, `crawled_at`, `status_code`), is written on every crawl in
`db/nodes.py`, and already powers the right-pane crawl-history list. The
reset redesigns it: re-point the FK from `nodes(id)` to `pages(id)`, swap the
composite PK for a surrogate `id`, and add the content columns
(`body_text`, `body_text_clean`, `body_hash`, `title`, `content_changed`).
The *content* versioning and diff are the new capability; the timestamp/
status timeline already ships.

### Graph metadata

```sql
CREATE TABLE graph_nodes (
    resource_id INTEGER PRIMARY KEY REFERENCES resources(id) ON DELETE CASCADE,
    x           REAL,
    y           REAL,
    cluster     INTEGER,
    pagerank    REAL,
    betweenness REAL
    -- other render/layout metadata
);
```

Edges continue to point at `resources(id)` (formerly `nodes(id)`).

### Findings (entities, notes)

```sql
CREATE TABLE findings (
    id          INTEGER PRIMARY KEY,
    resource_id INTEGER REFERENCES resources(id) ON DELETE CASCADE,
    page_version_id INTEGER REFERENCES page_versions(id) ON DELETE SET NULL,
    kind        TEXT NOT NULL,        -- entity, note
    value       TEXT NOT NULL,
    metadata    TEXT,                 -- JSON
    created_at  TEXT
);
```

Findings can attach to a resource (URL-level) or a specific page version
(content-level). When a finding refers to specific content (an entity
extracted from a particular crawl), it points at the version it came from.

`findings` holds only the lightweight, mostly-static items: extracted
entities and analyst notes. It does **not** store:

- **Flags** — flags stay a **typed table of their own**, not folded into
  `findings`. A flag is a managed workflow object: a lifecycle `status`
  (`pending` / `flagged` / `investigating` / `done` / `dismissed`), a
  `priority` (1–3), a `source` (`watchlist` auto-flagger vs `analyst`), and a
  note. The Flags bottom-pane tab filters by status and sorts by priority,
  which wants real indexed columns and CHECK constraints, not JSON in
  `metadata`. This mirrors the typed-table reasoning used for `analyses` and
  `crawls`. The `flags` table is kept; its `node_id` FK re-points to
  `resources(id)` and its `status` keeps its own vocabulary (it is **not**
  merged into the unified job-status vocabulary — flag status is an analyst
  workflow, not a work-queue state).
- **Labels** — an analyst-managed taxonomy with a registry table (`labels`)
  and typed N:M join tables (`resource_labels`, `domain_labels`), specced in
  the label-system work. Labels need referential integrity and a
  preset palette that `findings` can't express cleanly.

### Analyses — typed tables retained

`analyses` (page/resource-targeted) and `collection_analyses` (collection-
targeted) stay as separate typed tables. They get the new state vocabulary
on their `status` column, and their target FKs follow the resource/page
split (`analyses.resource_id` references `resources(id)`), but they are not
collapsed into one polymorphic table.

If Cluster Q&A is later wired through `analysis-intel-pane.md`, it gets a
typed `cluster_analyses` table — not a row in a polymorphic `analyses`.

### Unified jobs

```sql
CREATE TABLE jobs (
    id          INTEGER PRIMARY KEY,
    kind        TEXT    NOT NULL,        -- crawl, schedule, analysis, probe
    target_type TEXT    NOT NULL,
    target_id   INTEGER NOT NULL,
    status      TEXT    NOT NULL,
    payload     TEXT,                    -- JSON
    result      TEXT,                    -- JSON
    error       TEXT,
    created_at  TEXT,
    started_at  TEXT,
    finished_at TEXT
);

CREATE INDEX jobs_status_idx ON jobs(status);
CREATE INDEX jobs_kind_idx ON jobs(kind);
```

## Source-Table Linkages

The `jobs` table is the unified **work-tracking** layer. It does not absorb
every table that touches work — only the queue. Surviving source tables are
dropped outright, kept as typed **recipes** that spawn jobs when they fire,
or kept as typed **execution detail** that a job links to.

### What is dropped

- **`crawl_queue`** — drops entirely. Today it is essentially "pending
  crawl work"; in the new model that role is held by `jobs` rows with
  `kind = 'crawl'` and `status = 'pending'`. The queue-specific config
  (priority, depth, max_pages, etc.) moves into `jobs.payload`.

### What survives as a recipe

- **`crawl_schedules`** — typed recipe table. Holds the cron expression /
  next-run / crawl template that the analyst edits. When the scheduler
  fires the recipe, it writes a `jobs` row with `kind = 'crawl'` and
  `payload.crawl_schedule_id = N` linking back to the recipe.
- **`monitors`** — typed recipe table. Holds the watch definition
  (target, check interval, alert thresholds). When the monitor daemon
  fires a check, it writes a `jobs` row with `kind = 'probe'` and
  `payload.monitor_id = N`.

Recipes are not jobs. They show up in their own bottom-pane tabs
(Scheduled Crawls, Monitors), each mirroring the same recipe-list pattern
with edit / pause / resume / delete row actions. Their *firings* show up
in Activity. The bottom-pane Monitors tab is added by
`pane-responsibility-reset.md`; the existing `AddMonitorModal` stays as
the create flow, reachable from both the tab toolbar (global) and the
right-pane DomainTab (contextual to one domain).

### What survives as typed execution detail

- **`crawls`** — survives as the per-run execution-detail table, the same
  way `analyses` survives (see `unified-activity-view.md`): the `jobs` row
  (`kind = 'crawl'`) owns the work-tracking status/lifecycle, and the
  `crawls` row owns the rich per-run detail — `mode`, `max_depth`,
  `seed_url`, the page counters (`pages_crawled` / `pages_failed` /
  `pages_queued` / `pages_skipped`), and run timing. The `jobs` row links to
  it via `payload.crawl_id = N`. **`crawls` loses its own `status` column** —
  status is read from the linked `jobs` row, so the two never drift.
  (`unified-activity-view.md`'s "What Gets Deleted" already assumes this.)
- **`crawl_nodes`** — survives unchanged in shape, with its `node_id`
  foreign key re-pointed from `nodes(id)` to `resources(id)`. It still
  answers "which resources did this run touch, at what depth," which a JSON
  blob in `jobs.result` could not express queryably.
- **`probes`** — survives as the typed monitor-history (uptime) time series,
  same pattern: a monitor firing writes a `kind = 'probe'` `jobs` row for the
  Activity view, and the durable check result lands in `probes`
  (`checked_at`, `status_code`, plus a content-change result once monitors
  compare page-version hashes). Keeping `probes` typed keeps the uptime
  history lean and directly queryable, and lets job-retention prune the
  `kind = 'probe'` activity rows aggressively without touching uptime
  history.

This is the same typed-table + `jobs`-status pattern the milestone uses for
`analyses` and `collection_analyses`: a crawl run has durable identity
(counters, the resources it found, a place in crawl history), so its detail
stays in a typed table rather than collapsing into `jobs`. The rejected
alternative — folding `crawls` wholesale into `jobs` with counters in
`result` JSON — would make per-run counters unqueryable and contradict the
analyses pattern, for no real schema saving (`crawl_queue` already linked
1:1 to `crawls`, so only one table actually disappears either way).

### Lifecycle rules

- **Creating a recipe** — writes a `crawl_schedules` / `monitors` row.
  No `jobs` row yet.
- **Firing a recipe** — worker inserts a fresh `jobs` row with the
  back-reference in `payload`. Multiple firings of the same recipe produce
  multiple job rows over time (this is the activity history).
- **Cancelling a job** — only mutates the `jobs` row (`status = cancelled`).
  The recipe is untouched and will fire again on schedule.
- **Deleting a recipe** — in-flight jobs spawned by it (`status` in
  `pending` / `running` / `paused`) are cancelled. Terminal jobs (`done`,
  `failed`, `cancelled`) survive as history — their
  `payload.crawl_schedule_id` / `payload.monitor_id` now points at a
  missing row, which is acceptable for a log.
- **Job retention purge** — purging completed `jobs` rows never affects
  recipes.

### Why this asymmetry

Crawl queue entries have no identity beyond "work waiting to happen" — once
the work completes there is nothing left to refer to, so folding them into
`jobs` is lossless. Schedules and monitors have **durable identity** — the
analyst edits them, names them, sees them in lists, and expects them to
persist independently of any individual firing. That identity argues for
typed tables.

## Search, Embeddings, and Auxiliary Tables

These tables hang off `nodes` today and must re-point at the new schema. The
governing decision: search and embeddings cover **only each page's current
version**, never its full snapshot history.

### Full-text search + embeddings — current version only

- The FTS5 contentless index (`nodes_fts` today) and its maintenance move off
  `nodes` and onto current-version text, keyed per page (`content_rowid` =
  `pages(id)`). A page is re-indexed whenever its `current_version_id`
  advances — drop the prior FTS row, insert the new current text — handled in
  the crawl write transaction rather than the old `nodes` table-level
  triggers. Net effect: one searchable row per crawled page, as today.
- The `embeddings` vector table keys per page (one current-content embedding
  per crawled page), re-embedded when the current version changes. It is
  **not** keyed per `page_versions` row.

Rationale: search reflects live content; the index stays lean while
`page_versions` grows; results show one hit per page with no
dedup-by-version UI burden. Cross-version search, if ever wanted, is an
additive opt-in (a second index over `page_versions`) and is explicitly out
of scope here. Old snapshots remain reachable through the page-history
timeline and diff view, not through search.

### response_headers — current version only

`response_headers` re-points from `nodes(id)` to the current page version
(headers are captured per fetch). Fingerprint clustering reads the
current-version headers. Per-version header history is out of scope; only the
current fetch's headers are retained for clustering.

### entities — fold into findings, keep the type

The `entities` table folds into `findings` (`kind = 'entity'`). The entity
**type** (`email` / `btc` / `xmr` / `pgp` / `onion` / `handle` / `blob`) and
**source** (`crawl` / `llm`) are preserved in `findings.metadata` (JSON) so
entity-type filtering and provenance survive the merge. The typed CHECK
constraint `entities` enforces today becomes validation in the findings write
path rather than a column constraint.

## Body Storage — Text Only

`page_versions` stores text (`body_text` + `body_text_clean`), not HTML.
Reasons:

- **Privacy / threat model** — markup carries third-party asset URLs,
  beacon references, and embed paths the analyst doesn't need on disk.
  The DB is unencrypted today; less retained = less exposure if the
  device is imaged.
- **Storage discipline** — onion sites can be HTML-heavy. Storing HTML
  across every re-crawl multiplies disk use 5–20× over text-only, which
  forces an aggressive retention policy from day one.
- **Smallest code path** — no HTML sanitizer, no renderer for the diff
  view, no partial-retention rules. Diffs become text diffs handled by
  the existing tooling.

If a future workflow needs full-fidelity capture for specific resources,
a `pages.full_capture` opt-in plus a separate `page_version_html(version_id,
body_html)` side table is the additive upgrade — does not change anything
in the text-only path.

## Page Versioning — Key Feature Unlock

The biggest user-visible payoff of the reset. Each crawl of a URL writes a
new `page_versions` row instead of overwriting the previous one. Enables:

- **Snapshot diff view** — crawl a domain at T1 and T2, see what changed.
  Pages added, pages removed, pages whose content drifted, pages identical.
- **Page history timeline** — every version of a single URL over time.
- **Evidence preservation** — vendor pulls a listing, the snapshot remains.
- **First-seen / last-alive** — answer "when did this URL first appear / die"
  with a single query.
- **Richer monitors** — `probes` can compare the latest `page_versions` hash
  to the previous one and surface meaningful content change, not just
  HTTP status.

## State Vocabulary

Single canonical state machine on `resources`:

```
unknown    -- URL referenced but never fetched, never tried
known      -- URL recorded with metadata (e.g. from search), not yet crawled
crawled    -- successfully fetched at least once (page exists)
dead       -- repeatedly failed fetches; treat as terminal
```

Removes:

- `nodes.stub`
- `crawl_queue.lookup_state`
- analysis's separate `waiting` derivation
- per-callsite stub-vs-crawled special cases throughout frontend + backend

Frontend label mapping:

- `unknown` → "Unknown"
- `known` → "Known (uncrawled)"
- `crawled` → "Crawled"
- `dead` → "Dead"

## Migration Approach — DB Delete

No in-place migration, no export/import path. The cutover is:

1. Stop services.
2. Delete the existing project DB file.
3. Apply the new schema fresh.
4. Restart services. Empty state. Start crawling.

**What this wipes** — everything. Not just the resources/pages/findings/graph
tables that are being redesigned, but also the curated-config tables that
survive in the new schema's *shape*: `domains` (including aliases),
`search_engines`, `watchlist`, `crawl_schedules`, `monitors`, `collections`,
`seeds` (bookmarks), `analyses`, `collection_analyses`, and the `settings`
key/value table (settings, API keys, Tor / Ollama config). The cutover is
total.

Reasons:

- Adapter code maintaining both schemas would offset most of the LOC savings
  the reset is meant to deliver.
- The current DB is development data, not production data with users
  depending on its persistence.
- Owner has explicitly accepted DB delete — including loss of curated config
  — as the migration strategy.

If a future schema change ever lands against a long-running real-data DB,
that's a separate one-off migration script written against the known new
schema — not a generic dual-schema adapter.

**No pre-wipe export step.** Owner has explicitly declined an
export-curated-config helper before the cutover. The DB is treated as
disposable; analyst-curated config (watchlist, search engines,
scheduled crawls, monitors, aliases, collections, bookmarks) goes with
it. Do not re-introduce an export step in this milestone — if a
Save/Load profile feature is ever wanted it is a Settings-modal feature
in its own right, not a migration concession.

## Affected Surfaces

Verified upper bound from the original proposal: **112 backend/frontend files,
1,128 matches** for related node/page/stub/search/analyses terms. Realistic
expectation: most of those are shallow edits (rename a field access, update a
status check) rather than rewrites.

Backend:

- `backend/backend/db/core.py` — schema definitions
- `backend/backend/db/nodes.py` → split into `resources.py`, `pages.py`,
  `page_versions.py`, `graph_nodes.py`
- `backend/backend/db/findings.py` — new
- `backend/backend/db/analyses.py` — kept; target FK migrates to
  `resources(id)` and `status` adopts the unified vocabulary
- `backend/backend/db/collection_analyses.py` — kept; `status` adopts the
  unified vocabulary
- `backend/backend/db/collections.py` — kept; `collection_items.node_id` FK
  re-points to `resources(id)` (a collection groups resources/URLs)
- `backend/backend/db/jobs.py` — new
- `backend/backend/db/crawl_queue.py` — removed (folded into `jobs`)
- `backend/backend/db/crawl.py` — owns `crawls`, `crawl_nodes`, `seeds`
  (bookmarks), and `crawl_schedules` (the recurring-crawl recipe table; there
  is no dedicated `scheduled_crawls.py`). In the reset: `crawls` drops its
  `status` column (read from the linked `jobs` row) and keeps its per-run
  detail; `crawl_nodes` keeps its shape with `node_id` re-pointed to
  `resources(id)`; `crawl_schedules` stays as the recipe table and joins
  `jobs` for firing history.
- `backend/backend/db/monitors.py` — kept as recipe table; status columns
  removed, replaced by joining to `jobs`
- `backend/backend/db/entities.py` — folded into `findings.py`; entity
  type + source preserved in `findings.metadata`
- `backend/backend/db/notes.py` — folded into `findings.py` (`kind = 'note'`,
  body in `value`)
- `backend/backend/db/flags.py` — **kept** as its own typed table; `node_id`
  FK re-points to `resources(id)`; status/priority/source columns and indexes
  retained, status keeps its own workflow vocabulary
- `backend/backend/db/fingerprints.py` — reads current-version
  `response_headers` instead of `nodes`-keyed headers
- FTS5 (`nodes_fts`) + `embeddings` in `core.py` — re-pointed at
  current-version text, keyed per page; index maintenance moves from
  `nodes` triggers into the crawl write transaction
- `backend/backend/db/embed.py` — embedding persistence keyed per page
- All routes returning node payloads
- Crawl runner, LLM worker, monitor daemon

Frontend:

- `frontend/src/lib/api/*.ts` — response shapes for nodes/pages/resources
- `frontend/src/lib/stores/graph.svelte.ts` — graph payload shape
- Every component reading `node.body_text_clean`, `node.stub`,
  `node.summary`, etc.

## Code Size Expectation

Honest forecast: **net LOC stays flat or grows slightly.** Splitting one
table into five means more joins, more endpoint shapes, more insert paths.
The deletions (status shims, dedup analyses, stub-vs-crawled special cases,
per-source history endpoints) recover much of that, but not all.

This is a **shape win, not a size win.** Frame it as architectural
correctness and feature unlock (page versioning), not code reduction.

## User-Visible Changes

Most are subtle:

- "Stub" disappears from UI labels — replaced by "Known (uncrawled)".
- Consistent state labels across graph / collections / search / right pane.
- "Dead" becomes a first-class state — dead-link filter possible.
- Search results clearly represent crawled pages, not URL placeholders.

Major:

- **Page versioning** — re-crawl a URL → keep both snapshots → diff them.
- **Snapshot diff view** for domain over time.
- **Page history timeline** in the right pane Page tab.
- **Monitor content-change alerts** become meaningful (hash compare across
  versions).

## Implementation Order Within the Reset

Inside this package, sequence the changes to minimize broken intermediate
states. The concrete, checkbox-level task breakdown of these phases lives in
[`schema-reset-checklist.md`](schema-reset-checklist.md) (seeds the active
package's `checklist.md` on promotion):

1. Design the full new schema as one artifact. Review before any code.
   — done: see [`schema-reset-ddl.md`](schema-reset-ddl.md) (consolidated
   CREATE script, column mapping, fill-in decisions, and the resolved
   `analyses.status` spec inconsistency). Pending owner review.
2. Drop dev DB. Stand up the new schema. Get the app booting (empty state).
3. Backend rewrite: routes return new shapes. Crawl runner writes the new
   tables. Analysis/jobs workers write the new tables.
4. Frontend rewrite: stores, API clients, components consume the new shapes.
5. Page versioning UI: diff view, timeline, version picker.
6. Delete the dead code (old status shims, old per-source endpoints, old node
   accessors).

Do not try to ship the new schema with the old frontend, or the new frontend
with the old schema. One coordinated cutover.

## Relationship to Other Work

- Requires `pane-responsibility-reset.md`, `shared-ui-primitives.md`,
  `graphcanvas-decomposition.md`, and `list-to-graph-tabs.md` already
  landed. The frontend should be stable, decomposed, and using its final
  workspace model before the data shape changes underneath it.
- Delivers the `jobs` table and Activity tab UI from
  `unified-activity-view.md` as part of this cutover.
- Delivers the unified status vocabulary and the typed-analyses target
  migration that `analysis-intel-pane.md` (item 7) builds on. Item 7 does
  not need polymorphic analyses — the typed tables it inherits are
  sufficient, and adding `cluster_analyses` is item 7's own work if
  Cluster Q&A is built.
- Unlocks page versioning, which is consumed by:
  - Right-pane Page tab (timeline + version picker).
  - Right-pane Domain tab (snapshot comparison).
  - `settings-modal.md` Retention tab.
- Label system ([`../2026-06-10-label-system/`](../2026-06-10-label-system/)) — its `resource_labels` /
  `domain_labels` tables target `resources(id)` and `domains(host)` in the
  new schema, and `pages.alias` extends the post-reset `pages` table.
  Strictly additive on top of this milestone.

## Deferred Decisions

- Storage growth strategy. Re-crawling stores text again per version.
  Default retention policy (e.g. "keep last N versions per page" or "keep
  versions for M months") is a Retention setting in `settings-modal.md`.
_(decided 2026-05-27 — moved out of deferred:)_

- `pages.current_version_id` is a **cached pointer**, updated in the
  same `CrawlDB.transaction()` as the new `page_versions` insert.
  Single FK join keeps every list / right-pane read trivial. Frontend
  version-picker pins its own version id and is allowed to fall behind.
- **Dead-state transition is automatic** after a configurable failure
  threshold (default: 5 consecutive fetch failures over 7 days). Surfaced
  in the Retention tab in `settings-modal.md`. Analyst can also force a
  resource to `dead` from the right-pane action bar — automatic is the
  default path; manual is the override.
- **No `page_diffs` cache table.** Diffs compute on demand from the
  text bodies of two `page_versions` rows. Storage discipline; diffs
  are cheap to recompute and rarely viewed twice on the same pair.
  Revisit only if the diff view becomes a hot path.
- `findings.page_version_id` is **nullable**. NULL means "applies to
  the resource generally" (e.g. a user-applied flag); set means "this
  finding came from this specific crawl's content" (extracted entities).
