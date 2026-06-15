# Schema Reset — Executable Plan

This is the executable overlay on top of the authoritative DDL
(`source-ddl.md`) and task source
(`source-checklist.md`). It names the current code each phase
touches, grounded against the tree, and records the discrepancies found during
planning. **One coordinated cutover: phases 2–4 land together.**

## Reality-checks found during planning

- **No bottom-pane Crawl Queue tab exists to remove.** The queue surfaces via
  `frontend/src/components/crawl/CrawlQueuePanel.svelte` and the SSE
  `frontend/src/views/bottom/LiveCrawlTab.svelte`. Activity absorbs that surface
  and `AnalysesTab.svelte`; the checklist's "remove bottom-pane Crawl Queue tab"
  is a no-op — instead retire the `CrawlQueuePanel` queue-list usage into
  Activity (`kind='crawl'`).
- **`db/nodes.py:promote_waiting_analyses()` is the `waiting` derivation** the
  reset removes — analyses no longer wait on stub→crawled promotion once state
  lives on `resources` and analysis status lives on `jobs`.
- DB access seam confirmed: `CrawlDB.read()` (`db/core.py:746`) and
  `CrawlDB.transaction()` (`:765`). No raw connections (`make lint-security`
  blocks them).
- SSE infra to reuse for `/api/jobs/stream`: `routes/sse.py` `sse_stream()`
  (used today by `crawl_queue.py`, `harvest_search.py`).

## Phase 2 — Stand up new schema, boot empty (`backend/backend/db/core.py`)

- Rewrite `_SCHEMA_STATEMENTS` (~79–355), `_INDEX_STATEMENTS` (~357–383),
  `_FTS_STATEMENTS` (~387–409), `_VEC_STATEMENT` (~411) to the DDL. FTS becomes
  contentless `pages_fts` keyed `rowid = pages.id`; **drop the 3 `nodes_*`
  triggers** (maintenance moves into the crawl txn). `embeddings` vec0 re-keyed
  `page_id` (`FLOAT[384]`, `EMBED_DIM`).
- Bump `SCHEMA_VERSION = 3`; update `EXPECTED_TABLES` (~420–445).
- Delete dead migration/backfill: `_migrate_flags_table`, `_migrate_to_v2`,
  `_backfill_response_headers`.
- Replace `_sweep_stale_crawls` + `_sweep_stale_queue_rows` with one `jobs`
  sweep: `UPDATE jobs SET status='failed', error='process restarted' WHERE
  status='running'`.
- Keep `crawl.queue_paused` in `DEFAULT_SETTINGS` (now gates dispatch of
  `jobs WHERE kind='crawl' AND status='pending'`).
- Delete dev DB; confirm backend boots empty; `pages_fts` + `embeddings` create.

## Phase 3 — Backend rewrite (lands with Phase 4)

**db/ modules:** split `db/nodes.py` → `resources.py`/`pages.py`/
`page_versions.py`/`graph_nodes.py` (re-home `record_fetch`/
`record_failed_fetch`/`upsert_stub`→`upsert_resource(state='known')`/`get_node`/
toggles; drop `promote_waiting_analyses`). New `db/findings.py` (fold
`entities.py` + `notes.py`), `db/jobs.py`. Remove `db/crawl_queue.py`. Re-point
FKs / drop status columns: `crawl.py` (crawls drops `status`; `crawl_nodes`,
`crawl_schedules` → `resources(id)`), `monitors.py` (drop `last_status`),
`llm.py` + collection_analyses (drop `status`, target → `resources(id)`, drop
waiting/pending split), `flags.py`, `collections.py`, `edges.py`. Re-key:
`fingerprints.py` (current-version headers), `embed.py` (per page).

**routes/:** new `routes/jobs.py` (`GET /api/jobs`, `GET /api/jobs/:id`,
`POST /api/jobs/:id/{cancel,retry,pause,resume}`, `SSE /api/jobs/stream` via
`routes/sse.py`). Remove `routes/crawl_queue.py`; fold `routes/entities.py` +
`routes/notes.py` onto findings. Reshape node-returning routes to resource/page
+ `state`: `nodes.py`, `graph.py`, `search.py`, `harvest_search.py`,
`collections.py`, `fingerprints.py`, `domains.py`, `stats.py`, `edges.py`.

**workers:** `crawler/runtime.py` (`_process_one`) writes resources/pages/
page_versions/graph_nodes; computes `body_hash` + `content_changed`; advances
`pages.current_version_id`; maintains `pages_fts` in-txn; writes `jobs`
(`kind='crawl'`, live `kind='live-crawl'`); dead-state auto-transition (default
5 fails / 7 days). `crawl_queue_runner.py` scheduler → `kind='schedule'`, spawns
`kind='crawl'`. `llm_worker.py` `_persist` → `kind='analysis'` + typed rows.
`monitor_daemon.py` → `kind='probe'` + `probes` + content-change hash compare.
`embed_worker.py` per-page. Batch intake → `kind='batch'`.

## Phase 4 — Frontend rewrite (lands with Phase 3)

`lib/api/types.ts`: `stub: boolean` → `state: 'unknown'|'known'|'crawled'|'dead'`
on `NodeRow`/`GraphNode`/`CollectionItem`; add resource/page/version shapes; drop
`NodeLookupState 'stub'` + `CrawlQueueLookupState`. New `lib/api/jobs.ts`,
`lib/stores/jobs.svelte.ts` (SSE). `lib/stores/graph.svelte.ts` +
`lib/graph/model/applyPayload.ts` (~16 checks) + 5 `layouts/*.ts` +
`reducerController.ts` → state-based; `graphFilters` `showStubs` → "show
uncrawled" (`state !== 'crawled'`). Update ~32 `node.stub` callsites + `summary`/
`body_text_clean` readers. State labels everywhere (Unknown / Known (uncrawled) /
Crawled / Dead); remove every "Stub"/"not crawled" label (`PageTab.svelte:389`,
`CollectionTab` badge, `QueueAnalysisModal`, `DomainTab` placeholder). New
`views/bottom/ActivityTab.svelte` on shared primitives, registered in
`BottomPane.svelte` + `workspace.svelte.ts BOTTOM_GROUPS`. Remove `AnalysesTab`;
retire `CrawlQueuePanel` queue list into Activity; keep `LiveCrawlTab`.

## Phase 5 — Page versioning UI

Right-pane `PageTab.svelte` version timeline + picker (picker pins its own
version id, may lag `current_version_id`). On-demand text diff of two
`page_versions` (no `page_diffs` cache). Right-pane `DomainTab.svelte` snapshot
comparison (added/removed/drifted/identical). Surface monitor content-change.

## Phase 6 — Delete dead code

Remove stub-vs-crawled special cases, status shims, the `waiting` derivation,
per-source status translations, per-source history endpoints, old `nodes`-shaped
accessors. Grep sweep zero: `stub`, `lookup_state`, `body_html`, `nodes_fts`,
`crawl_queue`, old-shape `node.summary`.

## Reuse (don't reinvent)

`CrawlDB.read()`/`transaction()`; `routes/sse.py:sse_stream()`; item-2 shared
primitives (`StatusBadge`/`EmptyState`/`IconButton`/`PaneTabs`);
`buildNodeSetPredicate` + workspace-scope seam (item 4, unchanged — resources
remain the node identity); `fingerprints.py` header normalization (re-key only).

## Verification

Backend pytest via `test-runner` subagent (rewrite `tests/test_b2_schema.py`;
update `test_b7_*`/`test_b5c_*`/`test_crawl_queue_*`→jobs/`test_f3_nodes_lookup`
→state). `npm run check` clean; `npm run test` (update applyPayload/layout/
bottom-helper to `state`; add jobs store tests). `npm run build` (bundle guard);
`make lint-security` clean. E2E: fresh DB → boot empty → crawl → resources/pages/
page_versions rows → re-crawl → diff → Activity all kinds → search one hit per
current page → zero "stub" UI text.
