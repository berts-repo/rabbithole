# Shared UI Primitives

## Status

Implementation-ready feature spec. Second post-F6 cleanup package. Frontend
only — no schema work. Builds on `pane-responsibility-reset.md`.

Supersedes: the "Shared Components" and "Button Cleanup" sections of the
previous `additions/pane-action-cleanup.md`.

## Goal

Stop every pane from inventing its own buttons, badges, empty states, tabs,
and row affordances. Centralize repeated patterns into shared Svelte primitives
and shared action helpers, so the app feels designed rather than assembled.

The win is consistency and accessibility, not raw LOC reduction. Primitives
add code (each is its own component) while removing duplication, so net
savings are modest (~200–500 LOC). The real deliverable is uniform behavior,
focus management, and ARIA across every pane.

## Two Layers of Sharing

1. **Visual primitives** — Svelte components that centralize sizing, spacing,
   states, and styling.
2. **Action helpers** — TypeScript functions that buttons, context menus, and
   keyboard shortcuts all call. So `Send to Crawl` behaves identically
   regardless of trigger.

Both layers are required. Visual-only sharing leaves behavioral inconsistency
(buttons that look the same but fire slightly different code paths). Action
helpers without shared visuals leaves each surface drawing its own button
chrome.

## Visual Primitives

Extract in tiers — do tier 1 first, shake out, then expand.

### Tier 1 — highest dedup, lowest risk

- `StatusBadge` — status pills with all variants (pending/running/done/failed/
  cancelled/warning).
- `EmptyState` — empty list / no selection / no data placeholders.
- `IconButton` — icon-only buttons with consistent sizing, hover, focus,
  disabled, tooltip.

### Tier 2 — once tier 1 is stable

- `TextButton` — text-label buttons including primary/secondary/ghost variants.
- `PaneTabs` — the local tab strip used by `RightPanel.svelte`, `BottomPane.svelte`,
  and any pane with sub-tabs.
- `ActionBar` — the right-pane action bar container from
  `pane-responsibility-reset.md`.

### Tier 3 — judgment call, extract only if variants converge

- `OverflowMenu` — `…` menu shared by rows and action bars.
- `DangerButton` — destructive-action styling (delete, kill switch).
- `SectionHeader` — collapsible section headers inside panes.
- `DataRow` — row layout shared by Domains, Flags, Collections, Analyses lists.

Do not compulsively extract every pattern. Three similar inline blocks is
better than a premature abstraction. Stop tier 3 the moment variants stop
converging.

## Action Helpers

`$lib/contextMenu/actions.ts` already exists as the basis for shared command
behavior. Extend this pattern so every command — regardless of where it's
triggered — flows through the same helper:

- `sendToCrawl(targets, options)`
- `addToCollection(targets, collectionId)`
- `flag(targets, flagSpec)`
- `queueAnalysis(targets, analysisSpec)`
- `copyUrls(targets)`
- `removeFromCollection(targets, collectionId)`
- `hide(targets)` / `unhide(targets)`
- `markReviewed(targets, state)`

Callers — `IconButton`, `TextButton`, `OverflowMenu`, the right-pane
`ActionBar`, the graph context menu, keyboard shortcut handlers — all invoke
the same function. No surface re-implements the command.

Helpers must:

- Accept `targets` as a uniform shape (`Selection`) regardless of source
  (single node, multi-select, cluster, list selection).
- Handle progress/feedback through a single toast/notification channel.
- Return `Promise<void>` with consistent error handling.

## Accessibility

Bake accessibility into the primitives once, get it everywhere:

- Focus ring style/width is identical across all interactive primitives.
- `IconButton` has a required `label` prop that becomes `aria-label` and
  tooltip.
- `PaneTabs` implements arrow-key navigation and `role="tablist"`.
- `OverflowMenu` is keyboard-navigable with Escape-to-close.
- Disabled states are perceivable (not just visually grayed).

This is the most efficient accessibility upgrade available — one extraction
pass levels up the whole app simultaneously.

## Affected Surfaces

Verified scope (7 files, 6,785 LOC total, 1,794 local style lines):

- `frontend/src/views/RightPanel.svelte`
- `frontend/src/views/BottomPane.svelte`
- `frontend/src/views/right/PageTab.svelte`
- `frontend/src/views/right/DomainTab.svelte`
- `frontend/src/views/right/AnalysisTab.svelte`
- `frontend/src/components/crawl/CrawlControls.svelte`
- `frontend/src/components/crawl/CrawlQueuePanel.svelte`

Plus secondary surfaces that pick up primitives as tier 1 stabilizes
(collection rows, domain rows, flag rows, hidden rows).

## Code Size Expectation

Net LOC: roughly flat or slightly down. CSS deduplication in local style
blocks (~1,794 lines today) is the main source of removal — probably 400–700
lines saved there. Each primitive adds 50–100 lines × 5–7 primitives. Net:
modest negative.

Frame the deliverable as **the app feels designed and accessible**, not as
size reduction.

## User-Visible Changes

Subtle but pervasive:

- Identical hover/focus/disabled states across every pane.
- Consistent badge sizing and color across status indicators.
- Consistent empty-state typography and iconography.
- Same keyboard navigation patterns across tabs, menus, and overflow buttons.
- Improved screen-reader behavior throughout (currently inconsistent).

## Relationship to Other Work

- Depends on `pane-responsibility-reset.md` (extract from stable pane
  structure, not in-flux pane structure).
- Runs in parallel with `graphcanvas-decomposition.md` (different code; no
  conflict).
- Precondition for `unified-activity-view.md` (the new bottom-pane Activity
  tab should be built on the primitives from day one).
- Precondition for `analysis-intel-pane.md` and `settings-modal.md` (both
  build new UI that should use the primitives).

## Deferred Decisions

- Whether to extract any of the tier 3 primitives in the first pass or wait
  for tier 1/2 to settle.
- Whether `OverflowMenu` and the existing graph context menu share
  implementation or remain separate (similar visuals, different positioning
  models).
- Whether to introduce a Storybook-style component playground for primitives
  or rely on in-app usage as the visual spec.
