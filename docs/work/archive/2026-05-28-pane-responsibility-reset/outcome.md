# Outcome — Pane Responsibility Reset

Closed: 2026-06-03

First post-F6 cleanup package. Frontend only — no schema, no backend
routes (the backend changes are settings-key enum validators for the
two new persisted preferences). Establishes the four-pane mental model
and action taxonomy that the rest of the post-F6 queue depends on.

## What shipped

### Bottom pane — Work / Catalog / Sets grouping

- New pure module `lib/stores/bottomGroups.ts` owns the grouping data
  and helpers (`groupOf`, `firstTabOf`, `tabForGroup`, `isBottomTab`)
  so vitest can exercise the LRU logic without a Svelte-runes runtime.
  `workspace.svelte.ts` re-exports the public names.
- `BottomPane.svelte` renders two rows: top group strip (Work / Catalog
  / Sets), bottom tab strip for the active group's tabs. Group click
  calls `workspaceStore.selectGroup(group)` which returns the analyst
  to their last tab in that group, or the group's first tab if they
  haven't visited it yet (`lastTabPerGroup` map).
- Groups: **Work** = `live_crawl` · `analyses` · `scheduled_crawls` ·
  `monitors`; **Catalog** = `domains` · `flags` · `fingerprints` ·
  `hidden`; **Sets** = `collection` · `bookmarks`.

### Recipe tabs relocated / added

- `views/bottom/ScheduledCrawlsTab.svelte` — moved out of
  `components/crawl/ScheduledCrawls.svelte` (deleted) and widened for
  the bottom pane's horizontal space.
- `views/bottom/MonitorsTab.svelte` — new global monitor list using
  `listMonitors()` (no host). Row actions: pause/resume
  (`patchMonitor`), delete (`deleteMonitor`). Toolbar `+ Add Monitor`
  opens the existing `AddMonitorModal`.
- `AddMonitorModal.svelte` — URL field is now editable (`bind:value`)
  with an `untrack`'d seed from the `url` prop, so the global Monitors
  tab can create monitors without a preset host. Empty URL disables
  Save.

### Left pane slimmed

- `components/CrawlSidebar.svelte` drops the `<ScheduledCrawls>`
  section. The Crawl sub-tab is now CrawlControls + BatchConfirmStrip
  + CrawlQueuePanel + BulkImport. `CrawlQueuePanel` and
  `BatchConfirmStrip` stay in the left sidebar per the carve-out in
  the package README — the Schema Reset Milestone absorbs the durable
  queue into the unified Activity tab in one step.

### Right-pane action bar

- `views/right/ActionBar.svelte` — one consistent strip above the
  Page / Domain / Analysis tabs in single-selection mode (skipped in
  cluster mode for v1). Primary buttons: **Crawl**, **Collection**,
  **Flag** (toggles via `actFlag` / `actRemoveFlag`), **Analyze**.
  **More** dropdown: Copy URL, Open in Tor Browser (disabled when Tor
  not armed), Mark Reviewed / Unreviewed, Save as Seed Bookmark, Hide
  from Graph; on the Domain tab the dropdown adds **Add Monitor…**.
- Builds its action target with the `queueTarget()` pattern — prefer
  the live `graphStore.payload` node; fall back to lazily-fetched
  `NodeRow` synthesized into a `GraphNode` for nodes outside the
  current payload. A versioned `fetchGen` counter guards against slow
  earlier loads clobbering newer ones.
- `PageTab.svelte` loses its standalone stub `Send to Crawl` button —
  folded into the bar.

### Sub-tab persistence

- `lib/stores/workspace.svelte.ts` persists `workspace.bottomTab`;
  restored in `load()`, fire-and-forget on `setBottom`.
- `lib/stores/navigation.svelte.ts` persists `nav.leftTab` (new
  `load()` + `putSetting` on `setLeft`), restored at bootstrap.
- `app.svelte` adds `navigationStore.load()` alongside the existing
  `workspaceStore.load()`.
- `backend/db/settings.py` — new enum validators for `workspace.bottomTab`
  (the ten valid bottom tabs) and `nav.leftTab` (`search` · `intel` ·
  `crawl`). Covered by parametrized accept tests and a reject-junk
  test in `test_b4_settings.py`.

## Verification

- `npm run build` clean; TS strict.
- `vitest` green — 175 tests / 23 files, including new
  `bottomGroups.test.ts` coverage of `groupOf` and group-aware
  `setBottom` / `selectGroup` (LRU pick).
- Backend `pytest` green; enum validators covered.
- Browser smoke pass (2026-06-03): left tab slimmed, grouped bottom
  nav switches groups and remembers last tab per group, recipe tabs
  work, reload restores both `nav.leftTab` and `workspace.bottomTab`,
  DomainTab view-all jumps to the right bottom tab and selects its
  group, right-pane action bar fires on Page and Domain tabs and the
  Domain-only **Add Monitor…** appears.

## Deferred / not done

- Cluster-mode action bar — out of scope for v1; the cluster
  workspace already has its own action surface and the consistency
  win there is smaller. Revisit alongside the Shared UI Primitives
  `ActionBar` extraction (next package).
- `CrawlQueuePanel` / `BatchConfirmStrip` relocation — explicit
  carve-out. Stays in the left sidebar until the Schema Reset
  Milestone (NEXT item 6) absorbs the durable crawl queue into the
  unified Activity tab; that lets the move happen in one
  user-visible step rather than two.
- Standalone Tier-2 `ActionBar` primitive — the right-pane action bar
  exists as a single concrete component; Shared UI Primitives (NEXT
  item 2) generalizes it.

## Schema version on disk

`schema_version = 2` (no schema work this package).

## What this unlocks

- **Item 2 — Shared UI Primitives** (now active). The ActionBar
  shipped here is the prototype the primitives package generalizes;
  building it once cleanly informs the `IconButton`, `TextButton`,
  `ActionBar`, and `OverflowMenu` extractions.
- **Item 3 — GraphCanvas Decomposition** is now also unblocked and
  runnable in parallel.
- Items 4–8 in `NEXT.md` all assumed the four-pane mental model and
  action taxonomy from this package as their starting point.
