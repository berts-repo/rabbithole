# Checklist — Inventory Tab

## Pure helper
- [x] `inventory.ts` — `inducedSubgraph`, `summarize`, `domainsInGraph`
- [x] `inventory.test.ts` — vitest (empty, mixed flags/stubs/review, induced
      edge drop, domain sort + tie-break, cluster-node exclusion)

## Wiring
- [x] `bottomGroups.ts` — `'inventory'` in `BottomTab`; first tab of Catalog;
      Catalog default landing (+ test assertions updated)
- [x] `BottomPane.svelte` — render branch

## Component
- [x] `InventoryTab.svelte` — three sections (workspace tabs, domains, counts)
- [x] Workspace rows focus tab; active row marked
- [x] Domain rows highlight + open right-pane Domain (mirror DomainsTab)
- [x] Active-scope resolution via `buildNodeSetPredicate`
- [x] Reuse `EmptyState` for no-graph state

## Verification
- [x] `npm run check` — 12-error baseline unchanged, none in new files
- [x] `npm run build` clean (single bundle)
- [x] vitest green — 39 files / 359 tests (+1 file, +5 new)
- [x] Browser smoke: open tab, switch workspaces (global / collection /
      nodeset), click a domain row, click a workspace row, confirm counts —
      owner-confirmed

## Close
- [x] Update `docs/reference/` — `features.md` (bottom-pane tab list 8→9,
      Catalog grouping, Inventory entry). No other reference doc enumerates
      bottom-pane sub-tabs, so none else needed a change.
- [—] `outcome.md` — skipped per owner; the close record lives in `ACTIVE.md` /
      `NEXT.md` and the shipped detail in commit `ece8f99`.
- [x] Archive package, repoint `ACTIVE.md` / `NEXT.md`
</content>
