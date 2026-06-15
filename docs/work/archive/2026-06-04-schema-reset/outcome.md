# Outcome — Schema Reset Milestone (item 6)

**Closed 2026-06-05.** One coordinated, breaking DB-delete cutover. Shipped on
`feat/schema-reset` across phases 0–6 (final test-migration + cleanup in
`abb35de`, `c3b00ec`). `SCHEMA_VERSION` 2 → 4 (2→3 was the reset; 4 added a
probe content hash).

## What shipped

1. **State vocabulary consolidation.** `resources.state`
   (`unknown` / `known` / `crawled` / `dead`) replaced `nodes.stub`,
   `crawl_queue.lookup_state`, and the analysis `waiting` derivation. One state
   machine, surfaced everywhere (graph payload, lookups, badges, filters).
2. **Resource / page / version split.** The single `nodes` table became
   `resources` (URL identity + state), `pages` (1:1 durable analyst/LLM state),
   `page_versions` (one row per fetch), plus `graph_nodes` (metric cache) and
   `findings` (entities + notes folded, type/source in metadata JSON). This
   **unlocked page versioning**: re-crawl a URL, keep both snapshots, diff them
   (right-pane timeline + on-demand diff; monitors surface content drift).
3. **Unified `jobs` table + Activity tab.** One work-tracking table with one
   status vocabulary (`pending`/`running`/`done`/`failed`/`cancelled`/`paused`)
   replaced the `crawl_queue` table and the per-source `status` columns on
   `crawls` / `analyses` / `collection_analyses` / `monitors`. Typed tables keep
   durable detail and read status from their linked job (back-reference in
   `payload` JSON), so the two can never drift. New bottom-pane
   `ActivityTab.svelte` over `routes/jobs.py` covers all six job kinds with
   per-row cancel/retry/pause/resume.

`pages_fts` is contentless (rowid = pages.id), maintained by hand in the crawl
write txn (no triggers); `embeddings` (vec0) is keyed `page_id`.

## Owner decisions (durable)

Carried from `decisions.md` (kept in this package):

- **Gate 1 — DROP `status` from `analyses` / `collection_analyses`.** Status is
  read from the linked job, identical to `crawls`. The typed tables are retained;
  only the redundant column went. A future result-level state returns under a
  different name, not `status`.
- **D4 revised — `pages.reviewed` stays a boolean.** No half-built, un-CHECKed
  `review_state` column ships here; the typed review-state machine is built whole
  by **item 7 (Intel pane)** as an additive migration with its UI.
- **Migration = DB delete.** No in-place migration, no adapter, no pre-wipe
  export (owner-declined). Dev data is disposable; empty state after cutover.
- D1/D2/D3/D5/D6 accepted as written in `schema-reset-ddl.md` (AUTOINCREMENT PKs;
  `analysis_excluded`+`opened_at` on `pages`; CHECK enums on `jobs`;
  current-version-only `response_headers` keyed by `page_version_id`; `findings`
  indexed on `resource_id`+`kind`).

## Bugs found and fixed during test migration

Migrating ~140 phase-2–5-stale tests onto the v3 surface surfaced four real
bugs — live code that read dropped columns/functions but had no remaining test
exercising it:

1. `services/project_state.py` `switch()` read/wrote the dropped `crawls.status`
   → now uses `crawl.find_active` + `jobs.cancel_active_for(payload_key='crawl_id')`.
2. `routes/crawl.py` `POST /api/crawl/stop` called a non-existent
   `crawl.mark_stopped` → added it (finalize the run + cancel the linked job).
3. `db/pages.keyword_search` used FTS5 `snippet()`, which returns NULL on the
   contentless `pages_fts` → snippet rebuilt in Python from the current version's
   clean text.
4. The acceptance walkthrough caught the last user-facing "stub" wording
   (`BulkImport` `+ Stub` button + raw-state badge) → "+ Mark Known", shared
   `STATE_LABEL`.

Two latent bugs were also fixed earlier in Phase 6: a dead context-menu gate
(`MenuTarget` read `.stub` off a `GraphNode`) and an `llm_worker.py` `NameError`
in the domain-label-skip event.

## Acceptance — all green

- Fresh DB boots empty (v4, 25 tables, `foreign_key_check` clean).
- Crawl → resources/pages/page_versions; re-crawl → second version
  (`content_changed=1`) + both snapshots diffable.
- Activity shows all 6 job kinds under one vocabulary; `/api/jobs/:id/*` actions.
- Search returns one hit per current page (no per-version dupes).
- No "stub" text in the UI; state labels consistent.
- Test suite green: backend **660 passed**; frontend `check` **0 errors**,
  `test` **386 passed**, single-bundle `build`; `make lint-security` OK.

## Honest framing

A **shape win + feature unlock, not a code-size win**. Net LOC was flat-to-
slightly-up (five tables ⇒ more joins/insert paths). Affected surface was wide
(~112 files) but mostly shallow renames. The payoff is page versioning, a single
work-status vocabulary, and a state machine that can't drift.

## Reference docs updated

`docs/reference/data-model.md` rewritten to v4; `features.md`,
`backend-structure.md`, `architecture.md` updated for the new tables, the
Activity/jobs surface, page versioning, and the resource/page/version split.

## Follow-ups (not in this milestone)

- Item 7 (Intel pane) builds the typed `review_state` machine (D4).
- `graph_nodes` metric persistence has no writer/reader yet (builder computes
  metrics live) — wire it with a "workers write graph_nodes" task when a
  consumer exists.
