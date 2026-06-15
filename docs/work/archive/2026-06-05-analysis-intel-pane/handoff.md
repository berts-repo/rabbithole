# Handoff — Analysis / Intel Pane

## Where to start

Read `README.md` → `decisions.md` → `plan.md` → `checklist.md`. **Phases 1–2
are done** (2026-06-08); begin **Phase 3 — Remaining Intel sections** in
`plan.md` (Auto-analysis Rules, Prompt Templates, Embedding, Collection
Analysis). See the "Phase 2 scope notes" in `checklist.md` first — `autoRules.ts`
+ the prompt-template picker were intentionally sequenced into Phase 3 so they
ship with their consumers (and, for templates, the worker change that makes a
selected template `body` actually drive the analysis). The package is grounded against `main`; the "What the code survey
changed vs. the spec" section in `README.md` lists the spec items already
delivered by item 6 — don't redo them.

## Current state

**Phases 1–2 complete.** Backend green (709 passed, lint-security OK); frontend
green (svelte-check 0 errors, vitest 392 passed, build emits single bundle).

Phase 2 frontend surface (what Phase 3 builds on):
- `views/left/IntelTab.svelte` (collapsible section shell, wired into
  `LeftSidebar`) with two sections: `intel/WorkerControls.svelte` and
  `intel/ComposeForm.svelte`.
- `lib/stores/intelCompose.svelte.ts` (staged target + localStorage collapse)
  over the rune/DOM-free `lib/stores/intelComposeTarget.ts` (vitest'd).
- API: `lib/api/llm.ts`, `lib/api/prompts.ts`, `analyses.ts` cluster+collection.
- `queueAnalysis` in `lib/contextMenu/actions.ts` is the real funnel (stages a
  target + switches to the Intel tab).

Phase 1 backend surface Phase 2 built on:

- Tables (`SCHEMA_VERSION 5`, additive v4→v5 migration): `prompt_templates`,
  `auto_analysis_rules`, `cluster_analyses`; nullable `prompt_id` on the three
  analysis tables.
- DB modules: `db/prompt_templates.py`, `db/auto_rules.py`, cluster helpers in
  `db/llm.py` (incl. `compute_fingerprint`).
- Routes: `/api/prompts`, `/api/auto-analysis-rules`, cluster routes +
  `/api/llm/status` load block in `routes/llm.py`.
- Collection-add auto-analysis trigger wired in `routes/collections.py`.
- `llm.batch_size` setting (1–50) for worker concurrency.
- Tests: `tests/test_intel_*.py` (5 files) + the v4→v5 migration hard gate.

The 2026-06-05 groundwork commit landed the implementation but missed its exit
gate (no tests, 5 broken tests, an unwired hook, an unregistered setting); the
2026-06-08 pass reconciled all of it — see `checklist.md` "Closed-out notes".

## Key seams to reuse (don't reinvent)

- **Typed analyses tables + job linking** — `db/llm.py` already links
  `analyses` / `collection_analyses` rows to a `jobs` row for status. Mirror
  that for `cluster_analyses`.
- **Worker control routes** — `routes/llm.py` already has start/stop/pause/
  resume/status. Extend, don't duplicate.
- **Shared action helper** — `lib/contextMenu/actions.ts` `queueAnalysis` is the
  single funnel; every compose caller goes through it. It's a stub today.
- **Left-pane nav** — `LeftSidebar.svelte` + `navigation.svelte.ts` already
  expose the `intel` tab; replace the placeholder body.
- **Activity tab** — `views/bottom/ActivityTab.svelte` is the monitor surface
  (item 6); analyses appear there filtered by `kind = analysis`.

## Hard gates

- Migration is **additive only** (v4 → v5). No DB delete. Migration test is a
  blocker.
- End every phase green: `make` lint-security + backend pytest + frontend
  check/test/build.
- Delegate test runs to the `test-runner` subagent (global rule).

## Open threads

None blocking. The deferred items in `decisions.md` are intentionally out of
scope and tracked there (cross-project prompts, label/score auto-rule
predicates → item 11, per-analyzer worker pool).
