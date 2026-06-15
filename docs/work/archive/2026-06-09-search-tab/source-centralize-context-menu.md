# Handoff — Centralize the right-click context menu (Graph + Bottom + Search)

> Continuation prompt. Everything needed to execute is here — no re-exploration
> required. Status: **planned, not started.** Plan mirror:
> `~/.claude/plans/virtual-greeting-tiger.md`.

## The ask (owner's words)

> "we did the search engine, but it's lacking an open in tor button. I liked the
> right-click menu in the node graph — could we centralize the code and use a
> system that works on both? we want to copy, open in tor, start crawl, start
> analysis, add to collection, and so on."

Plus: keep it like the node graph as much as possible to **reuse code**.

## Owner decisions (confirmed via AskUserQuestion)

1. **Search rows keep ONE inline button** — crawled → `→ Graph`, uncrawled →
   `Send to Crawl`. Everything else (Copy, Open in Tor, Add to Collection, Queue
   Analysis, Flag, …) moves into the shared right-click menu.
2. **No bespoke right-pane search-detail view.** Reuse the graph pattern: a
   crawled result already drives the right pane through its node; an uncrawled
   result becomes a stub node on first action and inherits the right pane like
   any graph stub. (Enriched multi-engine provenance was discussed as a separate
   future package — not in scope.)

## Architecture already in place (reuse, don't rebuild)

The menu **shape + actions are already centralized** in
`frontend/src/lib/contextMenu/`:

- `sections.ts` — pure builders: `buildSingleTargetSections(target, ctx,
  handlers)` and `buildMultiSelectSections(...)` → `MenuSection[]`.
  `SingleTargetMenuHandlers` lists every handler the single menu needs.
- `actions.ts` — implementations: `actOpenInTor(nodeId)`, `actCopyUrl(url)`,
  `actQueueCrawl(url)`, `actFlag(nodeId, prio)`, `actRemoveFlag`,
  `actToggleReviewed`, `actSaveSeedBookmark`, `actHideFromGraph`,
  `queueAnalysis(Selection)`, `queueAnalysisIds(ids)`, `addToCollection`,
  `selectionFromNode`, etc.
- `ContextMenu.svelte` — the renderer (keyboard nav, edge-flip, sections/items).
- `index.ts` — re-exports the section builders + types.

**Two consumers today:**

- **Graph** — `lib/graph/controllers/contextMenuAdapter.ts`
  (`createContextMenuAdapter(deps)` → `singleNodeHandlers` / `multiSelectHandlers`)
  + a `ContextMenu` mount in `components/graph/GraphCanvas.svelte`
  (adapter created at `GraphCanvas.svelte:256`, deps incl. `openCollectionModal`
  at `:262`; menu rendered at `:471`/`:474`). Canvas coords, single+multi+edge.
- **Bottom pane** — `views/bottom/bottomPaneMenu.svelte.ts` (singleton store
  `bottomPaneMenu` with `open`/`openAt(target,event)`/`close`/`current`, target
  type `BottomPaneMenuTarget = { url, node?, inCollection?,
  onRemoveFromCollection? }`) + `views/bottom/BottomPaneContextMenu.svelte`
  (single-mount renderer, mounted at `views/BottomPane.svelte:39`). It owns the
  handler factory (`makeHandlers`) and the Rename / Monitor modal mounts. No-node
  rows currently **toast** "needs a crawled page" for id-bound actions.

The bottom-pane store+renderer is effectively a **surface-neutral row menu**
stuck under `views/bottom/`. Promote it to shared infra and point the Search tab
at it — exactly how every bottom sub-tab already uses it.

## Key API / type facts

- **Open in Tor requires a node id**: `openNodeInBrowser(id)` →
  `POST /nodes/{id}/open` (`lib/api/nodes.ts:47`). No URL-based variant. So
  uncrawled URLs need a stub node first.
- `createStubNode({ url })` → `{ id, url }` (`lib/api/nodes.ts:18`). The
  search-tab spec already uses this for "+ Collection" and "Flag".
- `SearchResult` (`lib/stores/searchHarvestModel.ts:8`): `{ url, engineLabel,
  crawled, anchorText, nodeId, title, category, lastSeen, description, probed }`.
  Note only the **first** engine that surfaced a URL is kept (`engineLabel`) —
  no multi-engine provenance (that's the deferred "enriched" idea).
- `graphStore.payload` holds the loaded `GraphNode[]`; bottom sub-tabs look up a
  node by id there to build their menu target. Search crawled rows hold a real
  `nodeId` but the node may not be in the current payload → target must carry
  `nodeId` so id-bound actions still work.
- `GraphNode` interface: `lib/api/types.ts:299` (fields used by the menu:
  `id, raw_url, domain, alias, flag_status, reviewed, state`).

## Implementation steps

### 1. Promote the row menu to `$lib/contextMenu/`
- Move `views/bottom/bottomPaneMenu.svelte.ts` → `lib/contextMenu/rowMenu.svelte.ts`.
  Rename export `bottomPaneMenu` → `rowContextMenu`, `BottomPaneMenuTarget` →
  `RowMenuTarget`. Add `nodeId?: number` to the target:
  ```ts
  export interface RowMenuTarget {
    url: string;
    node?: GraphNode;                 // full node when in graph payload
    nodeId?: number;                  // known id even if full node not loaded
    inCollection?: boolean;
    onRemoveFromCollection?: () => void | Promise<void>;
  }
  ```
  Keep the store API identical (one menu open app-wide).
- Move `views/bottom/BottomPaneContextMenu.svelte` →
  `lib/contextMenu/RowContextMenu.svelte`. Generalize its `makeHandlers`:
  - Add `async function ensureNodeId(t): Promise<number | null>` returning
    `t.node?.id ?? t.nodeId ?? (await createStubNode({ url: t.url })).id`; on
    stub creation `void graphPoller.refresh()`. Every id-bound handler
    (openInTor, flag, removeFlag, toggleReviewed, queueAnalysis, focus,
    addToCollection) awaits it instead of `nodeMissingToast(...)`. (Upgrades
    bottom-pane Bookmark rows for free; matches the search-tab spec.)
  - Add `addToCollection` handler → open a new `CollectionPickerModal` mount with
    `[id]` (add `kind: 'collection'` to the local `ActiveModal` union + the
    `{#if}` mount, import from `components/modals/CollectionPickerModal.svelte`).
  - Section gating still uses `target.node ?? { domain: null }`.
- Mount `<RowContextMenu />` **once in `views/AppShell.svelte`** (near the other
  global overlays — Toast/KillSwitchAlert ~lines 105-107). Remove the mount +
  import from `views/BottomPane.svelte` (line 9 import, line 39 mount).
- Repoint importers (rename symbol): `views/bottom/DomainsTab.svelte`,
  `BookmarksTab.svelte`, `CollectionTab.svelte`, `FingerprintsTab.svelte`,
  `FlagsTab.svelte`, `FindResultsTab.svelte` — each imports `bottomPaneMenu`
  (and maybe `BottomPaneMenuTarget`) from `./bottomPaneMenu.svelte`.

### 2. Single-target "Add to Collection" (`lib/contextMenu/sections.ts`)
- Add `addToCollection: () => void` to `SingleTargetMenuHandlers` (~line 74).
- Add a `Collection` item in `buildSingleTargetSections` (a new item; the
  existing collection-scoped `Remove from Collection` stays gated on
  `ctx.inCollection`). Decide placement — suggest top group near Copy, or a
  dedicated `Collection` section.
- Update `sections.test.ts` (expects the item + that handler fires).

### 3. Graph adapter (`lib/graph/controllers/contextMenuAdapter.ts`)
- In `singleNodeHandlers` (~line 85) add
  `addToCollection: () => deps.openCollectionModal([node])`. `openCollectionModal`
  dep already exists + is already passed from GraphCanvas — no GraphCanvas edit
  needed beyond a compile check.

### 4. Search tab (`views/SearchTab.svelte`)
- Add `oncontextmenu={(e) => onRowContextMenu(r, e)}` to each `.result` `<li>`
  (~line 197). `onRowContextMenu(r, e)`:
  - crawled: look up node in `graphStore.payload` by `r.nodeId`; target
    `{ url: r.url, node: found, nodeId: r.nodeId }`.
  - uncrawled: `{ url: r.url }`.
  - `rowContextMenu.openAt(target, e)`.
- Keep ONE inline button: crawled → `→ Graph` (`toGraph`), uncrawled →
  `Send to Crawl` (`sendToCrawl`). Remove the other inline `TextButton`s.
- Delete now-dead code: `crawledCollection`, `crawledAnalysis`,
  `uncrawledCollection`, `uncrawledFlag`, the `CollectionPickerModal` mount, and
  `collectionTargetIds` state. Keep `toGraph`, `sendToCrawl`, `onRowClick`
  highlight behavior. Drop unused imports (`createFlag`, `createStubNode`,
  `queueAnalysisIds`, etc.) once they move into the shared handler factory.

## Verify
- `cd frontend && npm run check` (0/0) ; `npx vitest run` (sections/actions
  green incl. new Add-to-Collection) ; `npm run build` (single bundle).
- Manual (`run` skill): graph node right-click shows Add to Collection; a
  bottom-pane Bookmark row's Open-in-Tor now works (stub-backed); Search tab
  crawled row → full menu incl. Open in Tor (Tor-gated), uncrawled row →
  Open in Tor / Add to Collection / Flag / Queue Analysis each create a stub then
  act; the single inline button remains.

## Docs to update on completion
- `docs/specs/search-tab.md` — action-bar section → "one inline button + shared
  right-click menu (incl. Open in Tor)".
- `docs/work/archive/2026-06-09-search-tab/checklist.md` — note the menu
  centralization + Open-in-Tor close.

## Notes / gotchas
- `RowContextMenu` uses a fixed-overlay (`position: fixed; inset: 0;
  pointer-events: none` with `.menu { pointer-events: auto }`) — safe to mount at
  AppShell; x/y are viewport coords from `event.clientX/Y`.
- Stub creation is **on-demand only** (triggered by an action) — never
  auto-create a stub for every search result; that would pollute the graph.
- CLAUDE.md selection model: search row *click* stays highlight-only; the menu is
  the action surface. Don't change click semantics.
