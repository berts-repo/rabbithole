# Shared UI Primitives

Second post-F6 cleanup package. Frontend only — no schema, no backend
routes. Centralizes the buttons, badges, empty states, sub-tab strips,
and action helpers that every pane currently reinvents.

Closed package. Prefer [`outcome.md`](outcome.md) for what shipped.

## Goal

Make the app feel designed rather than assembled. Two layers of sharing,
both required:

1. **Visual primitives** — Svelte components that own sizing, spacing,
   states, focus, and ARIA so every pane gets the same hover / focus /
   disabled / keyboard behavior.
2. **Action helpers** — TypeScript functions in
   `$lib/contextMenu/actions.ts` (already partially there) that every
   surface — buttons, context menus, keyboard shortcuts, the right-pane
   ActionBar — invokes. One verb, one code path, regardless of trigger.

Net LOC: flat or slightly down. The deliverable is consistency,
accessibility, and uniform behavior across panes — not size reduction.

## Scope of this package

Tiered extraction so we can shake out tier 1 before expanding:

### Tier 1 — first

- `StatusBadge` — status pills (`pending` / `running` / `done` /
  `failed` / `cancelled` / `warning`).
- `EmptyState` — empty list / no selection / no data placeholder.
- `IconButton` — icon-only buttons with required `label` (→ `aria-label`
  + tooltip), consistent sizing, hover, focus, disabled.

### Tier 2 — after tier 1 stabilizes

- `TextButton` — primary / secondary / ghost variants.
- `PaneTabs` — the local tab strip used by `RightPanel.svelte`,
  `BottomPane.svelte`, and any pane with sub-tabs. Implements
  `role="tablist"` + arrow-key navigation once for the whole app.
- `ActionBar` — generalized container for the right-pane action bar
  (`views/right/ActionBar.svelte` shipped in the previous package
  becomes the first consumer).

### Tier 3 — judgment call, only if variants converge

- `OverflowMenu` — `…` menu shared by rows and action bars.
- `DangerButton` — destructive-action styling (delete, kill switch).
- `SectionHeader` — collapsible section headers inside panes.
- `DataRow` — row layout shared by Domains / Flags / Collections /
  Analyses lists.

### Action-helper layer

Extend `$lib/contextMenu/actions.ts` so every surface flows through
one helper per verb:

- `sendToCrawl(targets, options)`
- `addToCollection(targets, collectionId)`
- `flag(targets, flagSpec)` / `removeFlag(targets)`
- `queueAnalysis(targets, analysisSpec)`
- `copyUrls(targets)`
- `removeFromCollection(targets, collectionId)`
- `hide(targets)` / `unhide(targets)`
- `markReviewed(targets, state)`

Uniform `Selection` shape for `targets` regardless of source (single
node, multi-select, cluster, list row). Toast/notification through one
channel. `Promise<void>` return with consistent error handling.

## Carve-outs (decisions for this package)

1. **Tier 3 stays deferred.** Spec is explicit: "Do not compulsively
   extract every pattern." We extract tier 3 only if real callers
   converge during the tier 1/2 pass; otherwise it stays out and the
   next consumer (Unified Activity, Settings Modal, Analysis/Intel
   Pane) drives the extraction when there's a third real consumer.
2. **No Storybook playground.** The in-app surfaces are the visual
   spec. A playground is its own package and the deferred-decisions
   section in the source spec calls it out as optional.
3. **GraphCanvas internal styling untouched.** This package does not
   reach into `GraphCanvas.svelte` — that's item 3 (parallel package).

## Affected surfaces (verified scope)

7 primary files, 6,785 LOC total, 1,794 local style lines:

- `frontend/src/views/RightPanel.svelte`
- `frontend/src/views/BottomPane.svelte`
- `frontend/src/views/right/PageTab.svelte`
- `frontend/src/views/right/DomainTab.svelte`
- `frontend/src/views/right/AnalysisTab.svelte`
- `frontend/src/components/crawl/CrawlControls.svelte`
- `frontend/src/components/crawl/CrawlQueuePanel.svelte`

Plus secondary surfaces that adopt tier 1 as it stabilizes (collection
rows, domain rows, flag rows, hidden rows, bookmark rows).

## Read order

1. [`outcome.md`](outcome.md)
2. [`plan.md`](plan.md), [`checklist.md`](checklist.md)
3. `docs/reference/frontend-structure.md`

## Relationship to the queue

- Depends on the now-archived Pane Responsibility Reset
  ([`../../archive/2026-05-28-pane-responsibility-reset/outcome.md`](../../archive/2026-05-28-pane-responsibility-reset/outcome.md))
  — extract from stable pane structure, not in-flux pane structure.
- Runs in parallel with **GraphCanvas Decomposition** (item 3) —
  different code, no conflict.
- Precondition for the unified Activity tab (item 6, bundled into
  Schema Reset), Analysis/Intel Pane (item 7), and Settings Modal
  (item 8) — all introduce new UI that should use the primitives
  from day one.
