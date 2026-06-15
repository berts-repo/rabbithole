# Checklist — Bottom Pane Completion (F7)

## Phase 1 — Row component + context menu + Bookmarks + Collection

### Context-menu consolidation

- [x] New `frontend/src/lib/contextMenu/` module (commits e703713,
      994b96c, fafec22 — landed before phase 1.4):
  - [x] `MenuTarget` type. Lives in `sections.ts`; the minimum-fields
        shape (`stub`, `flag_status`, `reviewed`, `domain`) is
        structurally compatible with `GraphNode` so the graph adapter
        passes nodes directly with no conversion.
  - [x] Section builders moved into `sections.ts` —
        `buildSingleTargetSections`, `buildMultiSelectSections`.
        Covered by `sections.test.ts`.
  - [x] `ContextMenu.svelte` (renamed from `NodeContextMenu.svelte`) is
        the single renderer for graph node, graph edge, and bottom-pane
        menus.
- [x] No dedicated `lib/graph/interactions/contextMenu.ts` file —
      reconsidered during the refactor. The trigger
      (`renderer.on('rightClickNode' | 'rightClickEdge', …)`) and the
      single/multi handler factories stay inline in `GraphCanvas.svelte`
      because they bind to Sigma renderer state plus the canvas's modal
      and selection stores; no pure helper to extract. Shared
      `act*` calls live in `$lib/contextMenu/actions.ts`.
- [x] No behavior change to the graph node menu — same actions, same
      labels, same ordering.

### BottomPaneRow

- [x] `frontend/src/views/bottom/BottomPaneRow.svelte`.
- [x] ●/○ visibility button bound to per-domain visibility state.
      (Controlled `visible` prop + `onToggleVisibility` callback — owning
      sub-tab decides scope: per-domain for Domains/Bookmarks/Collection,
      per-node for Fingerprints members.)
- [x] Content-button slot. (Snippet `children`.)
- [x] Click → full select (`selectionStore`, `selectMode: 'full'`).
      (`onSelect` callback; sub-tab calls `selectionStore.fullSelect`.)
- [x] Active-row marker scoped to the owning sub-tab. (`active` prop;
      parent compares its row id against the bottom-pane's full-select id.)
- [x] Hidden rows render dimmed. (`.dimmed` when `!visible`.)

### Bottom-pane context-menu adapter

- [x] Right-click on row mounts the shared `ContextMenu.svelte` with a
      row-derived `MenuTarget`.
      (`views/bottom/bottomPaneMenu.svelte.ts` + `BottomPaneContextMenu.svelte`
      — store-backed, mounted once in `BottomPane.svelte`, renders in a
      fixed overlay so the menu escapes `.body`'s `overflow: auto`.)
- [x] Collection sub-tab passes `collection context` so "Remove from
      collection" shows.
      (`BottomPaneMenuTarget.inCollection` + `onRemoveFromCollection`
      — Collection sub-tab (1.5) will set both when it builds rows.)

Action wiring: URL-only items (Copy URL, Send to Crawl, Save as Seed
Bookmark, Hide from Graph) always work; id-bound items (Open in Tor,
Flag, Mark Reviewed, Focus, Queue Analysis) require the row to resolve
to a `GraphNode`. Rows that don't (a Bookmark for a not-yet-crawled URL)
short-circuit with a readable toast — the menu still opens.

Shared `act*` functions moved to `$lib/contextMenu/actions.ts` so both
the graph (GraphCanvas) and the bottom pane call into the same toasts /
graph-poller refreshes / payload-cache invalidation.

### Bookmarks sub-tab

- [x] `frontend/src/views/bottom/BookmarksTab.svelte`.
- [x] Filter input, count badge, "Add bookmark" button.
- [x] `▶ Send to Crawl` per row → reuses `actQueueCrawl` (single-URL
      load into CrawlControls). Spec calls for single-URL into the
      manual input, matching the existing right-click path; the
      BatchConfirmStrip note in the plan referred to the Crawl-sub-tab
      surface as a whole.
- [x] Inline rename label (Enter saves, Escape cancels). Needed a small
      backend addition (`PATCH /api/seeds` + `update_seed_label` DB
      helper) — the original "no new endpoints" plan note overlooked
      that the spec's rename can't round-trip without one. Backend test
      `test_seeds_patch_label` covers it.
- [x] ✕ delete.
- [x] Save-as-Seed-Bookmark from other surfaces appears immediately
      (already wired via `seedBookmarksStore.add`, which mutates the
      same state this tab reads).
- [x] Duplicate-URL toast — `Already in crawl bookmarks.` matches the
      existing CrawlControls phrasing.
- [x] Per-host visibility wired through new `domainVisibilityStore`
      (client-side, ephemeral). GraphCanvas's `computeVisibility` pass
      reads `isHidden(host)`, so the ●/○ dot has end-to-end effect.
      Collection (1.5) and Domains (Phase 3) will reuse the same store.

### Collection sub-tab

- [x] `frontend/src/views/bottom/CollectionTab.svelte`.
- [x] Workspace-driven (reads `workspaceStore.activeWorkspaceId` via
      `activeCollectionId()` — `null` on Global, the row id otherwise).
- [x] Header: collection name, ✎ rename (inline; Enter saves, Escape
      cancels), ↓ export dropdown (JSON / Nodes CSV / GEXF — anchor
      download against `collectionExportUrl`), 🗑 delete (shared
      `Modal.svelte` confirm).
- [x] Filter input over URL + title + domain, count badge.
- [x] `Send to Crawl (all uncrawled)` — shown only when ≥ 1 stub;
      stages every stub URL into `BatchConfirmStrip` with `collectionId`
      pre-pinned via the new `defaultsOverride` arg on
      `batchConfirmStore.stage()`, switches the left pane to Crawl.
- [x] Rows: URL + page title; stubs render an amber `not crawled` badge
      in place of the title. Hollow-node rendering is the canvas's job
      (already keyed off `stub: true`) — full-select carries the row id
      through `selectionStore.fullSelect`.
- [x] Empty states: "Open a collection workspace tab…" / "No items in
      this collection." / filter-no-match / loading / load error.
- [x] Deleted collection calls `workspaceStore.closeTab(tabId)` which
      auto-flips active workspace back to Global. The renamed collection
      also updates the workspace tab label via new
      `workspaceStore.renameTab()`.

Action wiring: full-select uses the item's node id directly
(`selectionStore.fullSelect(it.id)`). Right-click menu pulls the real
`GraphNode` out of `graphStore.payload` by id so the menu builder gets
the full alias / flag_status / reviewed picture. "Remove from
collection" uses the new `removeItemFromCollection` API helper, then
invalidates the per-id cache and reloads.

### Wire-up

- [x] `BottomPane.svelte` body replaced with a tab-routed component slot
      (Bookmarks + Collection routed; remaining tabs keep the placeholder
      until their sub-tab component lands).
- [x] Per-tab "first-load done" flag — not needed. Analyses and other
      first-load-on-switch tabs handle the load with local component
      state; no shared workspace flag added.

### Phase 1 verification

- [x] `npm run check` clean.
- [x] `npm run test` clean; pure-helper tests for `BookmarksTab`
      (`bookmarks.test.ts`), `CollectionTab` (`collection.test.ts`), and
      the shared context-menu section builders (`sections.test.ts`).
      Component-level rendering verification stays on the browser
      exercise — vitest is node-only here.
- [ ] Browser exercise (SwiftShader Edge) — deferred. Vitest covers the
      pure helpers (140 passing across all four phases); the remaining
      surface checks (Bookmarks add/rename/delete/Send-to-Crawl,
      Collection rename/export/delete/Send-to-Crawl, selection-model
      parity, row-menu parity with the graph) will be exercised in
      F6 (right-pane row menus) by real use. Owner decision: archive
      package without this gate.
- [x] Update `docs/reference/features.md` with the new tabs and the
      shared context-menu module.

## Phase 2 — Live Crawl + Analyses

- [x] `LiveCrawlTab.svelte` (SSE, ring buffer, color coding) — `crawlLogStore`
      ref-counts the `/api/crawl/log` subscription so other consumers can
      share it; 200-line cap mirrors the backend ring buffer. `liveCrawl.ts`
      parses status code, onion URL, and severity per line (covered by
      `liveCrawl.test.ts`). Rows with a matching `GraphNode` full-select on
      click; rows without one toast.
- [x] `AnalysesTab.svelte` (5 s poll, filters, full-select) — uses the new
      `listAnalyses` API call, polls on `setInterval(5000)` with stale-fetch
      versioning so a late response can't clobber a newer one. Status filter
      treats `waiting` as part of `pending` per spec's four-bucket dropdown;
      type filter is client-side over the 500-row fetch cap. Row click drives
      `selectionStore.fullSelect(node_id)` + `navigationStore.setRight('analysis')`.
- [x] Tests pass — pure-helper tests for `liveCrawl` and `analyses`.
- [ ] Browser verification — deferred to F6 use (see Phase 1
      verification note).
- [x] `features.md` update.

## Phase 3 — Domains + Flags

- [x] `DomainsTab.svelte` (domain highlight, host-wide visibility toggle) —
      adds `listDomains` + `DomainRow` to the API barrel. Loads once on
      first switch (⟳ for manual refresh; no polling). Row click calls
      `selectionStore.replaceMulti(host node ids)` for the highlight set
      and `navigationStore.setRight('domain')` for the panel anchor.
      Host nodes are ordered by `first_seen ASC, id ASC` so the [0]
      entry is the stable Domain-panel anchor + right-click target.
      The ●/○ dot reuses `domainVisibilityStore.toggle(host)`.
      Spec note "not a multi-select, does not trigger cluster workspace"
      is a deferred F6 concern — today `replaceMulti` already produces
      the right highlight+dim; when F6 lands the cluster trigger must
      gate on something other than just multi-count.
- [x] `FlagsTab.svelte` (URL filter, status + priority dropdowns) —
      adds `listFlags` + `FlagListRow` (joined url/title from backend).
      Loads once on first switch; ⟳ refresh. URL filter (URL + title),
      Status dropdown (All / Pending / Investigating / Done / Dismissed
      — `flagged` folds into Pending), Priority dropdown (All / High /
      Med / Low). Row click full-selects (`selectionStore.fullSelect`).
      Per-host ●/○ dot via `domainVisibilityStore`.
- [x] Tests pass — pure-helper tests for `domains` and `flags`
      (`domains.test.ts`, `flags.test.ts`). `npm run check` clean,
      `npm run test` 140 passed.
- [ ] Browser verification — deferred to F6 use (see Phase 1
      verification note).
- [x] `features.md` update.

## Phase 4 — Fingerprints + Hidden

- [x] `FingerprintsTab.svelte` (min-sites threshold, lazy members, CSV) —
      adds `listFingerprints` / `listFingerprintMembers` / `fingerprintsCsvUrl`
      to the API barrel and `FingerprintCluster` / `FingerprintMember` types.
      Cluster rows expand on click, lazy-load + cache members keyed by
      (key, value); per-cluster member filter input. ⟳ refresh wipes both
      the cluster list and every member cache. CSV export is an anchor
      download against `/api/fingerprints/export.csv`.
- [x] Member visibility uses the new `domainVisibilityStore.toggleNode` /
      `isNodeHidden` per-node path (separate from the existing per-host
      path used by Bookmarks / Collection). GraphCanvas's `computeVisibility`
      pass reads both keys; the dot in `BottomPaneRow` is wired to the
      per-node negation for fingerprint members.
- [x] `HiddenTab.svelte` (add/remove terms, graph-cache invalidation) —
      adds `listGraphFilters` / `deleteGraphFilter` to the API surface
      alongside the existing `addGraphFilter`. Both mutations invalidate
      payload snapshots and refresh the graph poller. Duplicate adds
      collapse into an "Already hidden." toast on the 409 path.
- [x] Tests pass — pure-helper tests for `fingerprints` and `hidden`.
- [ ] Browser verification — deferred to F6 use (see Phase 1
      verification note).
- [x] `features.md` update.
- [x] Close package — `outcome.md` written, moved to `archive/`,
      `ACTIVE.md` repointed (2026-05-27).
