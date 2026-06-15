# Analysis / Intel Pane (item 7)

Promoted from `NEXT.md` item 7 on 2026-06-05, the day item 6 (Schema Reset)
closed. This package builds the left-pane **Intel** sub-tab and consolidates
the five fragmented analysis entry points into one compose / monitor / inspect
pattern.

## Source docs

- Historical source spec: [`source-spec.md`](source-spec.md)
- F5 intent spec: [`../../../specs/explore-left-pane-intel.md`](../../../specs/explore-left-pane-intel.md)
- Depends on item 6 outcome: [`../../archive/2026-06-04-schema-reset/outcome.md`](../../archive/2026-06-04-schema-reset/outcome.md)

## Read order

1. `source-spec.md` (the package source spec)
2. `decisions.md` (scope calls D1–D3 + internal defaults, this package)
3. `plan.md` (phased implementation)
4. `checklist.md` (live status)
5. Task Read Order for backend + frontend work in root `CONTEXT.md`

## Goal in one line

Make analysis a coherent workflow with clear pane ownership: **left** composes
and controls, **bottom Activity** monitors, **right** inspects the current
selection only — replacing the right-pane compose, the Queue Analysis modal,
the cluster Q&A path, and the (never-built) left Intel tab with a single
compose form.

## What the code survey changed vs. the spec

The spec predates item 6. Verified against current `main`:

- **Bottom-pane Analyses tab is already gone** — absorbed into
  `views/bottom/ActivityTab.svelte` by item 6. This package only confirms
  Activity filters `kind = analysis`; it does not remove a standalone tab.
- **Worker-control routes already exist** — `/api/llm/start`, `/stop`,
  `/pause`, `/resume`, `/status` in `routes/llm.py`. This package *exposes*
  them in Intel and adds a load/capacity surface; it does not build them.
- **Intel tab scaffold already exists** — `views/LeftSidebar.svelte` has the
  `intel` tab and `lib/stores/navigation.svelte.ts` has `LeftTab`; the body is
  a placeholder today. We fill the body, not the nav.
- **`analyses` / `collection_analyses` exist post-reset** with `status` on the
  linked `jobs` row and target FK on `resources(id)`. Neither has `prompt_id`.
- **The shared `queueAnalysis` helper is a stub** (`lib/contextMenu/actions.ts`)
  that only toasts. `QueueAnalysisModal` and cluster `QnATab` both call
  `createAnalysesBatch` directly — these are the compose paths we consolidate.

## Closes

The **Intel sub-tab** component of legacy F5. After this lands, F5's Intel
piece is complete (Search sub-tab is item 9; Settings modal is item 8).
