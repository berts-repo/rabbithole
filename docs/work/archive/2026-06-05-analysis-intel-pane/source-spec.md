# Analysis / Intel Pane

## Status

Implementation-ready feature completion. Frontend-heavy with light backend
glue (compose endpoint, worker-control endpoints, the new
`cluster_analyses` table if Cluster Q&A is in scope). Storage stays in the
existing typed analyses tables (`analyses`, `collection_analyses`); item 7
does not require — and the schema reset does not deliver — a polymorphic
analyses table.

Builds on:
- `schema-reset.md` (unified status vocabulary on `analyses` /
  `collection_analyses`; `analyses.resource_id` migrated to the new
  `resources` table)
- `pane-responsibility-reset.md` (left-pane composes work)
- `shared-ui-primitives.md` (compose form, action helpers)
- `unified-activity-view.md` (bottom-pane Activity absorbs the global queue)

This package implements the Intel sub-tab from the F5 spec
(`docs/specs/explore-left-pane-intel.md`). When this lands, the corresponding
F5 component is complete.

## Goal

Make analysis a coherent workflow with clear pane ownership:

- **Left pane Intel** — compose analysis jobs, control workers, configure
  auto-analysis rules.
- **Bottom pane Activity** — monitor global analysis queue and history (from
  `unified-activity-view.md`).
- **Right pane Analysis tab** — inspect results for the currently selected
  target only.

Replaces five fragmented entry points (right-pane tab, bottom-pane Analyses,
Queue Analysis modal, Cluster Q&A, the not-yet-built left-pane Intel) with
one compose/monitor/inspect pattern.

## Left-Pane Intel Sub-Tab

The new home for everything "I want to run an analysis."

### Compose Section

A single form that handles every kind of analysis target:

- **Target picker** — current selection, current collection, current cluster,
  current graph scope, or specific node ids.
- **Analyzer picker** — model (LLM choice) + prompt template.
- **Scope options** — for collection/cluster: whether to analyze items
  individually, as a synthesis, or both.
- **Run / queue button** — fires through the shared `queueAnalysis` action
  helper (`shared-ui-primitives.md`).

### Worker Controls

- Worker on / off toggle (already in backend; not yet exposed).
- Concurrency / capacity controls.
- Current worker load indicator (jobs in flight, queue depth).
- Pause / resume queue.

### Auto-Analysis Rules

- "Auto-analyze newly crawled pages with analyzer X" toggle.
- "Auto-analyze pages added to collection Y with analyzer Z" rule list.
- Backend wiring exists for some of this; UI completes it.

### Prompt Templates

- List of available analyzer prompts.
- Create / edit / clone / delete custom prompts.
- Built-in presets that can be hidden but not deleted.

## Right-Pane Analysis Tab — Narrowed

After this package lands, the right-pane Analysis tab does **only**:

- Show analyses targeting the currently selected node / domain / cluster.
- Re-run a specific analysis on the current target.
- Delete an analysis from the current target's history.
- Open a specific analysis result in detail.

It does **not**:

- Compose new analyses for arbitrary targets (that's Intel).
- Show global analysis history (that's Activity).
- Manage workers (that's Intel).

## Bottom-Pane Analyses Tab — Absorbed

The current bottom-pane Analyses tab is replaced by the unified Activity tab
filtered to `kind = analysis`. The standalone Analyses tab is removed.

## Queue Analysis Modal — Funnel into Intel

The existing Queue Analysis modal (triggered from graph context menu,
right-click, bottom-pane context surfaces) becomes a thin wrapper that opens
the left-pane Intel compose section pre-populated with the target. No
separate compose UI in the modal.

## Cluster Q&A — Funnel into Intel

Cluster Q&A becomes "an analysis you run against a cluster target, with a
Q&A prompt." Same compose flow, same result viewer, no bespoke Cluster Q&A
code path. Storage lands in a typed `cluster_analyses` table added as part
of this package (mirrors `analyses` / `collection_analyses` in shape).

**Cluster id stability.** Graph clusters are recomputed by layout /
algorithm runs, so a numeric cluster id is not a stable FK target. The
`cluster_analyses` row therefore stores a **cluster fingerprint** — the
sorted set of member `resource_id`s hashed into a stable key — plus a
denormalized `label` snapshot the analyst saw at compose time. Re-running
clustering may produce a cluster with the same fingerprint (analysis
re-attaches automatically) or a different membership (the old analysis
becomes orphaned history, still queryable by id, no longer surfaced on a
live cluster). This is the simplest model that respects "clusters drift,
analyses don't."

## Affected Surfaces

New:

- `frontend/src/views/left/IntelTab.svelte` (or sub-tab if left pane
  is sub-tabbed)
- `frontend/src/views/left/intel/ComposeForm.svelte`
- `frontend/src/views/left/intel/WorkerControls.svelte`
- `frontend/src/views/left/intel/AutoAnalysisRules.svelte`
- `frontend/src/views/left/intel/PromptTemplates.svelte`

Modified:

- `frontend/src/views/right/AnalysisTab.svelte` — narrow scope
- `frontend/src/components/modals/QueueAnalysisModal.svelte` — thin wrapper or removed
- Cluster Q&A components — fold into shared compose

Removed:

- `frontend/src/views/bottom/AnalysesTab.svelte` (absorbed)
- Cluster Q&A bespoke handlers
- Duplicate analyzer dispatch logic in 2–3 places

Backend (light, since schema-reset did the heavy lifting):

- New: worker-control endpoints (pause/resume/capacity).
- New: `prompt_templates` table + module + routes (typed table; preset
  prompts seeded with `builtin=1`). `analyses.prompt_id` /
  `collection_analyses.prompt_id` / `cluster_analyses.prompt_id` are
  added here as nullable FKs (nullable so ad-hoc free-form prompts —
  the only mode today — still work).
- New: `auto_analysis_rules` table + module + routes (typed table:
  trigger kind, target filter JSON, prompt_id FK, enabled flag).
- New: `cluster_analyses` table + module + routes (only if Cluster Q&A is
  in scope for this package).

Schema lands as an **additive, non-destructive migration** on top of the
post-reset schema — no DB delete. The schema reset (item 6) deliberately
does not bundle these tables since they're scoped to item 7 and would
inflate the cutover.

## Code Size Expectation

Modest net reduction (300–600 LOC) once compose flows consolidate and the
bottom Analyses tab is removed. The new Intel UI adds substantial code, but
collapsing five entry points into one removes more than it adds.

## User-Visible Changes

- Left-pane Intel exists for the first time. The gear-icon-like missing piece
  is filled in.
- One compose form for every kind of analysis — no more "where do I queue this
  from?" decisions.
- Bottom-pane Analyses tab disappears; analyses appear in Activity instead.
- Right-pane Analysis tab gets simpler — only shows the current selection's
  results.
- Cluster Q&A still works but visually matches every other analysis.

## Relationship to Other Work

- Requires `schema-reset.md` for the unified status vocabulary, the
  resource/page split (analyses' target FK migrates to `resources(id)`),
  and the Activity tab in the bottom pane. Item 6 keeps the typed
  `analyses` / `collection_analyses` tables and adds `cluster_analyses`
  if Cluster Q&A is in scope.
- Requires `pane-responsibility-reset.md` for left/right/bottom roles.
- Uses `shared-ui-primitives.md` for compose form, action helpers, status
  badges.
- `unified-activity-view.md` (delivered inside the schema reset milestone)
  absorbs the global analysis queue/history — this package assumes Activity
  is already filtering by `kind = analysis`.
- Completes the **Intel sub-tab** component of F5 from the legacy NEXT.md.

## Deferred Decisions

- Whether prompt templates are project-local or shareable across projects.
- Whether auto-analysis rules support more complex predicates (filters,
  labels, score thresholds) in v1 or stay simple in v1.
- Whether "synthesize this collection" is a separate analyzer kind or a flag
  on collection-targeted analyses.
- Worker capacity UI fidelity — single number or per-analyzer pool.
