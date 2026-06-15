# F4b changes — re-apply ledger  [RE-APPLIED 2026-05-17]

> **Status:** the re-apply described below is complete. Slices 1, 2+3,
> 3.5, and 3.6 now live on branch `feat/f4b-workspace-tabs`
> (commits `510c9a8`, `1921f00`, `da3dac2`, `7f7ac82`) on top of
> `main` tip `3516fef`. The implementation diverged from the
> per-slice plan in two places worth knowing:
>
> - Slices 2 and 3 landed as a **single commit** in slice 3's final
>   shape (`workspaceSnapshots.consumePending` deferred restore).
>   The ledger itself noted slice 2's design was superseded by
>   slice 3, so the interim shape was skipped.
> - 5 slices became 4 commits. Verification target was 52 backend
>   tests across `test_b6_graph`, `test_b7_collections`,
>   `test_f3_find_active`, `test_b5c_runtime`; actual = 64 (the
>   suites had more baseline tests than the ledger assumed).
>
> This file is preserved as historical context; do NOT use it as a
> live re-apply recipe again — the commits above are now the truth.

---

Snapshot of every change shipped in this F4b sitting, in the order
they landed. Workflow this file supports: revert these commits →
pull your other-computer fixes → re-apply each slice in order using
this file as the recipe.

## Commits (newest → oldest)

| Hash | Subject |
|------|---------|
| `47d4260` | fix(rabbithole): wire crawler to targeted collection membership |
| `efaf7bf` | feat(rabbithole): wire Crawl picker to workspace tabs |
| `9b604d0` | feat(rabbithole): F4b collection-scoped graph payload |
| `3c070f5` | feat(rabbithole): F4b per-tab state snapshots |
| `5f948d1` | feat(rabbithole): F4b workspace tab bar + checklist |

`47d4260` was authored on a separate machine; included here so the
re-apply sequence is one continuous recipe. The repo has been reset
back to commit `eecd450` (this morning's tip) and force-pushed.
Only this file (`docs/work/archive/2026-05-20-f4b-toolbar-modals/changes.md`) sits on top of that tip.

---

## Slice 1 — Workspace tab bar (`5f948d1`)

**Goal:** Global + collection workspace tabs above the graph toolbar.
`+` opens a collection picker popover; `✕` closes (Global cannot
close). Active workspace id propagates to the rest of the shell.

**Files created**

- `frontend/src/components/graph/WorkspaceTabs.svelte` — 28 px bar,
  per-tab buttons (with `aria-current="page"` on active), `✕` only
  on collection tabs, trailing `+` button that toggles
  `WorkspacePicker`.
- `frontend/src/components/graph/WorkspacePicker.svelte` — anchored
  popover (top: 100%; right: 4px; z: 50). Loads collections on mount
  via `listCollections()`; calls `workspaceStore.reconcileCollections`
  for the cross-window-deletion safety net. Inline `+ New collection…`
  with a programmatic-focus input (avoids the `svelte/a11y` autofocus
  warning). Click-outside + Escape close.

**Files modified**

- `frontend/src/lib/stores/workspace.svelte.ts`
  - Added `OpenTab` interface (`id`, `kind`, `collectionId`, `label`)
    and `WorkspaceKind` type.
  - Default state seeds `openTabs: [GLOBAL_TAB]`.
  - `setWorkspace(id)` guards against orphan ids.
  - New methods: `openCollectionTab(c)` (idempotent — reactivates if
    open), `closeTab(id)` (no-op for `'global'`; falls back to
    `'global'` if active), `reconcileCollections(known)` (drops
    tabs missing from `known`, fires toast per drop, falls back
    to `'global'` if the active was dropped).
  - `tabId(collectionId)` helper = `String(collectionId)`.

- `frontend/src/views/GraphTab.svelte`
  - Imported and mounted `<WorkspaceTabs />` above `<GraphToolbar />`.

- `frontend/src/views/BottomPane.svelte`
  - Placeholder line now reads `{bottomTab} — content lands in F7
    (workspace: {activeWorkspaceId})` so propagation is visible.

**Files created (top level)**

- `docs/work/archive/2026-05-20-f4b-toolbar-modals/checklist.md` — section-by-section acceptance checklist.
  Mirrors the F4a shape. User has been editing this directly; this
  file should be considered the user's tracking file going forward.

**Design constraints to preserve when re-applying**

- Picker is an *inline popover*, not a modal. Shared modal
  extraction (`CollectionPicker.svelte` per historical build-plan backlog)
  is a later F4b slice.
- `reconcileCollections` is called on picker *open*, not on a poll —
  cheap and correct.

---

## Slice 2 — Per-tab state snapshots (`3c070f5`)

**Goal:** Switching workspace tabs preserves each tab's node
positions, selection, and ego-focus independently. **Critical
architectural rule:** one graphology instance for the page lifetime
(`graph.svelte.ts:50-56` comment) — Sigma's WebGL context never
re-mounts. Per-tab independence is achieved by mutating positions on
the single instance, not by spawning new instances.

**Files created**

- `frontend/src/lib/stores/workspaceSnapshots.svelte.ts`
  - Page-lifetime `Map<workspaceId, Snapshot>` with `version` rune
    counter the canvas observes to refresh after position restores.
  - `Snapshot` shape: `{positions: Map<string, {x,y}>,
    selectedNodeId: number|null, selectedIds: Set<number>,
    egoFocus: EgoFocus|null}`.
  - API: `capture(id)`, `restore(id)`, `initFresh()`, `drop(id)`,
    `knownIds()`, `has(id)`, `version`.

**Files modified**

- `frontend/src/lib/stores/selection.svelte.ts`
  - Added `restoreSet(ids, focusId)` — atomic setter that honours an
    exact captured focus id (`replaceMulti` would pick arbitrarily
    when current focus is null/missing).

- `frontend/src/views/GraphTab.svelte`
  - Added bridge `$effect` on `workspaceStore.activeWorkspaceId`:
    capture prev, restore next (or `initFresh` if no snapshot).
    Tracks `prevWorkspaceId` outside the effect; uses `untrack` to
    avoid re-firing on the writes it makes. First run after mount
    (when `prevWorkspaceId === null`) is a no-op.
  - Added prune `$effect` on `workspaceStore.openTabs`: drops
    snapshots for ids not in the open list. Covers `closeTab` +
    `reconcileCollections` uniformly.

- `frontend/src/components/graph/GraphCanvas.svelte`
  - Imported `workspaceSnapshots`.
  - Added one-line `$effect` on `workspaceSnapshots.version` →
    `renderer.refresh()` (selection / ego restores already trip
    their existing effects; this only covers position writes).

**Design notes to preserve**

- DO NOT refactor toward N graphology instances. The single-instance
  rule is load-bearing for Sigma WebGL stability.
- In slice 3 this design evolved — see below — `restore` moved to
  *after* `applyPayload` rebuilds the graph for the new scope.

---

## Slice 3 — Collection-scoped graph payload (`9b604d0`)

**Goal:** Collection workspace tabs actually render only that
collection's subgraph. Metrics on surviving nodes pass through from
the full graph compute (correct analytical signal). Cache stays
single-flight for the global build; post-filter is cheap on each
scoped request.

**Backend**

- `backend/backend/db/collections.py`
  - **New:** `member_ids(db, cid) -> set[int] | None` — returns
    `None` when cid is unknown (distinct from "exists but empty").
  - **New:** `filter_payload_to_members(payload, members)` — pure
    post-filter; nodes by member set, edges by both endpoints
    surviving.
  - **Refactored:** `build_export_payload` now uses both helpers.
    Surface unchanged (still returns `{collection, nodes, edges}`).
  - `__all__` updated to export the two new helpers.

- `backend/backend/routes/graph.py`
  - `GET /api/graph` grows `collection_id: int | None = None` query
    param. When provided: fetch cached full payload via existing
    `_payload`, then return
    `collections_db.filter_payload_to_members(payload, members)`.
  - Unknown `collection_id` → 404 with
    `detail={"error": "unknown_collection", "collection_id": N}`.
  - Imports `from ..db import collections as collections_db` and
    `HTTPException`.

- `backend/tests/test_b6_graph.py`
  - **5 new tests** appended (with helpers `_insert_collection`,
    `_add_member`, `_remove_member`):
    1. `test_graph_collection_filter_keeps_only_members` — member
       filter; only edges between surviving members.
    2. `test_graph_collection_metrics_pass_through_from_full_graph`
       — pagerank/is_bridge/degree counts inherit from full compute.
    3. `test_graph_collection_unknown_404` — unknown id 404 shape.
    4. `test_graph_collection_empty_membership_returns_empty` —
       existing but empty collection returns `{nodes:[], edges:[]}`.
    5. `test_graph_collection_membership_change_visible_without_invalidation`
       — add/remove members reflects on next fetch without cache
       invalidation (post-filter reads membership fresh each time).

**Frontend**

- `frontend/src/lib/api/`
  - `getGraph(collectionId?: number | null)` — sends
    `?collection_id=` when provided. Uses existing `qs()` helper
    with `collection_id: collectionId ?? undefined`.

- `frontend/src/lib/stores/workspace.svelte.ts`
  - `activeCollectionId(): number | null` — poller's signal for
    which scope to fetch.
  - `activeLabel(): string` — toolbar reads this for the scope chip.

- `frontend/src/lib/stores/workspaceSnapshots.svelte.ts`
  - Added `pendingRestoreId: string | null` (module-level let).
  - New `onSwitch(prevId, nextId)`: capture prev, set
    `pendingRestoreId = nextId`.
  - New `consumePending(): boolean`: if set, restore (or
    initFresh); clear. Returns true if a restore landed.
  - **Why deferred:** with collection scoping, switching from a
    smaller subgraph back to a bigger one means the snapshot has
    positions for nodes that don't yet exist in `graphInstance` —
    `setNodeAttribute` would silently skip them. Deferring restore
    to *after* `applyPayload` ensures the bigger graph's nodes
    exist before we write positions.

- `frontend/src/lib/pollers/graph.svelte.ts` — rewritten:
  - Read `workspaceStore.activeCollectionId()` at fetch start, pass
    to `getGraph(cid)`.
  - Capture `requestedFor = workspaceStore.activeWorkspaceId` at
    fetch start; if it changed by response time, drop result and
    set `pending = true`.
  - `inFlight` + `pending` semaphore: refresh during in-flight
    queues exactly one follow-up; multiple refresh calls collapse
    to one extra poll.
  - `refresh()` calls `poll()`.

- `frontend/src/views/GraphTab.svelte`
  - Bridge effect changed from immediate capture/restore to
    `workspaceSnapshots.onSwitch(prev, next) + graphPoller.refresh()`.
    Restore is no longer here.
  - Imports `workspaceStore` (was already there for prune effect).

- `frontend/src/components/graph/GraphCanvas.svelte`
  - Payload-version effect: after `applyPayloadAndLayout()`, calls
    `workspaceSnapshots.consumePending()`. If a restore landed,
    clears bbox lock (`setCustomBBox(null)`) and refits camera
    (`getCamera().animatedReset({duration: 200})`) — prior bbox was
    sized for the previous tab.

- `frontend/src/components/graph/GraphToolbar.svelte`
  - Imports `workspaceStore`.
  - Derived `scopeLabel` (null on Global; `activeLabel()`
    otherwise).
  - Status line renders `<span class="scope">{label}</span> · ...`
    when present.
  - `.scope` style: `color: var(--accent)`.

**Design notes to preserve**

- No per-collection backend cache slots — single-flight cache stays
  global, post-filter is cheap.
- Metrics scope = full graph deliberately (analytical signal:
  "how does this rank in the whole crawl?").
- Camera refits on tab switch; per-tab camera is out of scope until
  a later slice if needed.

---

## Slice 3.5 — Crawl ↔ workspace tab wiring (`efaf7bf`)

**Goal:** Picking a collection in the left-pane Crawl dropdown and
starting a crawl gives immediate visual feedback. Three orthogonal
pieces (all user-confirmed; spec was silent on the linkage).

**Backend**

- `backend/backend/db/crawl.py`
  - `find_active` SELECT adds `collection_id` (column already exists
    on `crawls` table per `db/core.py:192`).

- `backend/tests/test_f3_find_active.py`
  - Asserts `collection_id is None` in existing test.
  - New `test_find_active_carries_collection_id` — creates
    collection, creates crawl with `collection_id=cid`, asserts the
    field round-trips.

**Frontend**

- `frontend/src/lib/api/`
  - `CrawlActiveRow.collection_id: number | null` added.

- `frontend/src/lib/stores/workspace.svelte.ts`
  - `openCollectionTabById(id: number): Promise<void>` — if tab
    open, just activate; otherwise `listCollections()`, find the
    row, call `openCollectionTab`. Silent no-op on missing.
  - Imports `listCollections` from `$lib/api`.

- `frontend/src/components/crawl/CrawlControls.svelte`
  - Imports `untrack` from `svelte`, `workspaceStore`.
  - New `$effect` (with local `lastSuggestedId`) that defaults the
    "Add results to collection" dropdown to the active workspace's
    collection when dropdown is at `'none'`. Resets to `'none'` only
    when our own suggestion is still there — explicit user picks
    are left alone.
  - `onStart()`: after successful `startCrawl`, calls
    `workspaceStore.openCollectionTab(c)` if a collection was set.
    For the `'new'` branch, synthesises `Collection` shape
    (`{id, name, description: null}`) from the `createCollection`
    response.

- `frontend/src/components/graph/GraphToolbar.svelte`
  - Derived `targetedChip` next to `scopeLabel`. Returns
    `{collectionId, label}` only when on Global AND
    `crawlStore.polledActiveRow.collection_id` is non-null. Label
    falls back to `Collection {id}` if the tab isn't open yet
    (browser-restart edge case).
  - Renders `<button class="chip">crawling → {label}</button>`
    inside the status `<div>`. Click calls
    `workspaceStore.openCollectionTabById(id)`.
  - `.chip` style: accent-bordered pill, hover-darken, sized to
    fit the 34 px bar.

**Design notes to preserve**

- `find_active` only returns running/paused crawls — the chip
  auto-disappears when the crawl finishes.
- Dropdown-default heuristic uses `lastSuggestedId` so explicit
  picks survive workspace switches.
- Auto-open is one-way (Start → open tab); cross-window opens are
  not handled and not in scope.

---

## Slice 3.6 — Crawler honours `collection_id` (`47d4260`)

**Goal:** The Crawl dropdown's `collection_id` was stored on the
`crawls` row but the runner never used it to populate
`collection_items`. Crawled pages landed only in the global graph;
the collection workspace tab stayed empty because the collection
had no members to filter on. After this fix every successfully
recorded crawl node is added to the runner's collection via the
existing idempotent `collections.add_item`. Stubs (discovered but
not yet crawled) are NOT added — the collection holds crawl
results, not exploration candidates.

**Files modified**

- `backend/backend/crawler/runtime.py`
  - Imports `from ..db import collections as collections_db`.
  - New private method `_add_to_targeted_collection(node_id)`:
    no-op when `self.collection_id is None`; calls
    `collections_db.add_item(self.db, self.collection_id, node_id)`;
    defensively swallows `ValueError` so a deleted-mid-crawl
    collection doesn't kill the runner.
  - Called from both record paths in the crawl loop —
    `record_fetch` (success) and the non-HTML-skipped path after
    `link_crawl_node`. Each call sits right after the existing
    `link_crawl_node` so membership lands as part of the same
    "this node is a result of this crawl" beat.

- `backend/tests/test_b5c_runtime.py`
  - **3 new tests** verifying:
    1. Happy path — runner with a `collection_id` adds both
       crawled pages to that collection's items.
    2. `collection_id=None` — runner skips membership writes
       entirely.
    3. Mid-crawl collection delete — analyst deletes the targeted
       collection while the runner is mid-loop; runner keeps
       going (the `ValueError` swallow path).

**Design notes to preserve**

- `add_item` is idempotent (INSERT OR IGNORE) so a re-recorded
  page stays put.
- Graph-cache invalidation already fires after each page; once
  membership is correct, the next `/api/graph?collection_id=N`
  read returns the new pages within the standard 15 s tick. No
  extra invalidation needed.
- Stubs (uncrawled discoveries) are *not* added — collection
  semantics are "crawl results", not "exploration candidates".

**Dependency:** Conceptually depends on F4b (the user-visible
payoff is the collection-scoped graph view from slice 3 actually
populating). The fix itself only touches the runner and is
independent of F4b code paths — re-applying it without F4b would
still be a correctness improvement, just without a UI surface to
observe it.

---

## Re-apply order

1. Apply your other-computer fixes first (anything not listed here).
2. Slice 1 — pure additions; no dependency on existing F4b.
3. Slice 2 — depends on slice 1's `workspace.svelte.ts`.
4. Slice 3 — touches backend + many frontend files; depends on 1+2.
   Note slice 3 *replaces* slice 2's immediate restore with deferred
   `consumePending` — when re-applying, slice 2's bridge effect in
   `GraphTab.svelte` should land first as an interim shape then get
   rewritten in slice 3, OR you can land both directly in their
   final slice-3 shape.
5. Slice 3.5 — depends on slice 3's `activeCollectionId` helper.
6. Slice 3.6 — independent of all other slices; can land anywhere
   after F4b's `workspace.openCollectionTab` exists (slice 1) since
   its end-user value depends on the workspace tab rendering the
   collection-scoped graph (slice 3).

## Verification (each slice)

- `cd backend && .venv/bin/python -m pytest tests/test_b6_graph.py tests/test_b7_collections.py tests/test_f3_find_active.py`
- `cd frontend && npm run check` — 0 errors, 0 warnings
- `cd frontend && npm run build` — single `bundle.js` + `bundle.css`
  in `backend/public/`

At final slice (3.5) the backend should show 52 passing tests
across those three files; frontend bundle around 368 kB / 30 kB.

## Files NOT to revert (not part of F4b work)

- `docs/work/archive/2026-05-20-f4b-toolbar-modals/checklist.md` — created in slice 1 but you've been editing
  it directly. Treat as your tracking file going forward.
- `/home/guy/.claude/plans/luminous-wandering-melody.md` — local
  plan file, not in repo.

## Open at end of session (in your tree, not committed by me)

- `backend/backend/crawler/runtime.py` — your edits from the other
  computer
- `backend/tests/test_b5c_runtime.py` — your edits
- `docs/work/archive/2026-05-20-f4b-toolbar-modals/checklist.md` — your tracking edits

These should survive the revert (they're not in any F4b commit).
