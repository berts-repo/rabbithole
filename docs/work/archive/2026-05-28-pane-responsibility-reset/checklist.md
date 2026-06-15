# Checklist — Pane Responsibility Reset

## Stores
- [x] `workspace.svelte.ts`: `scheduled_crawls` + `monitors` BottomTab ids
- [x] `workspace.svelte.ts`: `BottomGroup`, `groupOf(tab)`, `bottomGroup` getter
- [x] `workspace.svelte.ts`: persist + restore `bottomTab`
- [x] `navigation.svelte.ts`: persist + restore `leftTab`
- [x] `bottomPanePreset.svelte.ts`: `send()` selects the target tab's group
      (via `setBottom` → `lastTabPerGroup[groupOf(tab)] = tab`)
- [x] `app.svelte`: bootstrap loads navigation persistence

## Bottom tabs
- [x] `views/bottom/ScheduledCrawlsTab.svelte` (relocated, widened form)
- [x] `views/bottom/MonitorsTab.svelte` (global list, row actions, AddMonitorModal)
- [x] delete `components/crawl/ScheduledCrawls.svelte`

## BottomPane
- [x] Work / Catalog / Sets two-level nav
- [x] new tabs rendered; group switch works

## Left pane
- [x] `CrawlSidebar.svelte` drops ScheduledCrawls

## Right pane
- [x] `views/right/ActionBar.svelte` with Send to Crawl / Add to collection / Flag / Queue Analysis / More
- [x] hosted in `RightPanel.svelte`; action set varies Page vs Domain
- [x] `PageTab.svelte` standalone Send-to-Crawl folded into the bar

## Verify
- [x] `npm run build` clean (TS strict)
- [x] tests for `groupOf` + group-aware `send` (`lib/stores/bottomGroups.test.ts`)
- [x] vitest suite green (test-runner subagent) — 175 tests / 23 files
- [x] browser check: left tab slimmed, grouped bottom nav, recipe tabs work,
      reload restores tabs, DomainTab view-all jumps + selects group, action bar fires
