# Checklist — NodeSet Workspaces

## Engine
- [x] `nodeSetScope.ts` — `buildNodeSetPredicate(source, hiddenDeps)` + vitest
- [x] `visibilityController.setScope(predicate, { includeHidden })` + vitest
- [x] `workspace.svelte.ts` — typed scope, `openNodeSetTab`, `activeNodeSetSource`,
      nodeset-aware reconcile, persistence

## Wiring
- [x] GraphCanvas installs/clears scope on active workspace
- [x] WorkspaceTabs close ✕ on nodeset tabs

## Consumers (Open as graph tab)
- [x] Domains — per-row (BottomPaneRow trailing action)
- [x] Flags — header (filtered set)
- [x] Fingerprints — per-cluster-row
- [x] Bookmarks — header (filtered set, by host)
- [~] Hidden — engine-ready, no v1 consumer (server-side `graph_filters` nodes
      are excluded from the payload; see `decisions.md`)
- [x] Graph multi-selection — context-menu "Open as graph tab (N)"

## Verification
- [x] `npm run check` — no new errors (12 pre-existing baseline unchanged)
- [x] `npm run build` clean (single bundle.js + bundle.css)
- [x] vitest green — 38 files / 354 tests (was 342; +12 new)
- [x] Browser smoke: open each source as a tab, confirm induced subgraph,
      switch back to Global, close a nodeset tab, reload (persistence) —
      owner-confirmed 2026-06-03, all four entry points good

## Close
- [x] Update `docs/reference/` (workspace model) — `features.md` +
      `frontend-structure.md`
- [x] `outcome.md` with before/after LOC + tests
- [x] Archive package, repoint `ACTIVE.md`
</content>
