# Outcome — Shared UI Primitives

Closed: 2026-06-03

Second post-F6 cleanup package (item 2). Frontend only — no schema, no
backend routes. Built in an isolated worktree in parallel with GraphCanvas
Decomposition (item 3); merged to `main` after integrated build + test
passed across both packages.

## What shipped

### Primitives module (`lib/ui/`)

- `lib/ui/index.ts` barrel for `$lib/ui` imports.
- **Tier 1** — `StatusBadge.svelte` (9 variants: pending / running / done /
  failed / cancelled / warning / waiting / skipped / queued, pulsing dot for
  running), `EmptyState.svelte` (title / body / icon / action snippet / error
  mode), `IconButton.svelte` (required `label` → `aria-label` + `title`,
  focus ring, disabled, pressed/toggle, sizes, variants).
- **Tier 2** — `TextButton.svelte` (primary / secondary / ghost, sizes,
  optional icon snippet), `PaneTabs.svelte` (`role="tablist"` / `role="tab"`
  + ArrowLeft/ArrowRight/Home/End roving navigation), `ActionBar.svelte`
  (primary + overflow named snippet slots).
- Each primitive ships a vitest file.

### Adoption

- `StatusBadge` adopted in `AnalysisTab`, `AnalysesTab`, `CrawlQueuePanel`.
- `EmptyState` adopted in `RightPanel`, `AnalysisTab`, `DomainTab`, `PageTab`,
  `LiveCrawlTab`, `MonitorsTab`, `ScheduledCrawlsTab`, `CrawlQueuePanel`.
- `IconButton` adopted across the 7 verified surfaces.
- `PaneTabs` adopted in `RightPanel.svelte` (normal + cluster strips) and
  `BottomPane.svelte` (per-group sub-strip).
- `views/right/ActionBar.svelte` migrated to consume `lib/ui/ActionBar`.
- `TextButton` adopted in `CrawlControls.svelte`, `BulkImport.svelte`, and
  the shared `modals/Modal.svelte` (covering `AddMonitorModal`,
  `QueueAnalysisModal`, `CollectionPickerModal` — all delegate footer buttons
  to `Modal.svelte`).

### Action-helper layer (`lib/contextMenu/actions.ts`)

- Uniform `Selection = { nodes: GraphNode[], urls: string[] }` shape.
- Verbs lifted to a `(targets, …)` signature: `sendToCrawl`,
  `addToCollection`, `flag` / `removeFlag`, `queueAnalysis`, `copyUrls`,
  `removeFromCollection`, `hide`, `markReviewed`, `setAnalysisExcluded`.
- Single-node wrappers kept during migration. Toasts route through
  `toastStore`; errors through `explainError`, which moved from
  `PageTab.svelte` to `$lib/api/errors.ts`.
- Vitest covers `explainError`, selection builders, shape invariants,
  filtering, and routing.

## Verification

- `npm run build` clean (TS strict, no new `any`) on the merged tree.
- `vitest` green on the integrated tree: 37 files / 342 tests (combined with
  item 3). The primitives + action-helper specs land here.
- Browser smoke pass: deferred to the post-merge check shared with item 3.

## Deferred / not done

- **Tier 3 primitives** (`OverflowMenu`, `DangerButton`, `SectionHeader`,
  `DataRow`) — deferred per the spec's "do not compulsively extract every
  pattern." A real third consumer (Unified Activity, Settings Modal,
  Analysis/Intel Pane) drives each one when it appears.
- **Stop button in `CrawlControls`** stays a native danger-styled button —
  there is no `TextButton` danger variant, and `DangerButton` is tier 3. A
  ghost/secondary swap would have dropped the danger-red signal on a live
  crawl, so it was intentionally left native. First real `DangerButton`
  consumer absorbs it.
- No Storybook playground (own package; optional per the spec).

## What this unlocks

- **Item 4 — NodeSet Workspaces** uses the "Open as graph tab" affordance
  pattern and the shared primitives.
- **Items 6–8** (Unified Activity tab, Analysis/Intel Pane, Settings Modal)
  introduce new UI that should consume these primitives from day one and
  drive the tier-3 extractions.
