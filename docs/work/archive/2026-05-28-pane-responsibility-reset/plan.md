# Plan — Pane Responsibility Reset

Frontend-only. Net LOC roughly flat (mostly moves). Verified surface:
`CrawlSidebar.svelte`, `crawl/ScheduledCrawls.svelte`, `views/BottomPane.svelte`,
`views/RightPanel.svelte`, `views/right/{PageTab,DomainTab,AnalysisTab}.svelte`,
and the `workspace` / `navigation` / `bottomPanePreset` stores.

## 1. Stores

- `lib/stores/workspace.svelte.ts`
  - Add `BottomTab` ids `scheduled_crawls`, `monitors`.
  - Add a `BottomGroup = 'work' | 'catalog' | 'sets'` type, a `groupOf(tab)`
    lookup, and a `bottomGroup` getter derived from the active tab.
  - Persist `bottomTab` through the existing `getSetting`/`putSetting`
    settings keys (new key `workspace.bottomTab`), restored in `load()`.
- `lib/stores/navigation.svelte.ts`
  - Persist `leftTab` (new `load()` + `putSetting('nav.leftTab', …)`), restored
    at bootstrap.
- `lib/stores/bottomPanePreset.svelte.ts`
  - `send()` stays one-arg; it already calls `workspaceStore.setBottom(tab)`,
    which now also selects the tab's group via `groupOf`.
- `app.svelte` bootstrap: call `navigationStore.load()` alongside the existing
  `workspaceStore.load()`.

## 2. New bottom tabs

- `views/bottom/ScheduledCrawlsTab.svelte` — relocate
  `components/crawl/ScheduledCrawls.svelte`; widen the add-form for the bottom
  pane's horizontal space. Delete the old component after the move.
- `views/bottom/MonitorsTab.svelte` — global monitor list via
  `listMonitors()` (no host). Row actions: pause/resume (`patchMonitor`),
  delete (`deleteMonitor`). Toolbar `+ Add` opens the existing
  `components/modals/AddMonitorModal.svelte`.

## 3. BottomPane grouped nav

- `views/BottomPane.svelte`: two rows — group labels, then the active group's
  tabs. Groups:
  - Work: `live_crawl`, `analyses`, `scheduled_crawls`, `monitors`
  - Catalog: `domains`, `flags`, `fingerprints`, `hidden`
  - Sets: `collection`, `bookmarks`
- Clicking a group selects its first tab (or its last-used tab if cheap).
- Render the two new tab components.

## 4. Left pane

- Remove `<ScheduledCrawls>` from `components/CrawlSidebar.svelte`. Crawl
  sub-tab now: CrawlControls + BatchConfirmStrip + CrawlQueuePanel + BulkImport.

## 5. Right-pane action bar

- `views/right/ActionBar.svelte`, hosted at the top of `views/RightPanel.svelte`
  in the single-selection branch (skip in cluster mode for v1).
- Actions reuse helpers/modals; no new action logic:
  - Send to Crawl → `actQueueCrawl(url)`
  - Flag → `actFlag(nodeId, priority)`
  - Add to collection → `CollectionPickerModal`
  - Queue Analysis → `QueueAnalysisModal`
  - More → copy URL / open in Tor / hide / mark reviewed via `actions.ts`.
- Build the `GraphNode[]` target with the `queueTarget()` pattern from
  `views/right/AnalysisTab.svelte:178` (prefer `graphStore.payload`, fall back
  to a synthesized node from `getNode`).
- Vary action set by right tab (Page vs Domain). Fold `PageTab`'s standalone
  stub Send-to-Crawl into the bar.

## 6. Verify

`npm run build` clean; add tests for `groupOf` + group-aware `send`; run vitest
via the test-runner subagent; browser-check the shell.
