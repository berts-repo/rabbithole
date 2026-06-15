# Outcome — NodeSet Workspaces

Closed: 2026-06-03

Fourth post-F6 package (item 4). Frontend only — no schema, no backend routes.
Built on item 3's `visibilityController.setScope()` seam and item 2's shared
primitives. Generalises the graph workspace-tab system from a hard-coded
`global | collection` shape to a typed `WorkspaceScope`, so any bottom-pane
node set opens as its own graph tab over the induced subgraph, filtered
client-side from the loaded global payload (v1 is purely frontend-filtered, no
scoped-payload endpoint).

## What shipped

### Engine

- `lib/graph/nodeSetScope.ts` — pure `buildNodeSetPredicate(source, hiddenDeps)`
  → `{ predicate, includeHidden }` plus a source-signature builder for dedup.
  Vitest alongside.
- `visibilityController.setScope(predicate, { includeHidden })` — the optional
  flag lets a `hidden` scope *show* the nodes the controller normally drops.
  Vitest extended.
- `workspace.svelte.ts` — typed `WorkspaceKind = 'global' | 'collection' |
  'nodeset'` and `NodeSetSource` (domain, flag, fingerprint, bookmarks, hidden,
  selection); `openNodeSetTab` (dedup + re-capture on reopen),
  `activeNodeSetSource()`, nodeset-aware `reconcileCollections` (keeps
  `kind === 'nodeset'` tabs whose `collectionId` is null), and persistence.
  Derived sources re-derive on each compute; captured sources freeze member
  ids at open.

### Wiring

- `GraphCanvas.svelte` installs/clears the scope predicate via an effect on the
  active workspace.
- `WorkspaceTabs.svelte` shows the close ✕ on nodeset tabs.

### Consumers ("Open as graph tab")

- **Domains** — per-row trailing action (`BottomPaneRow`), one domain.
- **Flags** — header button, the current filtered set.
- **Fingerprints** — per-cluster-row, that cluster's members.
- **Bookmarks** — header button, the current set by host.
- **Graph multi-selection** — context-menu "Open as graph tab (N)".

## Verification

- `npm run check` — 12 errors / 11 files, the unchanged pre-existing baseline;
  none in the nodeset files. Independently re-run at close.
- `npm run build` — clean, single `bundle.js` + `bundle.css` (→ `backend/public`).
  The >500 kB chunk-size warning is informational, not a failure.
- `vitest` — 38 files / 354 tests green (+12 new over the 342 baseline).
  Independently re-run at close.
- Browser smoke — owner confirmed all four entry points open the induced
  subgraph, switch back to Global, close cleanly, and persist across reload.

## Size

+642 / −39 across 16 files. New engine module + its vitest are 229 LOC.

## Deferred / not done

- **Hidden source** — engine-ready (`{ kind: 'hidden' }` predicate +
  `includeHidden`, unit-tested) but **no v1 consumer**. Server-side
  `graph_filters` nodes are excluded from the `/api/graph` payload, so a
  frontend-only tab over them would be empty, violating the spec's own
  "members must be in the payload" rule. A real consumer needs a backend
  opt-in returning server-hidden nodes with a flag, or a dedicated
  "review what I've hidden" surface for the client-side ●/○ hides. The engine
  seam shipped anyway, mirroring how item 3 shipped `setScope` ahead of its
  first consumer. See `decisions.md`.
- Label / label-query sources — shipped by
  [`../2026-06-10-label-system/outcome.md`](../2026-06-10-label-system/outcome.md).
- Local crawled-content search results — wait for F5 (item 9); they qualify as
  a NodeSet source and get the affordance as an additive follow-on.
- Live Crawl and external (F8) search results — intentionally excluded, not
  deferred; see the spec's "Explicitly excluded."

## What this unlocks

- **Item 5 — Inventory tab** pairs directly with this: NodeSet Workspaces
  multiplies the open-tab count, and Inventory makes the explosion legible.
- The typed `WorkspaceScope` is now the final workspace model the frontend
  settles on before the **item 6 schema reset** changes data shapes underneath.
</content>
</invoke>
