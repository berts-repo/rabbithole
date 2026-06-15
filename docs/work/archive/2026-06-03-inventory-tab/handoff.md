# Handoff — Inventory Tab

## State

Package opened 2026-06-03, right after NodeSet Workspaces (item 4) closed.
Implementation in progress — see `checklist.md` for live status.

## Where things live (grounded reads)

- Bottom-pane tab registry + groups: `frontend/src/lib/stores/bottomGroups.ts`
  (`BottomTab` union, `BOTTOM_GROUPS`). Render switch:
  `frontend/src/views/BottomPane.svelte`.
- Graph payload: `graphStore.payload` (`lib/stores/graph.svelte.ts`) — the
  loaded global/collection payload; `GraphNode` / `GraphPayload` in
  `lib/api/types.ts:132`.
- Active nodeset source + scope seam: `workspaceStore.activeNodeSetSource()`
  (`lib/stores/workspace.svelte.ts:278`) +
  `buildNodeSetPredicate(source, hiddenDeps)` (`lib/graph/nodeSetScope.ts`),
  wired exactly as `GraphCanvas.svelte:132`.
- Highlight gesture precedent: `DomainsTab.onSelect` (`views/bottom/DomainsTab.svelte:111`)
  → `selectionStore.replaceMulti` + `navigationStore.setRight('domain')`.
- Hidden accessors: `domainVisibilityStore.isHidden(host)` /
  `.isNodeHidden(id)`.

## Gotchas

- Only the **active** workspace's payload is loaded in `graphStore`. Per-tab
  node counts are exact only for captured nodeset tabs (`source.nodeIds`) and
  the active tab; others render `—`. Don't try to fetch other tabs' payloads.
- Backend serves `is_cluster: false` for all payload nodes (clustering is
  client-side) — but guard `domainsInGraph` against `is_cluster` anyway so a
  future change can't silently inflate domain counts.
- `flag_status` is a nullable string; count it truthy and not `'none'`.

## Owner surface (answer when convenient — defaults shipped)

Two user-facing picks shipped on defaults; see `decisions.md`:
- Tab name = **"Inventory"** (vs Overview / Workspace).
- Placement = **first tab of the Catalog group + its default landing**.

Both are one-line changes if the owner wants otherwise.
</content>
