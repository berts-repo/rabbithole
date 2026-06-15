# Schema Reset — Cutover Checklist

## How to use

Concrete, sequenced task list for the Schema Reset Milestone
(`schema-reset.md`), derived from that spec's six-phase build order, the
consolidated DDL in `schema-reset-ddl.md`, and the worker/API/UI changes in
`unified-activity-view.md`.

**Planning artifact, not active work.** The milestone is queue item 6 in
`NEXT.md`, gated behind four frontend packages. When it is promoted to
active, this file's content seeds the
`active/YYYY-MM-DD-schema-reset/checklist.md` and `ACTIVE.md` is repointed
then — not now.

**One coordinated cutover.** Phases 2–4 land together. Do not ship the new
schema with the old frontend, or the new frontend with the old schema
(`schema-reset.md` → "Implementation Order").

---

## Phase 0 — Preconditions (hard gate)

- [ ] Item 1 **Pane Responsibility Reset** landed.
- [ ] Item 2 **Shared UI Primitives** landed — Activity tab is built on
      `StatusBadge` / `EmptyState` / `IconButton` / `PaneTabs` from this item.
- [ ] Item 3 **GraphCanvas Decomposition** landed.
- [ ] Item 4 **NodeSet Workspaces** landed — frontend on its final workspace
      model before data shapes change underneath it.
- [ ] Promote milestone: create `active/YYYY-MM-DD-schema-reset/`
      (`README.md`, `plan.md`, `checklist.md` from this file), remove item 6
      from `NEXT.md`, repoint `ACTIVE.md` — all in one change.

## Phase 1 — Schema design & sign-off

- [x] Consolidated CREATE script, column mapping, delta — `schema-reset-ddl.md`.
- [ ] **Owner: confirm or overrule** dropping `status` from `analyses` /
      `collection_analyses` (the resolved spec inconsistency).
- [ ] **Owner: review** fill-in decisions D1–D6 in `schema-reset-ddl.md`.
- [ ] Lock final DDL — no further column changes once Phase 2 starts.

## Phase 2 — Stand up new schema, app boots empty

- [ ] Rewrite `core.py` schema blocks (`_SCHEMA_STATEMENTS`,
      `_INDEX_STATEMENTS`, `_FTS_STATEMENTS`, `_VEC_STATEMENT`) to the new DDL.
- [ ] Bump `SCHEMA_VERSION` to 3.
- [ ] Delete migration/backfill helpers: `_migrate_flags_table`,
      `_migrate_to_v2`, `_backfill_response_headers`.
- [ ] Replace `_sweep_stale_crawls` + `_sweep_stale_queue_rows` with one
      `jobs` sweep (`running` → `failed`, `error='process restarted'`).
- [ ] Update `EXPECTED_TABLES`.
- [ ] Delete dev DB file; confirm backend boots to empty state, no crash.
- [ ] Confirm `pages_fts` (contentless) and `embeddings` vec0 (keyed
      `page_id`, `FLOAT[384]`) create cleanly with sqlite-vec.

## Phase 3 — Backend rewrite

**db/ modules**
- [ ] Split `db/nodes.py` → `resources.py`, `pages.py`, `page_versions.py`,
      `graph_nodes.py`.
- [ ] New `db/findings.py` — entities + notes folded in; entity `type`/`source`
      preserved in `metadata` JSON; old `entities` CHECK enum becomes
      write-path validation.
- [ ] New `db/jobs.py` — insert, claim, status transitions, list (filters:
      kind/status/target_type/since/limit), cancel/retry/pause/resume.
- [ ] Remove `db/crawl_queue.py`, `db/entities.py`, `db/notes.py`.
- [ ] `db/crawl.py` — `crawls` drops `status`; `crawl_nodes.node_id` and
      `crawl_schedules` FK re-point; `crawls` reads status from linked `jobs`.
- [ ] `db/monitors.py` — drop `last_status`.
- [ ] `db/analyses.py` + `db/collection_analyses.py` — drop `status`; target
      FK to `resources(id)`.
- [ ] `db/flags.py` — `node_id` FK re-point to `resources(id)`.
- [ ] `db/collections.py` — `collection_items.node_id` → `resources(id)`.
- [ ] `db/edges.py` — `from_id`/`to_id` → `resources(id)`.
- [ ] `db/fingerprints.py` — read current-version `response_headers`.
- [ ] `db/embed.py` — embeddings keyed per page; re-embed on version advance.
- [ ] FTS maintenance moves into the crawl write transaction (drop the four
      `nodes_*` triggers; manual delete+insert on `current_version_id` advance).

**routes/**
- [ ] New `routes/jobs.py` — `GET /api/jobs`, `GET /api/jobs/:id`,
      `POST /api/jobs/:id/{cancel,retry,pause,resume}`, `SSE /api/jobs/stream`
      (reuse existing `routes/sse.py` infra).
- [ ] Remove `routes/crawl_queue.py` (folds into jobs); fold
      `routes/entities.py` + `routes/notes.py` onto findings.
- [ ] All node-returning routes emit new resource/page shapes + `state` vocab:
      `nodes.py`, `graph.py`, `search.py`, `harvest_search.py`,
      `collections.py`, `fingerprints.py`, `domains.py`, `stats.py`, `edges.py`.
- [ ] Merge per-source status/history endpoints into `GET /api/jobs`.

**workers**
- [ ] Crawl runner — writes `resources`/`pages`/`page_versions`/`graph_nodes`;
      computes `body_hash` + `content_changed`; advances
      `pages.current_version_id`; maintains FTS in-txn; writes `jobs`
      (`kind='crawl'`, live progress `kind='live-crawl'`).
- [ ] Scheduled-crawl scheduler — writes `kind='schedule'`; spawns
      `kind='crawl'` children on fire with `payload.crawl_schedule_id`.
- [ ] LLM/analysis worker — writes `kind='analysis'` jobs + typed analyses rows
      (status from `jobs`, `payload` back-reference).
- [ ] Monitor daemon — writes `kind='probe'` jobs + `probes` rows; compares
      latest `page_versions` hash for content-change alerts.
- [ ] Batch intake — writes `kind='batch'` jobs.
- [ ] Dead-state auto-transition after the configurable failure threshold
      (default 5 / 7 days); manual force-dead via right-pane action.

## Phase 4 — Frontend rewrite

- [ ] `lib/api/*.ts` — response shapes for resources/pages/versions; `state`
      union type replacing `stub`.
- [ ] New `lib/api/jobs.ts`.
- [ ] New `lib/stores/jobs.svelte.ts` — live SSE stream.
- [ ] `lib/stores/graph.svelte.ts` — payload shape (resource + graph_nodes).
- [ ] Update every component reading `node.body_text_clean` / `node.stub` /
      `node.summary` to the new shape.
- [ ] State label mapping: `unknown` → "Unknown", `known` → "Known
      (uncrawled)", `crawled` → "Crawled", `dead` → "Dead". Remove "Stub".
- [ ] New `views/bottom/ActivityTab.svelte` on shared primitives.
- [ ] Remove `views/bottom/AnalysesTab.svelte` and the bottom-pane Crawl Queue
      tab (absorbed into Activity).
- [ ] Live Crawl tab → Activity filter (`kind='live-crawl'`), keep streaming
      log view.

## Phase 5 — Page versioning UI

- [ ] Right-pane Page tab — version timeline + version picker (picker pins its
      own version id, allowed to lag `current_version_id`).
- [ ] Snapshot diff view — on-demand text diff of two `page_versions` (no
      `page_diffs` cache table).
- [ ] Right-pane Domain tab — snapshot comparison over time (added/removed/
      drifted/identical pages).
- [ ] Monitor content-change surfacing in the Monitors/Activity views.

## Phase 6 — Delete dead code

- [ ] Remove stub-vs-crawled special cases (frontend + backend).
- [ ] Remove old status shims, `analyses` `waiting` derivation, per-source
      status-vocabulary translations.
- [ ] Remove per-source history endpoints (merged into `/api/jobs`).
- [ ] Remove old `nodes`-shaped accessors.
- [ ] Grep sweep returns zero stale callsites: `stub`, `lookup_state`,
      `body_html`, `nodes_fts`, `crawl_queue`, `node.summary` on the old shape.

## Acceptance criteria

- [ ] Fresh DB → backend + frontend boot to empty state.
- [ ] Crawl a URL → `resources`/`pages`/`page_versions` rows written;
      re-crawl → second version + a working diff.
- [ ] Activity tab shows all job kinds under one status vocabulary; row
      actions (cancel/retry/pause/resume) hit `/api/jobs/:id/*`.
- [ ] Search returns one hit per current page (no per-version dupes).
- [ ] No "stub" text anywhere in the UI; state labels consistent across
      graph / collections / search / right pane.
- [ ] Test suite green (delegate the run to the `test-runner` subagent).
