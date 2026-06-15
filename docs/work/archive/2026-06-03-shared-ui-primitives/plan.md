# Plan — Shared UI Primitives

Frontend only. Tiered extraction so tier 1 stabilizes before tier 2
expands. Tier 3 stays deferred unless real callers converge in-flight.
Net LOC roughly flat — savings come from local-style dedup
(~1,794 lines today across 7 verified surfaces).

## 1. Primitives module layout

- `frontend/src/lib/ui/StatusBadge.svelte`
- `frontend/src/lib/ui/EmptyState.svelte`
- `frontend/src/lib/ui/IconButton.svelte`
- `frontend/src/lib/ui/TextButton.svelte`
- `frontend/src/lib/ui/PaneTabs.svelte`
- `frontend/src/lib/ui/ActionBar.svelte`
- `frontend/src/lib/ui/index.ts` — barrel for `$lib/ui` imports.

Visual tokens stay on `CLAUDE.md`'s palette (`--bg`, `--text`, `--border`,
`--accent`, `--muted`); primitives don't introduce new tokens.

## 2. Tier 1 — extract first

### StatusBadge

- Variants: `pending` · `running` · `done` · `failed` · `cancelled` ·
  `warning`. Optional pulsing dot for `running` (already used in
  AnalysisTab).
- Replace inline pill markup in `AnalysisTab.svelte`, `LiveCrawlTab.svelte`,
  `AnalysesTab.svelte`, `MonitorsTab.svelte`, `ScheduledCrawlsTab.svelte`,
  `CrawlQueuePanel.svelte`.
- Vitest: status → variant mapping + render snapshots (small).

### EmptyState

- Props: `title`, optional `body`, optional `icon`, optional `action`
  slot.
- Replace ad-hoc "No selection" / "No data" blocks in `RightPanel`,
  bottom-pane sub-tabs, `AnalysisTab`, `DomainTab`, `PageTab`.

### IconButton

- Required `label` → `aria-label` + tooltip (`title`).
- Sizes: default (24px) and small (20px) — match the existing
  `views/right/ActionBar.svelte` icon button.
- States: hover (accent), focus-visible ring, disabled (perceivable, not
  just opacity), `aria-pressed` when used as a toggle.
- Replace inline icon buttons across the seven primary surfaces.
- Vitest: ARIA label set, disabled blocks click, keyboard focus path.

## 3. Tier 2 — once tier 1 lands

### TextButton

- Variants: `primary` (accent bg) · `secondary` (outline) · `ghost`
  (transparent + accent text). Sizes: default · small. Optional leading
  icon.
- Replace text buttons in `CrawlControls`, `BulkImport`, modals
  (`AddMonitorModal`, `QueueAnalysisModal`, `CollectionPickerModal`).

### PaneTabs

- Props: `tabs: { id, label }[]`, `active: string`, `onSelect(id)`,
  optional `aria-label`.
- Implements `role="tablist"` + `role="tab"` + arrow-key navigation
  (ArrowLeft / ArrowRight wrap; Home / End jump).
- Consumers: `RightPanel.svelte` (Page / Domain / Analysis), the
  cluster workspace strip (Nodes / Q&A / Common), and `BottomPane`'s
  bottom (per-group) tab strip. The top group strip in `BottomPane`
  stays bespoke for now — it's a two-level nav with different
  semantics; revisit only if a third consumer of the two-level pattern
  appears.

### ActionBar

- Container component: flex strip with a primary action group on the
  left, a `More` overflow slot on the right.
- `views/right/ActionBar.svelte` becomes the first consumer — slot its
  buttons into `<lib/ui/ActionBar>` and let the primitive own padding,
  border, focus order.
- Action buttons inside become `<IconButton>` / `<TextButton>`.

## 4. Action helpers

Extend `$lib/contextMenu/actions.ts`:

- Define a uniform `Selection` shape: `{ nodes: GraphNode[], urls:
  string[] }` derived from the caller's context.
- Lift verb helpers to the new signature:
  - `sendToCrawl(targets, options?)`
  - `addToCollection(targets, collectionId)`
  - `flag(targets, flagSpec)` / `removeFlag(targets)`
  - `queueAnalysis(targets, analysisSpec)`
  - `copyUrls(targets)`
  - `removeFromCollection(targets, collectionId)`
  - `hide(targets)` / `unhide(targets)`
  - `markReviewed(targets, state)`
- Keep the current single-node helpers as thin wrappers during the
  migration to avoid a 7-file churn in one commit; remove the wrappers
  once every caller uses the `targets` form.
- All toasts route through `toastStore`; all errors surface through a
  single `explainError` helper (already in `PageTab.svelte`; move to
  `$lib/api/errors.ts`).
- Vitest covers each helper's target shaping + error path.

## 5. Adoption order

Land primitives behind the new module first, then convert callers in
this order so each step is verifiable:

1. `views/right/ActionBar.svelte` — already a single consumer; cheapest
   first adopter.
2. `views/right/PageTab.svelte`, `DomainTab.svelte`, `AnalysisTab.svelte`
   — tier-1 badges + empty states.
3. `views/BottomPane.svelte` + sub-tabs — `PaneTabs` adoption + tier-1
   badges in `Analyses`, `LiveCrawl`, `Monitors`, `ScheduledCrawls`.
4. `components/crawl/CrawlControls.svelte`, `CrawlQueuePanel.svelte` —
   `TextButton`, `IconButton`, `StatusBadge` for queue rows.
5. Secondary list rows (Domains, Flags, Collections, Bookmarks, Hidden)
   — only what tier 1/2 covers; do not chase tier 3.

## 6. Accessibility audit (rolled into adoption)

- Focus ring consistent across all interactive primitives
  (`--accent` outline, 2px, 2px offset).
- `IconButton.label` required; lint or runtime warning on omission.
- Tab focus order verified by keyboard walk on each converted pane.
- Disabled states perceivable beyond opacity (cursor + ARIA).

## 7. Verify

- `npm run build` clean; TS strict; no new `any`.
- Vitest: per-primitive specs + action-helper specs; CI green.
- Browser smoke per adoption step: keyboard nav on `PaneTabs`,
  tooltip + `aria-label` on `IconButton`, identical hover / focus /
  disabled across panes, no regressions on the right-pane ActionBar
  shipped in the previous package.
