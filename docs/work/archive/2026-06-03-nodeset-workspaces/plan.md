# Plan — NodeSet Workspaces

## Typed scope design

The workspace store currently keys a tab by `kind: 'global' | 'collection'`
plus a nullable `collectionId`. Generalise to a typed source:

```ts
type WorkspaceKind = 'global' | 'collection' | 'nodeset';

type NodeSetSource =
  | { kind: 'domain'; host: string }            // derived: raw.domain === host
  | { kind: 'flag'; nodeIds: number[]; summary: string }       // captured
  | { kind: 'fingerprint'; nodeIds: number[]; summary: string } // captured
  | { kind: 'bookmarks'; urls: string[] }       // derived-by-url: raw.raw_url ∈ urls
  | { kind: 'hidden' }                          // derived: isHidden / isNodeHidden
  | { kind: 'selection'; nodeIds: number[] };   // captured

interface OpenTab {
  id; kind; collectionId; label;
  source: NodeSetSource | null;   // set only when kind === 'nodeset'
}
```

**Derived vs captured.** A *derived* source re-evaluates its membership from
the live payload/store on every `compute()` (so newly-crawled domain pages or
newly-hidden nodes appear automatically). A *captured* source freezes the
node-id member set at open time — used where membership is not a stable graph
attribute (a fingerprint cluster, a filtered flag list, a graph selection).

Membership lives in the payload for every kind we ship:
- `domain` → `GraphNode.domain`
- `flag` → captured `node_id`s (honours the list's status+priority filter)
- `fingerprint` → captured member `id`s (cluster membership is not a node attr —
  `infra_cluster_id` is only the node's single rarest header pair)
- `bookmarks` → `GraphNode.raw_url` matched against the seed urls
- `hidden` → `domainVisibilityStore.isHidden / isNodeHidden`
- `selection` → captured ids

## Build order

1. **Engine — scope predicate.** New pure module
   `frontend/src/lib/graph/nodeSetScope.ts`: `buildNodeSetPredicate(source, hiddenDeps)`
   → `{ predicate: ScopePredicate; includeHidden: boolean }`. Vitest alongside.
2. **Engine — controller.** `visibilityController.setScope(predicate, opts?)`
   gains an optional `{ includeHidden }` so a `hidden` scope can *show* the
   nodes the controller normally drops. Extend its vitest.
3. **Engine — workspace store.** Typed `WorkspaceScope` / `NodeSetSource`,
   `openNodeSetTab(source, label)` (dedup by source signature, re-capture
   members on reopen), `activeNodeSetSource()`, nodeset-aware `reconcile`,
   and persistence of nodeset tabs. Extend its vitest.
4. **Wiring — canvas.** GraphCanvas installs the scope predicate via an effect
   on the active workspace; clears it for global/collection tabs.
5. **Wiring — tabs.** WorkspaceTabs shows the close ✕ on nodeset tabs too.
   WorkspacePicker keeps opening collections; nodeset tabs are opened from the
   lists.
6. **Consumers.** "Open as graph tab" affordance per list:
   - Domains — per-row (one domain).
   - Flags — header (current filtered set).
   - Fingerprints — per-cluster-row (that cluster's members).
   - Bookmarks — header (current filtered set).
   - Hidden — header (singleton hidden scope).
   - Graph multi-selection — context-menu "Open selection as graph tab".

## Payload base

NodeSet tabs carry `collectionId: null`, so the existing
`graphPoller` already fetches the **global** payload for them — no poller
change. The bridge effect in `GraphTab.svelte` refreshes on tab switch.

## Out of scope (v1)

Live Crawl tab, external (F8) search results, and the standalone Analyses set
do **not** get the affordance — see the spec's "Explicitly excluded". Label and
local-search sources were waiting on label-system / F5; both are now archived
as completed work.
