# Checklist — Shared UI Primitives

## Module scaffolding
- [ ] `lib/ui/index.ts` barrel
- [ ] move `explainError` from `PageTab.svelte` to `$lib/api/errors.ts`

## Tier 1
- [ ] `lib/ui/StatusBadge.svelte` + vitest
- [ ] `lib/ui/EmptyState.svelte` + vitest
- [ ] `lib/ui/IconButton.svelte` + vitest (ARIA + disabled + keyboard)
- [ ] adopt `StatusBadge` in `AnalysisTab`, `AnalysesTab`,
      `LiveCrawlTab`, `MonitorsTab`, `ScheduledCrawlsTab`,
      `CrawlQueuePanel`
- [ ] adopt `EmptyState` in `RightPanel`, bottom-pane sub-tabs,
      `AnalysisTab`, `DomainTab`, `PageTab`
- [ ] adopt `IconButton` across the 7 verified surfaces

## Tier 2
- [ ] `lib/ui/TextButton.svelte` + vitest
- [ ] `lib/ui/PaneTabs.svelte` + vitest (arrow-key nav, `role="tablist"`)
- [ ] `lib/ui/ActionBar.svelte` + vitest (slot layout)
- [ ] adopt `TextButton` in `CrawlControls`, `BulkImport`,
      `AddMonitorModal`, `QueueAnalysisModal`, `CollectionPickerModal`
- [ ] adopt `PaneTabs` in `RightPanel` + cluster workspace strip +
      `BottomPane` per-group strip
- [ ] migrate `views/right/ActionBar.svelte` to consume
      `lib/ui/ActionBar.svelte`

## Action helpers
- [ ] define `Selection = { nodes: GraphNode[], urls: string[] }`
- [ ] lift verbs to `(targets, …)` signature in
      `$lib/contextMenu/actions.ts`:
      `sendToCrawl`, `addToCollection`, `flag`, `removeFlag`,
      `queueAnalysis`, `copyUrls`, `removeFromCollection`, `hide`,
      `unhide`, `markReviewed`
- [ ] keep single-node wrappers during migration; delete once unused
- [ ] route all toasts through `toastStore`; all errors through
      `explainError`
- [ ] vitest per verb (target shaping + error path)

## Accessibility audit
- [ ] focus ring style identical across all primitives
- [ ] `IconButton.label` required; warn on omission
- [ ] keyboard walk on each converted pane (no traps, logical order)
- [ ] disabled states perceivable beyond opacity

## Verify
- [ ] `npm run build` clean (TS strict, no new `any`)
- [ ] `vitest` green via test-runner subagent
- [ ] browser check: keyboard nav on tabs, tooltips on icon buttons,
      consistent hover/focus/disabled across panes, no regressions on
      right-pane ActionBar
