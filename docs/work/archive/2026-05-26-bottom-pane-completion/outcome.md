# Outcome — Bottom Pane Completion (F7)

Closed: 2026-05-27

## What shipped

### Shared infrastructure

- `frontend/src/lib/contextMenu/` — surface-neutral context-menu module.
  `sections.ts` owns the `MenuTarget` shape and the two section builders
  (`buildSingleTargetSections`, `buildMultiSelectSections`). `MenuTarget`'s
  minimum fields (`stub`, `flag_status`, `reviewed`, `domain`) are
  structurally compatible with `GraphNode`, so the graph adapter passes
  nodes directly with no conversion. `ContextMenu.svelte` (renamed from
  `NodeContextMenu.svelte`) is the single renderer used by every surface.
  `actions.ts` holds the shared `act*` functions so graph, bottom pane,
  and future right-pane / search row menus call the same toasts /
  graph-poller refreshes / payload-cache invalidations. Covered by
  `sections.test.ts`.
- `frontend/src/views/bottom/BottomPaneRow.svelte` — reusable row with
  ●/○ visibility button (controlled `visible` + `onToggleVisibility`),
  content-button snippet, click-to-full-select wiring, active-row marker,
  and dimmed rendering when hidden.
- `frontend/src/views/bottom/bottomPaneMenu.svelte.ts` +
  `BottomPaneContextMenu.svelte` — bottom-pane right-click adapter.
  Store-backed, mounted once in `BottomPane.svelte`, renders the shared
  `ContextMenu` in a fixed overlay so the menu escapes
  `.body`'s `overflow: auto`. URL-only items always work; id-bound items
  (Open in Tor, Flag, Mark Reviewed, Focus, Queue Analysis) require the
  row to resolve to a `GraphNode` and short-circuit with a readable
  toast otherwise.

### Eight sub-tabs (`frontend/src/views/bottom/`)

- **`BookmarksTab`** — `seedBookmarksStore`-driven; filter + count badge,
  Add Bookmark, ▶ Send to Crawl, inline rename (Enter saves / Escape
  cancels) backed by new `PATCH /api/seeds` + `update_seed_label` DB
  helper, ✕ delete. Per-host ●/○ via new `domainVisibilityStore`
  (client-side, ephemeral). Duplicate-URL toast matches CrawlControls
  phrasing.
- **`CollectionTab`** — workspace-driven via `activeCollectionId()`;
  header with rename / export (JSON / Nodes CSV / GEXF) / delete; filter +
  count badge; `Send to Crawl (all uncrawled)` stages every stub into
  `BatchConfirmStrip` with `collectionId` pre-pinned (new
  `defaultsOverride` arg on `batchConfirmStore.stage()`); stubs render
  an amber `not crawled` badge; rename/delete propagate to the workspace
  tab via new `workspaceStore.renameTab()` / existing `closeTab`.
- **`LiveCrawlTab`** — `crawlLogStore` ref-counts the `/api/crawl/log`
  SSE; 200-line cap mirrors the backend ring buffer. `liveCrawl.ts`
  parses status code, onion URL, and severity per line; rows with a
  matching `GraphNode` full-select on click.
- **`AnalysesTab`** — `listAnalyses` polling on `setInterval(5000)` with
  stale-fetch versioning. Status filter folds `waiting` into `pending`;
  type filter is client-side over the 500-row fetch cap. Row click drives
  `selectionStore.fullSelect(node_id)` + right-panel `analysis` route.
- **`DomainsTab`** — `listDomains`; row click calls
  `selectionStore.replaceMulti(host node ids)` for highlight + dim and
  `navigationStore.setRight('domain')` for the panel anchor. Host nodes
  ordered by `first_seen ASC, id ASC` so the [0] entry is the stable
  anchor. Per-host ●/○ via `domainVisibilityStore`.
- **`FlagsTab`** — `listFlags` (joined url/title); URL filter (URL +
  title), Status dropdown (All / Pending / Investigating / Done /
  Dismissed — `flagged` folds into Pending), Priority dropdown (All /
  High / Med / Low). Row click full-selects.
- **`FingerprintsTab`** — `listFingerprints` / `listFingerprintMembers`
  / CSV export. Cluster rows expand on click, lazy-load + cache members
  keyed by `(key, value)`; per-cluster member filter; ⟳ wipes both the
  cluster list and every member cache. Member visibility uses the new
  per-node path
  `domainVisibilityStore.toggleNode` / `isNodeHidden`.
  `GraphCanvas.computeVisibility` reads both the per-host and per-node
  keys.
- **`HiddenTab`** — `listGraphFilters` / `addGraphFilter` /
  `deleteGraphFilter`. Both mutations invalidate payload snapshots and
  refresh the graph poller. Duplicate adds collapse into an "Already
  hidden." toast on the 409 path.

### Deferred surfaces closed

- Bookmarks row `▶ Send to Crawl` (carried from durable-crawl-queue
  Phase B deferred list).
- Collection sub-tab `Send to Crawl (all uncrawled)` (same).

### Verification

- `npm run check` clean.
- `npm run test` 140 passed across 18 files (pure-helper coverage for
  every sub-tab plus the shared section builders).

## Schema version on disk

`schema_version = 2` (no schema work this package; the `PATCH /api/seeds`
addition is a route on existing tables).

## Deviations from plan

- **No `lib/graph/interactions/contextMenu.ts` file.** The plan called
  for the graph-side trigger / canvas-coord positioning / node →
  `MenuTarget` adapter to live in a sibling file under
  `lib/graph/interactions/`. On the refactor it became clear there was
  no pure helper to extract: `MenuTarget` is structurally compatible
  with `GraphNode` (no conversion adapter), and the trigger is a
  `renderer.on('rightClickNode' | 'rightClickEdge', …)` registration
  tied to Sigma renderer state plus the canvas's modal and selection
  stores. It stays inline in `GraphCanvas.svelte:1312-1354`; the shared
  `act*` actions and section builders are still in
  `$lib/contextMenu/`, so F6 / F8 still plug into the same module.
- **Per-tab "first-load done" flag not added.** Plan flagged this as
  "may add to workspace.svelte.ts if Analyses / others need it." They
  didn't — AnalysesTab handles first-load-on-switch with local component
  state and `setInterval(5000)` polling; no shared flag was useful.
- **Bookmarks rename needed a backend addition.** Plan note said "no new
  endpoints"; the spec's inline rename can't round-trip without one, so
  `PATCH /api/seeds` + `update_seed_label` shipped. Covered by
  `test_seeds_patch_label`.
- **Browser exercise deferred.** Spec called for per-phase SwiftShader
  Edge passes (add/rename/delete loops, selection-model parity, row-menu
  parity with the graph). Vitest covers the pure helpers (140 passing);
  the remaining surface checks will be exercised in F6 (right-pane row
  menus) by real use. Owner decision: archive package without this
  gate.
- **F6-shaped concern noted on Domains row click.** Spec says the
  multi-host highlight "is not a multi-select, does not trigger cluster
  workspace." Today `selectionStore.replaceMulti` already produces the
  right highlight + dim; when F6 lands, the cluster-workspace trigger
  must gate on something other than just multi-count. Captured in the
  Phase 3 checklist note.
