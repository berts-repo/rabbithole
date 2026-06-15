# Checklist — Analysis / Intel Pane

Status: **Phase 1 complete** (2026-06-08) — backend additive schema + routes
landed and fully tested; suite green (709 passed). Next: Phase 2 (Intel shell +
Compose form).

## Phase 1 — Backend schema + routes
- [x] `prompt_templates` table + seed builtins (`builtin=1`)
- [x] `auto_analysis_rules` table (target_filter_json placeholder for item 11)
- [x] `cluster_analyses` table (fingerprint-keyed)
- [x] nullable `prompt_id` FK on analyses / collection_analyses / cluster_analyses
- [x] `SCHEMA_VERSION 4 → 5`, additive migration (no DB delete)
- [x] `db/prompt_templates.py`, `db/auto_rules.py`, `db/llm.py` cluster + fingerprint helper
- [x] `routes/prompt_templates.py`, `routes/auto_rules.py`, `routes/llm.py` extensions
- [x] `/api/llm/status` load/capacity block + concurrency honored in worker
      (`llm.batch_size` setting registered in `db/settings.py`, 1–50)
- [x] auto-analysis enqueue hook — collection-add wired into the
      `/api/collections/{cid}/items` route (D4 Phase-1 scope); crawl trigger
      stays on legacy `llm.auto_enqueue.*` until Phase 3 migrates it
- [x] routers registered in `main.py`
- [x] pytest per module + v4→v5 migration test (`tests/test_intel_*.py`)
- [x] lint-security + backend tests green

### Closed-out notes (groundwork reconciliation, 2026-06-08)
The 2026-06-05 "Add analysis intel backend groundwork" commit landed the
implementation but left Phase 1 short of its exit gate. This pass closed it:
- Fixed 5 tests the groundwork broke (`SCHEMA_VERSION` pin 4→5;
  `add_items` now returns `added_ids`).
- Added the missing coverage: `test_intel_prompt_templates`, `_auto_rules`,
  `_cluster_analyses`, `_migration` (v4→v5 hard gate), `_worker_status`.
- Wired the collection-add hook — `auto_enqueue_for_collection_add` existed but
  was never called; the route now invokes it for genuinely new members only.
- Registered the `llm.batch_size` setting so the configurable concurrency
  number is actually settable (the worker read it but `put_setting` rejected it).

## Phase 2 — Intel shell + Compose form  ✅ (2026-06-08)
- [x] `views/left/IntelTab.svelte` shell wired into `LeftSidebar.svelte`
      (collapsible sections; collapse persisted to localStorage like
      `layout.svelte.ts`, not the settings table — pure view-state)
- [x] `views/left/intel/ComposeForm.svelte` — dispatch switch handles all
      target kinds (nodes/cluster/collection); Phase 2 UI sources the **nodes**
      target (current selection or a staged set). Cluster/collection targets
      get their entry points in Phase 4 (cluster Q&A) / Phase 3 (collection)
- [x] `views/left/intel/WorkerControls.svelte` + load indicator (8s poll of
      `/api/llm/status`; first frontend surface over the worker-control routes)
- [x] `lib/api/llm.ts` (worker status + lifecycle), `lib/api/prompts.ts`,
      `analyses.ts` extensions (cluster + collection). Pure target model split
      to `lib/stores/intelComposeTarget.ts` for vitest
- [x] `queueAnalysis` helper becomes the real funnel (stage target + switch to
      Intel tab; no toast stub)
- [x] vitest (`intelComposeTarget.test.ts`) + frontend check/test/build green

### Phase 2 scope notes (build-order decisions)
- **`autoRules.ts` API + Auto-analysis Rules UI** build together in **Phase 3**
  with their consumer (`AutoAnalysisRules.svelte`) — that is the correct order
  for the full feature; a client with no consumer would be dead code now.
- **Prompt-template picker** ships in **Phase 3** with the template management
  UI *and* the worker change that makes the worker consume a template `body`.
  Until the worker uses the body, selecting a template only records provenance,
  so a picker now would be non-functional UI. The `prompts.ts` list client is
  in place for the analyzer picker the moment that lands.
- **Menu → compose cutover + `QueueAnalysisModal` removal** is **Phase 4** per
  plan; Phase 2 makes `queueAnalysis` real and the Intel compose reachable via
  the Intel tab, ready for that cutover.

## Phase 3 — Remaining Intel sections
- [x] `AutoAnalysisRules.svelte` (simple v1) + **D4 crawl-trigger migration**.
      Backend: `auto_rules.seed_crawl_rules` (idempotent, carries the legacy
      `llm.auto_enqueue.*` state once), seeded at `CrawlDB` init;
      `auto_enqueue_for_node` rewritten to read enabled `crawl` rules (legacy
      `_setting_suffix_for_type` removed). Parity tests + Phase 1 test updates;
      backend 711 green. Frontend: `lib/api/autoRules.ts` + the section (crawl
      toggles + per-collection rules). The legacy settings now serve only as the
      one-time seed source; the rule's `enabled` flag is the runtime authority.
- [ ] `PromptTemplates.svelte` (CRUD; builtins hideable) — **blocked on an owner
      decision**: should the worker substitute a template `body` into the model
      call? `prompts.py` is the auditable single source of prompt text with
      per-type output validators (Risk Score→int, Category→enum); routing an
      analyst-editable body through the model is a new prompt-injection surface
      against those contracts. Management CRUD UI can ship regardless; the
      analyzer-picker wiring waits on this call.
- [x] Embedding section — `intel/EmbeddingSection.svelte` over `lib/api/embed.ts`
      (status + progress + pause/resume, 10s poll). Start/stop stays in Settings.
- [x] Collection Analysis section — `intel/CollectionAnalysis.svelte`: per-URL
      (batch over crawled members, stubs excluded) + synthesis (multi_page
      types via the collection-analyses route). Reuses the compose dispatch.
      Fixed a latent client-type bug: `listCollections` now typed
      `CollectionListRow[]` (the route already returned `item_count`).
- [x] frontend check/test/build green (0 errors / 392 vitest / single bundle)

## Phase 4 — Consolidation  ✅ (2026-06-09)
- [x] `right/AnalysisTab.svelte` narrowed to inspect-only — the Queue button
      funnels the selection into Intel · Analyse via `queueAnalysis`.
- [x] `QueueAnalysisModal.svelte` **removed** — all four callers (GraphCanvas,
      BottomPaneContextMenu, ActionBar, AnalysisTab) route through the
      `queueAnalysis` funnel. Context-menu adapter dep renamed
      `openAnalysisModal` → `queueAnalysisForNodes`.
- [x] cluster `QnATab.svelte` rewritten inline on `cluster_analyses` (Option B):
      drops the bespoke per-node batch+poll; composes inline via
      `createClusterAnalysis` (one **synthesis** answer, not per-page) and polls
      the membership fingerprint, doubling as the cluster inspect surface.
- [x] **D1 backend completion** — Phase 1 left `cluster_analyses` non-functional
      (membership unstored; worker never claimed cluster jobs). This pass added
      a `resource_ids` JSON membership snapshot (DDL + guarded ALTER), wired
      `claim_next_cluster` + `_process_cluster_job` into the worker tick, and
      added a `Cluster Q&A` multi-page prompt spec (question-aware
      `render_multi`). Route rejects single-page types for clusters.
- [x] duplicate dispatch removed. **Note:** the plan's "≤1 `createAnalysesBatch`
      caller" assumed Option-A unified funnel; under owner-chosen Option B
      (per-section inline compose) there are exactly **two** batch callers —
      `ComposeForm` (nodes) and `CollectionAnalysis` (per-URL) — each the single
      dispatch for its kind, no duplication. ComposeForm's dead
      `cluster`/`collection` branches + those `ComposeTarget` kinds removed.
- [x] tests updated — backend cluster e2e + frontend `fingerprint.test.ts`
      (pinned to backend) + trimmed `intelComposeTarget.test.ts` + adapter mock.

### Phase 4 scope decisions (owner, 2026-06-08/09)
- **Cluster Q&A UX → Option B (inline ask).** Keeps the question box in the
  cluster workspace (no pane jump) while sharing the `createClusterAnalysis`
  dispatch + `cluster_analyses` storage — Q&A is the most iterative loop and a
  left↔right ping-pong taxes it; "one compose path" holds at the dispatch level.
- **Prompt templates → deferred to a follow-up (Option C), out of this package.**
  Worker body-substitution is a data-integrity concern for the *typed* output
  contracts (Risk Score→int, Category→enum), not the security/injection surface
  first framed (page content is the real injection vector and already exists).
  Target: body drives free-form types only; typed stay on audited `prompts.py`.
  Tracked in `NEXT.md`. (Closes the open Phase-3 `PromptTemplates.svelte` item.)

## Phase 5 — Verify + docs  ✅ (2026-06-09)
- [x] Activity filters `kind = analysis` confirmed — cluster jobs are
      `kind='analysis'` (`target_type='cluster'`); `ActivityTab.svelte:111`
      routes them to the right-pane Analysis view like every other analysis.
- [x] net LOC reconciled. Frontend consolidation is **−151 net** (358 removed,
      207 added incl. the tested fingerprint helper). It does **not** hit the
      spec's −300..−600 because (a) that target assumed the Option-A unified
      funnel that collapses every surface to one, which Option B traded away for
      the in-context cluster loop, and (b) this pass had to *complete* the
      cluster backend Phase 1 left non-functional (net-additive). The
      consolidation goals — one modal gone, bespoke cluster poll gone, dead
      dispatch branches gone — are met.
- [x] reference docs updated (features, backend-structure, data-model,
      frontend-structure, architecture) to v5 / Intel current truth.
- [x] full suite green — backend 714 passed + lint-security OK (one runtime
      test is timing-flaky under full-suite load; passes in isolation, untouched
      by this work); frontend check 0 errors / 393 vitest / single bundle.
- [x] `outcome.md` written, package archived, `ACTIVE.md` repointed.
