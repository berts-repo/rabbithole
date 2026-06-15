# Data Model

The authoritative schema lives in `backend/backend/db/core.py`. `CrawlDB`
creates the schema, indexes, FTS5 table, sqlite-vec virtual table, and default
settings whenever a project database is opened. `SCHEMA_VERSION` is `6` (the
schema-reset cutover bumped 2 → 3; 4 added a probe content hash; 5 added the
analysis-intel tables additively — see _Analysis And Search Tables_; 6 added the
label-system tables + `pages.alias` additively — see _Label Tables_).

## Project Database

Each project uses one SQLite database file. The backend has one active project
DB at a time. Project files are registered in the project registry and opened
through `ProjectState`.

`CrawlDB` configures:

- WAL mode
- foreign keys
- busy timeout
- `sqlite-vec`
- FTS5
- a reentrant transaction context manager

On open it runs a single boot sweep that marks any non-terminal `jobs` row
(`pending` / `running` / `paused`) left behind by a prior process exit as
`failed`, so work-tracking recovers cleanly.

## Resource / Page / Version Split

The schema reset replaced the single `nodes` table with a three-level split.
This is the core of the data model:

| Table | Purpose |
| --- | --- |
| `resources` | URL identity + lifecycle `state` (`unknown` / `known` / `crawled` / `dead`). One row per URL. `state` replaced the old `nodes.stub` boolean and `crawl_queue.lookup_state`. |
| `pages` | 1:1 with a resource (created lazily). Durable per-page analyst/LLM state that survives re-crawls: `summary`, `category`, `reviewed`, `analysis_excluded`, `embed_excluded`, `opened_at`, `alias` (v6 — analyst-chosen name for the *content*, mirroring `domains.alias`; the URL stays the immutable identity), and `current_version_id` (cached pointer to the latest version). |
| `page_versions` | One row per fetch: `fetched_at`, `http_status`, `body_text`, `body_text_clean`, `body_hash`, `title`, `content_changed`. Re-crawling a URL appends a new version and advances `pages.current_version_id` in the same transaction. |

A "node" id throughout the API is a **resource id**. "Uncrawled" means
`state != 'crawled'` (no current version yet); only `crawled` resources carry
real page content.

## Graph / Identity Tables

| Table | Purpose |
| --- | --- |
| `domains` | Per-host metadata and analyst alias. Every resource FKs to its `host`. |
| `graph_nodes` | Per-resource graph layout/metric cache (`x`, `y`, `cluster`, `pagerank`, `betweenness`). |
| `edges` | Resource-to-resource graph edges, `source` ∈ (`crawl`, `analyst`). |
| `response_headers` | Response headers for the **current page version** (`page_version_id` keyed); prior-version headers are pruned on re-crawl. Drives fingerprint clustering. |
| `findings` | Absorbs the old `entities` + `notes` tables. `kind` ∈ (`entity`, `note`); entity type + source live in `metadata` JSON. `page_version_id` NULL = applies to the resource generally; set = came from that crawl. |
| `seeds` | Saved seed URLs (bookmarks). |

## Crawl Tables

| Table | Purpose |
| --- | --- |
| `crawls` | Per-run **execution detail** only — seed, mode, collection, counters, timing, error. **No `status` column**: work-tracking status lives on the linked `jobs` row (`kind='crawl'`, `payload.crawl_id`). |
| `crawl_nodes` | Resources seen by a crawl, with crawl depth. |
| `crawl_schedules` | Recurring crawl definitions (spawn `kind='crawl'` jobs when they fire). |
| `watchlist` | Terms used by focused-crawl / watchlist matching. |

For scheduled crawls, the unified `jobs` table is the canonical record of "last
fired." Retiming reads schedule-sourced crawl jobs (`payload.source='schedule'`)
by `created_at` (when the schedule intended to fire), not `crawls.started_at`
(when a crawl actually began), which prevents a double-fire while dispatch is
paused or the kill switch holds.

## Unified Work Tracking — `jobs`

| Table | Purpose |
| --- | --- |
| `jobs` | One row per piece of background work across every source. Replaced the old `crawl_queue` table and the per-source status columns on `crawls` / `analyses` / `collection_analyses` / `monitors`. |

`kind` ∈ (`crawl`, `schedule`, `analysis`, `probe`, `live-crawl`, `batch`);
`target_type` ∈ (`url`, `domain`, `collection`, `cluster`); `status` ∈
(`pending`, `running`, `done`, `failed`, `cancelled`, `paused`). Kind-specific
config and back-references to typed detail tables live in `payload` (JSON);
completion data in `result` (JSON). Typed tables keep their durable detail and
read work-status from the linked job, so the two can never drift. The bottom-pane
**Activity** tab and `routes/jobs.py` are built on this table.

## Analyst Workflow Tables

| Table | Purpose |
| --- | --- |
| `collections` | Named analyst collections. Names unique case-insensitively (`COLLATE NOCASE`). |
| `collection_items` | Resource membership in collections. |
| `flags` | Resource flags with status, priority, and note. `status` is an analyst workflow vocabulary, **not** the unified job vocabulary. |
| `graph_filters` | Terms used to hide/filter graph data (out of scope for the reset). |
| `monitors` | Uptime monitor configuration. No `last_status` column — latest status reads from the most recent `probes` row. |
| `probes` | Monitor probe history + uptime series. `body_hash` + `content_changed` (v4) let a probe flag content drift, not just an HTTP status. Each probe also writes a paired `kind='probe'` job. |

## Analysis And Search Tables

| Table | Purpose |
| --- | --- |
| `analyses` | Per-resource LLM analysis **detail/results** (`resource_id`); status lives on a linked `kind='analysis'` job. Nullable `prompt_id` → the `prompt_templates` row used (NULL = ad-hoc free-form prompt). |
| `collection_analyses` | Collection-level LLM synthesis detail/results; status on a linked `kind='analysis'` job (`target_type='collection'`). Nullable `prompt_id` as above. |
| `cluster_analyses` | Cluster-level LLM synthesis detail/results (decision D1). Keyed by a membership **fingerprint** (sorted member `resource_id`s → SHA-256, 16 hex) — clusters drift across layout runs, so there is no stable cluster id. Stores a `resource_ids` JSON **membership snapshot** taken at compose time (the fingerprint is one-way, so the worker reads this list back to fetch each member's page body) plus a denormalized `label` snapshot. Status on a linked `kind='analysis'` job (`target_type='cluster'`, soft-referenced by `payload.cluster_analysis_id`). Nullable `prompt_id` as above. Re-running clustering re-attaches on a matching fingerprint; a changed membership orphans the old rows as queryable history. |
| `prompt_templates` | Project-local analyzer prompt presets (decision D3): `name`, `analysis_type`, `body`, `builtin`, `hidden`. Built-ins (`builtin=1`) are seeded idempotently and are hideable, not deletable. |
| `auto_analysis_rules` | Single typed home for auto-analysis (decision D4): `trigger_kind` ∈ (`crawl`, `collection_add`), optional `target_filter_json` (predicate placeholder for label-aware targeting), `analysis_type`, `model`, `enabled`, nullable `prompt_id`. Crawl-trigger rules are seeded once from the legacy `llm.auto_enqueue.*` settings; the rule's `enabled` flag is the runtime authority. |
| `search_engines` | Configured search-engine templates. |
| `settings` | Per-project settings. |
| `pages_fts` | FTS5 **contentless** index over the current page version's `body_text_clean`, keyed `rowid = pages.id`. |
| `embeddings` | sqlite-vec virtual table, keyed `page_id`, `FLOAT[EMBED_DIM]` + `model` / `created_at`. |

`pages_fts` has **no triggers** — because the indexed text lives in
`page_versions`, maintenance happens by hand inside the crawl write transaction
(delete the stale current row, insert the new current text) when
`pages.current_version_id` advances. Being contentless, FTS5 `snippet()` /
`highlight()` return NULL; keyword-search snippets are rebuilt in Python from
the current version's clean text (`db/pages.keyword_search`).

## Label Tables

Project-wide labeling for resources and domains (item 11, added at
`SCHEMA_VERSION 6`). Two **typed** join tables, not one polymorphic
`(target_type, target_id)` table, because `resources.id` is INTEGER and
`domains.host` is TEXT — typed FKs give clean cascade-on-delete (decision D2).
Labels are deliberately **not** a `findings` kind: they need a managed taxonomy
(preset palette, color, `builtin`) and referential integrity a stringly-typed
findings row loses.

| Table | Purpose |
| --- | --- |
| `labels` | The taxonomy. `name` (unique), `color`, `description`, `builtin`, `rank`, `hidden`, `created_at`. Seven `builtin=1` presets (Market, Forum, Directory, Blog, Service, Scam, Avoid) are seeded idempotently by name; presets can be recolored / redescribed / hidden but never renamed or deleted. Custom labels (`builtin=0`) are fully editable + deletable. |
| `resource_labels` | N:M page/resource ↔ label, keyed `(label_id, resource_id)`. Both FKs cascade. |
| `domain_labels` | N:M domain ↔ label, keyed `(label_id, host)`. Both FKs cascade. |

`rank` is the **single analyst-controlled ordering** (decision D5; lower number
ranks higher, warnings seeded at the top) that resolves three features at once:
the collapse-by-label fold home (the highest-ranked collapsed label a page
carries wins; domain-collapse sits at the floor of the same list, D6), the
"dominant label" for color-by-label, and the label-picker order. `hidden` is the
preset hide-from-picker toggle (decision D3).

The graph payload, node detail, and domain profile each carry `label_ids`
(direct, rank-ordered) and `domain_label_ids` (via the resource's host,
server-deduped); attach / detach / delete / reorder invalidate the graph cache.

## Important Relationships

| Relationship | Behavior |
| --- | --- |
| `resources.host -> domains.host` | Cascades. |
| `pages.resource_id -> resources.id` | Cascades (1:1). |
| `pages.current_version_id -> page_versions.id` | Cached pointer (forward ref). |
| `page_versions.page_id -> pages.id` | Cascades. |
| `graph_nodes.resource_id -> resources.id` | Cascades. |
| `edges.from_id / to_id -> resources.id` | Cascades. |
| `response_headers.page_version_id -> page_versions.id` | Cascades. |
| `findings.resource_id -> resources.id` | Cascades. |
| `findings.page_version_id -> page_versions.id` | Set to `NULL` if the version is deleted. |
| `collection_items.collection_id -> collections.id` | Cascades. |
| `collection_items.node_id -> resources.id` | Cascades. |
| `crawls.collection_id -> collections.id` | Set to `NULL` if the collection is deleted. |
| `crawl_nodes.crawl_id -> crawls.id` | Cascades. |
| `crawl_nodes.node_id -> resources.id` | Cascades. |
| `crawl_schedules.collection_id -> collections.id` | Set to `NULL`. |
| `probes.monitor_id -> monitors.id` | Cascades. |
| `analyses.resource_id -> resources.id` | Cascades. |
| `collection_analyses.collection_id -> collections.id` | Cascades. |
| `analyses / collection_analyses / cluster_analyses .prompt_id -> prompt_templates.id` | Set to `NULL` on delete (free-form prompt). |
| `auto_analysis_rules.prompt_id -> prompt_templates.id` | Set to `NULL` on delete. |
| `flags.node_id -> resources.id` | Cascades. |
| `resource_labels.label_id -> labels.id` | Cascades. |
| `resource_labels.resource_id -> resources.id` | Cascades. |
| `domain_labels.label_id -> labels.id` | Cascades. |
| `domain_labels.host -> domains.host` | Cascades. |

`jobs` has no FK on `target_id` — it is a soft reference resolved through
`payload` (e.g. `payload.crawl_id`, `payload.analysis_id`).

## Enum-Like Constraints

SQLite `CHECK` constraints enforce several stored states:

- `resources.state`: `unknown`, `known`, `crawled`, `dead`
- `edges.source`: `crawl`, `analyst`
- `findings.kind`: `entity`, `note`
- entity `type` (validated in `db/findings.py`, not a CHECK): `email`, `btc`, `xmr`, `pgp`, `onion`, `handle`, `blob`
- entity `source` (validated in `db/findings.py`): `crawl`, `llm`
- `crawls.mode` / `crawl_schedules.mode`: `Cross-site`, `BFS`, `DFS`, `Diverse`, `Focused`
- `jobs.kind`: `crawl`, `schedule`, `analysis`, `probe`, `live-crawl`, `batch`
- `jobs.target_type`: `url`, `domain`, `collection`, `cluster`
- `jobs.status`: `pending`, `running`, `done`, `failed`, `cancelled`, `paused`
- `flags.status`: `pending`, `flagged`, `investigating`, `done`, `dismissed`
- `flags.source`: `watchlist`, `analyst`
- `flags.priority`: `1`, `2`, `3`
- `labels.builtin`: `0`, `1`
- `labels.hidden`: `0`, `1`

`analyses` / `collection_analyses` / `cluster_analyses` carry no status column —
the old `waiting` / `pending` / `running` / `done` vocabulary is gone, replaced
by the linked job's status.

## Module Ownership

Use table-specific helpers under `backend/backend/db/` instead of writing SQL
inside routes when possible.

| Module | Typical Ownership |
| --- | --- |
| `core.py` | Schema, connection, transactions, defaults, boot sweep. |
| `resources.py` | URL identity + the `state` lifecycle machine (upsert, set_state, mark_dead, lookups). |
| `pages.py` | 1:1 page state, toggles, `get_page_detail`, keyword search. |
| `page_versions.py` | Versioning + crawl-write orchestration (`record_fetch`), FTS maintenance, history/diff reads. |
| `graph_nodes.py` | Per-resource layout/metric cache. |
| `jobs.py` | Unified work tracking — create/claim/transition/list/cancel. |
| `crawl.py` | Crawl run detail, counters, seeds, schedules; status read from the linked job. |
| `graph.py` | Graph payload construction and metrics. |
| `collections.py` | Collections and collection membership. |
| `embed.py` | Embedding persistence and vector serialization (page-keyed). |
| `settings.py` | Settings read/write and validation. |
| `monitors.py` | Monitor + probe persistence (probe writes a paired job). |
| `llm.py` | Per-resource / collection / cluster analysis detail/results; status on linked analysis jobs. Owns the cluster fingerprint helper + cluster enqueue/claim/mark. |
| `prompt_templates.py` | Analyzer prompt-template CRUD + built-in seeding + hide/unhide. |
| `auto_rules.py` | Auto-analysis rules CRUD + "rules matching trigger X" query + crawl-rule seeding. |
| `domains.py` | Per-domain metadata and analyst aliases. |
| `labels.py` | Label taxonomy CRUD, attach/detach (both join tables), member counts + lists, rank read/write, built-in preset seeding. |
| `edges.py` | Graph edge rows (crawl and analyst). |
| `findings.py` | Entities + notes (folded), with type/source in metadata JSON. |
| `fingerprints.py` | Response-header fingerprint clusters (current-version headers). |
| `flags.py` | Resource flags. |
| `graph_filters.py` | Graph hide/filter terms. |
| `search_engines.py` | Search-engine templates. |
| `stats.py` | Aggregate project counts. |
| `watchlist.py` | Watchlist terms. |

When adding schema, update `db/core.py` (bump `SCHEMA_VERSION` + `EXPECTED_TABLES`),
add table/module helpers, and extend tests around schema creation and route
behavior.
