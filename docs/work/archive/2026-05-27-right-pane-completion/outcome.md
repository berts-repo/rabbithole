# Outcome — Right Pane Completion (F6)

Closed: 2026-05-27

The shell's right-side detail panel is no longer a stub. The three
single-node tabs (Page, Domain, Analysis) plus the multi-select cluster
workspace (Nodes, Q&A, Common) all ship from this package, with no
schema work and no new backend endpoints (the few additive fields —
`body_text_preview` on `get_node`, `id` on `list_pages` rows — sit on
existing routes).

## What shipped

### Shell

- `RightPanel.svelte` body replaced with a per-tab component slot,
  routing on `navigationStore.rightTab` and the new selection mode.
- Auto-expand on every new full-selection unless the user collapsed
  the panel themselves this session
  (`layoutStore.userCollapsedRightThisSession` +
  `expandRightForSelection()`).
- No-selection placeholders per tab — no API calls fire when
  `selectedNodeId` is `null`.

### Phase 1 — Page tab (`views/right/PageTab.svelte`)

- Parallel fetch of node detail, collections, and notes on every
  `selectedNodeId` change, guarded by a versioned `fetchGen` counter
  so a slow earlier load can't clobber a newer one.
- Header: URL, alias + ✎ pencil (reuses `RenameAliasPopover.svelte`),
  title, meta chips, Reviewed + Exclude toggles (immediate `PATCH`),
  summary block.
- Collections: pills with ✕ (immediate remove); `+ Add` opens a
  lazy-loaded picker (cached in component state); already-joined
  collections show ✓ and are unselectable. New helper
  `listNodeCollections` (`api/collections.ts`).
- Flag section (only when `flag` is non-null): Status select (folds
  `flagged` into `pending` for display), Priority select, note
  textarea (save on blur), Remove flag. New helper `patchFlag`
  (`api/flags.ts`).
- Details toggle starts expanded on every node load. Expanded block:
  - Content preview (~500 chars; backend `get_node` now derives
    `body_text_preview`).
  - Entities: header `Entities (N)`; click/right-click opens the
    shared `ContextMenu` with type-aware actions (Onion URL: Send to
    Search / Send to Crawl / Copy; Handle: Send to Search / Copy;
    Email/BTC/XMR/PGP/blob: Copy). Builder lives in
    `views/right/entityMenu.ts`; covered by `entityMenu.test.ts`.
    New action `actSendToSearch` + `searchPendingStore` stages
    the value for the F5-owned Search sidebar.
  - Response headers `<details>` (open by default).
  - Version history `<details>` (open by default); `get_node` now
    joins `page_versions`.
  - Notes: list with ✕ delete, textarea + `Save note` (disabled on
    blank trim). New `api/notes.ts`.
- Stub-node branch: URL + amber `not crawled` badge, collection
  pills, flag section if flagged, notes, prominent `Send to Crawl`
  that reuses `actQueueCrawl` to switch the left pane to Crawl and
  load the URL into the manual single-URL input. **Closes the
  durable-crawl-queue Phase B deferred single-node stub
  `Send to Crawl`.**

### Phase 2 — Domain tab (`views/right/DomainTab.svelte`)

- Scoped to the loaded node's `domain`; fetches node detail, profile,
  pages, entities, and monitors in parallel with a `fetchGen` guard.
- Profile card: four chips (Pages / Flags / Entities / Uptime — `Up`
  teal at HTTP 200, numeric red otherwise, `–` when no monitor).
- Activity sparkline — SVG polyline + dots with `YYYY-MM-DD: N
  page(s)` tooltips; single-day → text label; empty → "No dated
  pages". Layout math in `$lib/sparkline.ts`, covered by
  `sparkline.test.ts` (empty / single / multi / all-zero
  divide-by-zero guard).
- Entity-type chips row.
- Pages list — up to 200 rows; row click is
  `selectionStore.highlight(p.id)`; over-cap link switches the
  bottom pane to Domains pre-filtered for this host via
  `bottomPanePresetStore.send('domains', host)`.
- Entities list — shared `ContextMenu` per type via
  `buildEntityMenu`; below it `View fingerprint clusters →` switches
  the bottom pane to Fingerprints pre-filtered for this host.
- Uptime monitors — list rows with ⏸/▶ enable toggle and ✕ remove;
  add-monitor form (URL pre-filled from the selected node + label +
  interval; collapsible Alert settings). New API helpers
  `listMonitors(host?)`, `patchMonitor`, `deleteMonitor` +
  `UpdateMonitorBody`.
- Stub-node branch: monitors fully functional; profile / pages /
  entities hidden behind a "Not yet crawled." notice.

### Phase 3 — Analysis tab (`views/right/AnalysisTab.svelte`)

- Reloads on every node change via the same
  `selectionStore.selectedNodeId` `$effect` pattern as Page / Domain.
- Analyses list: type + status badge (`done` teal / `pending` amber /
  `running` teal + pulsing dot / `waiting` muted amber with
  `Waiting — crawl this URL first.` tooltip), model line, Re-run on
  `done` rows, ✕ delete.
- Result pane: meta line (type · model · status), Q&A question line
  (italic grey) when present, monospace body, status placeholders.
- Result rendering gated on `status === 'done' && result`;
  pending / running / waiting rows show the placeholder without an
  API call. Backend `list_queue` returns `result` inline.
- Stub-node branch: same Queue Analysis button + amber "Jobs will
  run when this URL is crawled." notice. Waiting rows show their
  wait tooltip.
- Polling: 5 s `setInterval` while any row is `pending` or `running`;
  stops as soon as the work settles (`shouldPoll` helper). Cleaned
  up in `onDestroy`.
- Queue Analysis: reuses `QueueAnalysisModal`. Looks up a live
  `GraphNode` from `graphStore.payload` and falls back to a
  constructed shape from `NodeRow` when the node isn't currently in
  the graph view. Modal close triggers a refresh.
- API: new `deleteAnalysis`, `rerunAnalysis` helpers in
  `api/analyses.ts`.

### Phase 4 — Cluster workspace (`views/right/cluster/`)

- **Three-mode selection** in `selection.svelte.ts`: `full` /
  `highlight` / `cluster`. `replaceCluster(...)`, `toggleCluster(id)`,
  and `deselect(id)` are the cluster-mode primitives; mode derives
  from selection size (`>= 2` → `cluster`, `1` → `highlight`,
  `0` → `full` + null focus). The cluster workspace gates on
  `selectMode === 'cluster'`, **not** raw `multiCount` — so the
  bottom-pane Domains row click (`replaceMulti`) still highlights
  without tripping the workspace. **Resolves the F7 Phase 3
  follow-up note.**
- Graph multi-select (Ctrl/Cmd-click, Shift-click, Ctrl+A) calls
  `replaceCluster(...)` from `GraphCanvas.svelte`. Dropping below
  2 selected snaps the panel back to single-node view; Escape and
  empty-canvas click return to single-node.
- **Nodes tab** (default) — per-row URL display, amber `not crawled`
  badge on stubs, ✕ removes that node from the selection. Actions:
  Add to collection (picker), Save as new collection (name-input
  popover, creates and adds every selected node including stubs),
  Send to Crawl (stages every URL in `BatchConfirmStrip`, regardless
  of stub state). **Closes the cluster batch `Send to Crawl`
  deferred from F7.**
- **Q&A tab** — single textarea + `Ask all`. Queues Q&A jobs per
  crawled node via `POST /api/analyses/batch`, skips stubs, respects
  the same skip-already-queued logic as `QueueAnalysisModal`. Notice
  when stubs are excluded; button disabled with "No crawled nodes in
  selection." notice on all-stub selections. Results render inline
  per node as they complete; polls every 5 s while any selected job
  is pending or running. Per-node results also visible from the
  bottom-pane Analyses sub-tab and the single-node Analysis tab.
- **Common tab** — single fetch on tab open via
  `GET /api/entities/common?node_ids=…` (crawled only); ⟳ refresh
  button. Rows grouped by type: type chip · value (mono) · "seen on
  N / M nodes". Click / right-click → shared `ContextMenu` per type.
  Stubs-in-selection notice when applicable; empty state "No shared
  entities across selected nodes." New helper `commonEntities` in
  `api/entities.ts`.

## Verification

- `npm run check` clean across all four phases.
- `npm run test` — 162 passed at phase 3; phase 4 added cluster-mode
  coverage on top.
- Backend `pytest` clean: `get_node` (`body_text_preview`) and
  `list_pages` (`id`) extensions are additive; existing tests still
  pass.
- `features.md` updated per phase.

## Deferred / not done

- **Browser exercise (SwiftShader Edge) deferred per phase.** Vitest
  covers the pure helpers (entity menu mapping, sparkline math,
  analysis status / placeholder / poll predicate). The remaining
  surface checks — auto-expand, alias rename round-trip, collection
  picker, flag editor, notes, stub `Send to Crawl`, monitors
  add / pause / resume / remove, cluster trip from graph
  multi-select, no cluster trip from Domains row click, batch
  `Send to Crawl`, `Ask all` queues only crawled, Common tab
  shows entities seen on ≥ 2 selected nodes, selection drop to 1
  snaps back, Escape clears — will be exercised in normal use as
  the post-F6 queue moves forward.
- **Right-click context menu on Domain-tab Pages list.** Spec lists
  it but the pages-list response doesn't carry a `GraphNode`-shaped
  target the shared `ContextMenu` needs. Captured as a small
  follow-up; the cluster Nodes-tab pattern (build target from row
  id) is the model.

## Schema version on disk

`schema_version = 2` (no schema work this package).

## What this unlocks

- **Item 1 — Pane Responsibility Reset** is now the next active
  package per `NEXT.md`. F6 finished the right pane's *content*;
  item 1 finishes the right pane's *role* (right-pane action bar)
  and moves CrawlQueuePanel / ScheduledCrawls / BatchConfirmStrip
  from the left sidebar to the bottom pane.
- F5 is no longer a single package — `NEXT.md` items 7 (Intel
  sub-tab), 8 (Settings modal), and 9 (Search sub-tab) cover its
  three components.
