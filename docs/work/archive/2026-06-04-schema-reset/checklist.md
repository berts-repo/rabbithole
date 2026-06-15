# Schema Reset — Cutover Checklist

Seeded from `source-checklist.md`, with the planning
reality-checks and the D4 revision (see `decisions.md`) baked in.
**One coordinated cutover: phases 2–4 land together.**

## Phase 0 — Promote (done)

- [x] Item 1 Pane Responsibility Reset landed.
- [x] Item 2 Shared UI Primitives landed.
- [x] Item 3 GraphCanvas Decomposition landed.
- [x] Item 4 NodeSet Workspaces landed.
- [x] Create `active/2026-06-04-schema-reset/`, remove item 6 from `NEXT.md`,
      repoint `ACTIVE.md`.

## Phase 1 — Schema sign-off

- [x] Consolidated DDL exists (`schema-reset-ddl.md`).
- [x] Gate 1: DROP `status` from `analyses`/`collection_analyses` — confirmed.
- [x] Gate 2: D1/D2/D3/D5/D6 accepted; D4 revised to `pages.reviewed` boolean.
- [ ] Apply D4 revision + Gate 1 into `schema-reset-ddl.md` (pages DDL + column
      mapping). Lock DDL — no further column changes once Phase 2 starts.

## Phase 2 — Stand up new schema, app boots empty

- [ ] Rewrite `core.py` schema blocks to the DDL.
- [ ] Bump `SCHEMA_VERSION` to 3; update `EXPECTED_TABLES`.
- [ ] Delete `_migrate_flags_table`, `_migrate_to_v2`, `_backfill_response_headers`.
- [ ] Replace the two boot sweeps with one `jobs` sweep.
- [ ] `pages_fts` contentless (rowid=pages.id), `embeddings` vec0 keyed page_id.
- [ ] Delete dev DB; backend boots empty, no crash; FTS/vec create cleanly.

## Phase 3 — Backend rewrite

- [x] Split `db/nodes.py` → resources/pages/page_versions/graph_nodes. *(verified)*
- [x] New `db/findings.py` (entities+notes folded; type/source in metadata JSON).
- [x] New `db/jobs.py` (insert/claim/transitions/list/cancel/pause/resume).
- [ ] Remove `db/crawl_queue.py`, `db/entities.py`, `db/notes.py` (after importers updated).
- [x] `db/crawl.py` — crawls drops `status`; status read from linked job; `set_started`/`finalize`. *(verified)*
- [x] `crawler/runtime.py` `run()` + `services/crawl_queue_runner.py` — crawl work-status on `jobs`; dispatcher claims via `jobs.claim_next_crawl`. *(verified)*
- [x] `db/monitors.py` + `services/monitor_daemon.py` — drop `last_status`; `record_probe` writes a paired `kind='probe'` job; daemon emits `jobs.changed`. *(verified)*
- [x] `db/llm.py` + `services/llm_worker.py` — drop `status`; target FK → resources; drop waiting split; status on linked `kind='analysis'` jobs. *(verified)*
- [x] `db/flags.py`, `db/edges.py` — FK re-point to resources (+ `insert_watchlist_flag`/`insert_crawl_edge` moved in).
- [x] `db/collections.py` — reads join resources + current page title. *(verified)*
- [x] `db/fingerprints.py` — current-version headers (`page_version_id`); cluster reads re-pointed.
- [x] `db/embed.py` + `services/embed_worker.py` — vec0 keyed `page_id`; `pending`→pages w/ current clean text; `semantic_search` joins pages→resources (`node_id`=resource). *(verified)*
- [x] FTS maintenance into crawl write txn (no triggers) — `page_versions._maintain_fts`.
- [x] `crawler/runtime.py` `_process_one` rewired to new helpers (data-write path).
- [ ] New `routes/jobs.py` (incl SSE via `routes/sse.py`); remove `routes/crawl_queue.py`; fold entities/notes routes onto findings.
- [x] `db/graph.py` — builder reads resources+pages+current page_versions; `_seed_node_dict` `stub`→`state`; headers via `page_version_id`; metrics over the crawled subgraph; depth from `crawl_nodes`. *(verified)*
- [x] Node-returning routes emit resource/page + `state` (nodes/search/harvest_search/domains/entities/notes/llm routes + db/stats + db/graph_filters reshaped; `import backend.main` succeeds). *(verified)*
- [ ] Workers write resources/pages/page_versions/graph_nodes + `jobs`; dead-state auto-transition.

## Phase 4 — Frontend rewrite

- [x] `lib/api/types.ts` — `state` union replaces `stub`; resource/page/version shapes. *(Task 1, `6aad635`)*
- [x] New `lib/api/jobs.ts`, `lib/stores/jobs.svelte.ts` (SSE). *(Task 4, `f8ecf11`)*
- [x] graph store + applyPayload + 5 layouts + reducerController → state-based. *(Task 2, `b51646a`)*
- [x] Update ~32 `node.stub` + `summary`/`body_text_clean` callsites. *(Task 3, `61d6714`)*
- [x] State label mapping; remove all "Stub"/"not crawled" labels. *(Task 3, `61d6714`)*
- [x] New `views/bottom/ActivityTab.svelte`; register in BottomPane + BOTTOM_GROUPS. *(Task 5, `963ba38`)*
- [x] Remove `AnalysesTab.svelte`; keep `LiveCrawlTab`. *(Task 5, `963ba38`)* — crawl work absorbed into Activity as `kind='crawl'` rows; **`CrawlQueuePanel` retirement deferred to Task 5b** (left pane, legacy `crawl_queue` API — rides Phase 6).

## Phase 5 — Page versioning UI

- [x] Right-pane PageTab — version timeline + picker. *(Task 1, see handoff-phase5.md)*
- [x] Snapshot diff view — on-demand text diff of two page_versions. *(Task 1)*
- [x] Right-pane DomainTab — snapshot comparison over time. *(Task 2)*
- [x] Monitor content-change surfacing in Monitors/Activity. *(Task 3)*

## Phase 6 — Delete dead code

Code work done. Test migration complete — all ~140 phase-2–5-stale tests
migrated to v3; backend suite green (660 passed). See
`handoff-phase6-test-migration.md` for the recipe. Four real bugs surfaced and
fixed during migration (the schema reset had left live readers of dropped
columns/functions that no test had re-exercised yet):

- `services/project_state.py` `switch()` read/wrote the dropped `crawls.status`
  — now checks `crawl.find_active` and force-stops via
  `jobs.cancel_active_for(payload_key='crawl_id')`.
- `routes/crawl.py` `/api/crawl/stop` called a non-existent `crawl.mark_stopped`
  — added `crawl.mark_stopped` (finalize the run + cancel the linked job).
- `db/pages.keyword_search` used FTS5 `snippet()`, which returns NULL on the
  contentless `pages_fts` — snippet is now rebuilt in Python from the current
  version's clean text (`_build_snippet`; route passes raw `query_text`).
- Frontend `check` cleared to **0 errors** (was ~10 pre-existing): added a
  `title` prop to `TextButton`, widened `isMultiSelectModifier`, dropped dead
  vars/imports, double-cast a test fixture.

- [x] Remove stub-vs-crawled special cases (frontend + backend). *(deleted
      `db/nodes.py`/`entities.py`/`notes.py`; frontend `.stub` field reads → `state`)*
- [x] Remove old status shims, `waiting` derivation, per-source status translations.
- [x] Remove per-source history endpoints; old `nodes`-shaped accessors.
      *(`routes/crawl_queue.py` slimmed to enqueue-only; `crawlQueue.ts` slimmed;
      `CrawlQueuePanel.svelte` deleted)*
- [x] Grep sweep zero: `lookup_state`, `nodes_fts`, `body_html`, dead
      `crawl_queue` table accessors, frontend `.stub` field. *(Remaining "stub"
      hits are internal graph-halo rendering vocabulary + historical "replaces
      old X" notes — not stale-shape callsites.)*
- Bonus fixes found en route: latent context-menu bug (`MenuTarget` read
  `.stub` off `GraphNode`, gating was dead) and a real `llm_worker.py`
  `NameError` (`node_id` undefined in the domain-label-skip event).

## Acceptance

- [x] Fresh DB → boots empty: v4, 25 tables, all content tables 0 rows,
      `foreign_key_check` clean; frontend single-bundle build OK.
- [x] Crawl → resources/pages/page_versions rows; re-crawl → second version
      (`content_changed=1`) + both snapshots retrievable for diff. *(smoke)*
- [x] Activity shows all 6 job kinds under one 6-status vocabulary; `/api/jobs`
      + `/api/jobs/:id/{cancel,retry,pause,resume}`; ActivityTab registered in
      BottomPane/BOTTOM_GROUPS and wired to those endpoints.
- [x] Search returns one hit per current page (3 versions across 2 pages → 2
      hits, current-version title only). *(smoke)*
- [x] No "stub" text anywhere; state labels consistent — `BulkImport` `+ Stub`
      → `+ Mark Known`, toast reworded, badge now uses shared `STATE_LABEL`.
- [x] Test suite green: backend 660 passed; frontend `check` 0 errors,
      `test` 386 passed, `build` single-bundle; `make lint-security` OK.
