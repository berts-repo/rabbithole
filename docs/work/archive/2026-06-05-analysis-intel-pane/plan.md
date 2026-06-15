# Plan — Analysis / Intel Pane

Five phases. Each phase is a vertical slice of the **whole** package and ends
green (lint-security + backend tests + frontend check/test/build). The order is
the build order toward the complete feature, not a staged trimming of scope.

Scope decisions D1–D3 are settled in `decisions.md` (Cluster Q&A in; auto-rules
simple; prompt templates full CRUD, project-local, nullable FK).

---

## Phase 1 — Backend additive schema + routes

Lands the storage and API surface everything else builds on. Additive,
non-destructive migration; `SCHEMA_VERSION 4 → 5`.

**Schema (`db/core.py`)**
- New table `prompt_templates` (id, name, analysis_type, body, builtin,
  created_at, updated_at). Seed built-in presets with `builtin = 1`.
- New table `auto_analysis_rules` (id, trigger_kind, target_filter_json,
  prompt_id FK nullable, analysis_type, model, enabled, created_at).
- New table `cluster_analyses` (id, cluster_fingerprint, label, analysis_type,
  model, result, question, prompt_id FK nullable, priority, created_at,
  updated_at) — mirrors `analyses`, keyed by fingerprint not a cluster id (D1).
- Add nullable `prompt_id` FK to `analyses`, `collection_analyses`,
  `cluster_analyses` via guarded `ALTER TABLE` (idempotent).
- Bump `SCHEMA_VERSION`; additive migration path that does NOT delete the DB.

**DB modules (`db/`)**
- `db/prompts.py` — CRUD + preset seeding + hide/unhide for builtins.
- `db/auto_rules.py` — CRUD + "rules matching trigger X" query.
- Extend `db/llm.py` — `cluster_analyses` create/get/list + job linking,
  fingerprint compute helper (sorted resource_ids → SHA-256 → truncated hex).

**Routes**
- `routes/prompts.py` — `GET/POST/PATCH/DELETE /api/prompts` (DELETE refuses
  builtins; hide instead).
- `routes/auto_rules.py` — `GET/POST/PATCH/DELETE /api/auto-analysis-rules`.
- Extend `routes/llm.py` — `cluster_analyses` create/list/get/rerun/delete;
  add a load/capacity block (in-flight, queue depth, concurrency) to
  `GET /api/llm/status`; add a capacity setter if concurrency is configurable.
- Register the two new routers in `main.py`.

**Worker (`services/llm_worker.py`)**
- Honor the configured concurrency number; expose in-flight + queue depth for
  the status route. Auto-analysis hook: on crawl-page-complete and
  collection-add events, consult `db/auto_rules.py` and enqueue jobs.

**Tests** — pytest for each new db module + route module; migration test that an
existing v4 DB upgrades to v5 without data loss.

**Exit:** lint-security green, backend tests green.

---

## Phase 2 — Intel shell + Compose form

The unifying piece. Fill the existing `intel` left tab body.

**Frontend**
- `views/left/IntelTab.svelte` — section shell (collapsible sections, per-section
  collapsed state persisted via settings, matching the F5 intent spec layout).
  Wire into `LeftSidebar.svelte` replacing the placeholder branch.
- `views/left/intel/ComposeForm.svelte` — single form: target picker (current
  selection / collection / cluster / graph scope / specific node ids),
  analyzer picker (model + prompt template, free-form when no template),
  scope options (collection/cluster: individual / synthesis / both), run/queue.
- `views/left/intel/WorkerControls.svelte` — start/stop/pause/resume (existing
  routes) + live load indicator (in-flight, queue depth, concurrency) from the
  Phase-1 status block.
- `lib/api/` — add `prompts.ts`, `autoRules.ts`; extend `analyses.ts` for
  cluster analyses + the status load block.
- **Make `queueAnalysis` real** in `lib/contextMenu/actions.ts`: instead of the
  toast stub, it opens the Intel compose section pre-populated with the target.
  This is the single funnel all callers use.

**Tests** — vitest for compose target/scope derivation + the action helper.

**Exit:** compose form queues every target kind through the shared helper;
worker controls reflect real state. Frontend check/test/build green.

---

## Phase 3 — Remaining Intel sections

On top of Phase-1 routes.

**Frontend**
- `views/left/intel/AutoAnalysisRules.svelte` — toggle "auto-analyze newly
  crawled with analyzer X" + per-collection rule list (D2 simple form).
- `views/left/intel/PromptTemplates.svelte` — list + create/edit/clone/delete;
  builtins hideable not deletable (D3).
- Embedding section — status + pause/resume (existing embed routes), per F5 spec.
- Collection Analysis section — per-URL bulk + collection-scoped synthesis,
  reusing the compose plumbing.

**Tests** — vitest for rule list + template CRUD interactions.

**Exit:** all five F5 Intel sections present and wired.

---

## Phase 4 — Consolidation (remove the fragmented paths)

The net-LOC-reduction phase.

- `views/right/AnalysisTab.svelte` — narrow to inspect-only: show analyses for
  the current target, re-run, delete, open-in-detail. Remove any compose UI.
- `components/modals/QueueAnalysisModal.svelte` — becomes a thin wrapper that
  opens Intel compose pre-populated (or is removed if every caller can call the
  helper directly). Keep one entry semantics.
- `views/right/cluster/QnATab.svelte` — rewrite to route a cluster Q&A through
  the shared compose flow targeting `cluster_analyses` (D1). Delete the bespoke
  batch+poll path.
- Remove duplicate analyzer dispatch logic across the (now ≤1) compose paths.

**Tests** — update/trim vitest for the rewritten cluster Q&A + narrowed
right-pane tab.

**Exit:** exactly one compose path; right-pane inspect-only; cluster Q&A visually
matches every other analysis.

---

## Phase 5 — Verify + docs

- Confirm `views/bottom/ActivityTab.svelte` filters `kind = analysis` for the
  analyses view (item 6 already removed the standalone tab).
- Reconcile expected net LOC reduction (spec: 300–600 LOC down).
- Update reference docs: `features.md` (Intel sub-tab now built; right-pane
  Analysis narrowed; left-pane completion), `backend-structure.md` (new route +
  db modules), `data-model.md` (new tables + `prompt_id` columns,
  `SCHEMA_VERSION 5`), `frontend-structure.md` (Intel views + stores/api),
  `architecture.md` if the analysis dispatch story changed.
- Full suite green; write `outcome.md` and archive on close.

---

## Risks / watch points

- **Migration safety** — v4 → v5 must be additive only; the migration test is a
  hard gate (item 6 was a deliberate DB-delete cutover; this is explicitly not).
- **Single compose path** — the funnel only pays off if QueueAnalysisModal and
  cluster QnATab both genuinely route through the helper. Don't leave a second
  `createAnalysesBatch` caller behind (Phase 4 grep check).
- **Cluster fingerprint drift** — verify re-clustering re-attaches on matching
  fingerprint and orphans (not deletes) on changed membership.
- **Auto-analysis loops** — the crawl-complete hook must not re-enqueue excluded
  pages or already-analyzed pages (respect the existing exclude + skip-existing).
