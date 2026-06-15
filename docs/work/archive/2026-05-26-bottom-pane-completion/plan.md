# Plan — Bottom Pane Completion (F7)

## Scope

Eight sub-tabs in the graph view's bottom pane, plus the reusable
`BottomPaneRow` component and the bottom-pane row right-click context
menu. All frontend; no schema work; no new endpoints.

Spec: `../../../specs/explore-bottom-pane.md`.

## Approach

One package, four phases on `main`. Each phase ships independently and
updates `checklist.md` as it goes. Phase 1 establishes the two reusable
pieces (`BottomPaneRow`, consolidated context menu) so later phases plug
in without renegotiating shape.

### Phase 1 — Row component + context menu + Bookmarks + Collection

Builds the reusable pieces and closes the two deferred Phase B intake
surfaces from the durable-crawl-queue work.

- `BottomPaneRow.svelte` — two-element row from the spec's "Shared row
  interaction pattern" section: a ●/○ visibility button bound to the
  per-domain graph visibility state, plus a content-button slot for the
  sub-tab's own row body. Owns the click-to-full-select wiring
  (`selectionStore` with `selectMode: 'full'`) and the active-row marker
  for the owning sub-tab.
- **Context-menu consolidation.** Move section builders out of
  `frontend/src/lib/graph/interactions/contextMenu.ts` into a neutral
  `frontend/src/lib/contextMenu/` module that takes a `MenuTarget` shape
  (node id, url, host, collection context, flag state, reviewed state,
  alias) instead of a graphology node. `NodeContextMenu.svelte` moves
  there (likely renamed `ContextMenu.svelte`) as the single renderer for
  every surface. The graph keeps its trigger / canvas-coord positioning
  adapter in `lib/graph/interactions/`; a bottom-pane adapter lives
  alongside `BottomPaneRow.svelte`. "Remove from collection" is a
  single conditional in the section builder keyed off the collection-
  context field. Designed so F6 (right-pane row menus) and F8 (search-
  result row menus) plug in without another refactor.
- `BookmarksTab.svelte` — uses `seedBookmarksStore`, `▶ Send to Crawl`
  per row (stages into existing `BatchConfirmStrip.svelte`), rename
  label inline, ✕ delete. Save-as-Seed-Bookmark from other surfaces
  lands here.
- `CollectionTab.svelte` — driven by active workspace; header has ✎
  rename, ↓ export dropdown (JSON / Nodes CSV / GEXF), 🗑 delete; `Send
  to Crawl (all uncrawled)` stages every stub into `BatchConfirmStrip`
  with the collection pre-selected.

### Phase 2 — Live Crawl + Analyses

- `LiveCrawlTab.svelte` — SSE connection to `/api/crawl/events` opened
  at mount and held for page lifetime; ring-buffer of 200 lines;
  color-coded by HTTP status; onion-URL detection makes the row clickable.
- `AnalysesTab.svelte` — loads on first switch; polls `/api/analyses?...`
  every 5 s while active; status + type filter dropdowns; full-select
  opens the right panel on the Analysis tab (the right panel itself is
  F6 work — fall back to current right-panel stub if not yet available,
  but pass the analysis id through).

### Phase 3 — Domains + Flags

- `DomainsTab.svelte` — `/api/domains`; alias-or-host display; domain
  highlight on click (highlights every node from that host, does not
  multi-select); visibility toggle hides every node from that host at
  once.
- `FlagsTab.svelte` — `/api/flags`; URL filter; status dropdown
  (All / Pending / Investigating / Done / Dismissed); priority dropdown
  (All / High / Medium / Low); full-select on row click.

### Phase 4 — Fingerprints + Hidden

- `FingerprintsTab.svelte` — `/api/fingerprints?min_sites=N`; expandable
  cluster rows that lazy-load members via `/api/fingerprints/members`;
  CSV export; manual refresh.
- `HiddenTab.svelte` — `/api/graph-filters` CRUD; add/remove terms with
  immediate graph-cache invalidation.

## Files

- `frontend/src/views/BottomPane.svelte` — replace placeholder body
  with a tab-routed component slot.
- `frontend/src/views/bottom/*` — new directory for the eight sub-tab
  components, `BottomPaneRow.svelte`, and the bottom-pane context-menu
  adapter.
- `frontend/src/lib/contextMenu/*` — new module: section builders and
  the `MenuTarget` type, lifted from
  `lib/graph/interactions/contextMenu.ts`. `NodeContextMenu.svelte`
  moves here as the shared renderer.
- `frontend/src/lib/graph/interactions/contextMenu.ts` — becomes the
  graph-side adapter only: trigger + canvas-coord positioning + node →
  `MenuTarget` conversion.
- `frontend/src/lib/api/*` — minor additions for analyses list polling,
  domains list, flags CRUD, fingerprints; most endpoints already have
  an API module.
- `frontend/src/lib/stores/workspace.svelte.ts` — already has
  `bottomTab`; may add a per-tab "first-load done" flag.

## Verification

Per phase, in `rabbithole/frontend/` with the backend running on
`:7654`:

- `npm run check` — TypeScript strict passes.
- `npm run test` — existing Vitest suites pass; each new component gets
  a smoke test plus filter / selection-model tests.
- `npm run dev` and exercise the feature in a browser via the
  SwiftShader Edge profile. Verify the selection model (row click =
  full select; graph click = highlight only; left-pane search =
  highlight only) and the right-click menu actions.
- Phase 1: verify the two deferred Send-to-Crawl surfaces by staging
  items in `BatchConfirmStrip` from both Bookmarks and a collection
  with stubs, and confirming the resulting queue rows.
