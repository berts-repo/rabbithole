# Plan — Inventory Tab

## Shape: pure helper + thin component

Follow the bottom-pane convention (a pure `.ts` helper beside the `.svelte`
tab, vitest against the helper):

- `frontend/src/views/bottom/inventory.ts` — runtime-free. Operates on plain
  `GraphNode[]` / `GraphEdge[]` arrays the component hands it; no store imports.
  - `inducedSubgraph(payload, keep): { nodes, edges }` — nodes passing `keep`,
    plus edges whose **both** endpoints survive (the item-4 induced-subgraph
    rule).
  - `summarize(nodes, edges): InventorySummary` — `{ nodes, edges, crawled,
    uncrawled, flagged, reviewed, categorized, bridges }`.
  - `domainsInGraph(nodes): DomainCount[]` — `{ host, count, flagged }` per
    distinct non-null host, sorted by count desc then host asc. Skips
    `is_cluster` synthetic nodes.
- `frontend/src/views/bottom/inventory.test.ts` — vitest over the three pure
  functions (empty payload, mixed stub/flag/review, induced-edge dropping,
  domain sort + tie-break, cluster-node exclusion).
- `frontend/src/views/bottom/InventoryTab.svelte` — resolves the active scope,
  calls the helpers in `$derived`, renders three sections.

## Active-scope resolution (component)

```ts
const scoped = $derived.by(() => {
  const payload = graphStore.payload;
  if (!payload) return { nodes: [], edges: [] };
  const source = workspaceStore.activeNodeSetSource();
  if (!source) return { nodes: payload.nodes, edges: payload.edges };
  const { predicate } = buildNodeSetPredicate(source, {
    isHidden: (d) => domainVisibilityStore.isHidden(d),
    isNodeHidden: (id) => domainVisibilityStore.isNodeHidden(id),
  });
  return inducedSubgraph(payload, (n) => predicate(n.id, n));
});
```

Same `buildNodeSetPredicate` + `hiddenDeps` wiring GraphCanvas uses
(`GraphCanvas.svelte:132`), so a NodeSet tab's inventory matches what's drawn.
Global / collection tabs use the full loaded payload.

## Workspace-tab rows

`workspaceStore.openTabs` → one row each: label, a kind/source descriptor, and
a node count.
- **Captured** nodeset tabs (`flag`/`fingerprint`/`selection`) show
  `source.nodeIds.length` directly — exact regardless of which tab is active.
- The **active** tab shows its live scoped node count.
- Other tabs (inactive global/collection, derived nodeset whose payload isn't
  loaded) show `—`; only the active tab's payload is in memory.

Click → `workspaceStore.setWorkspace(tab.id)`. Active row marked.

## Aggregate counts (fields available today)

From `GraphNode`: `stub` (crawled = `!stub`), `flag_status`, `reviewed`,
`category` (categorized), `is_bridge`. Deferred counts (`dead`, `labeled`) wait
on their upstream items — see `decisions.md`.

## Wiring

1. `lib/stores/bottomGroups.ts` — add `'inventory'` to `BottomTab`; add
   `{ id: 'inventory', label: 'Inventory' }` as the **first** tab of the
   `catalog` group; default `lastTabPerGroup.catalog` to `'inventory'`.
2. `views/BottomPane.svelte` — `{:else if bottomTab === 'inventory'}` branch.
3. Reuse shared `EmptyState` for the no-graph / no-domains states.

## Build order

1. `inventory.ts` + vitest.
2. `bottomGroups.ts` registration.
3. `InventoryTab.svelte`.
4. `BottomPane.svelte` branch.
5. `npm run check` + `npm run build` + vitest; browser smoke.

## Out of scope (v1)

Optional expandable breakdowns (by flag / category / review / language) — the
spec marks them optional; ship the three core sections first. No live-stream
behavior (that's the Activity tab, item 6). Read-only — no row mutates state.
</content>
