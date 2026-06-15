# NodeSet Workspaces (Lists as Graph Tabs)

## Status

Implementation-ready feature spec. Promoted from deferred on 2026-05-27 — the
owner chose to bundle this with the broader post-F6 cleanup rather than wait
for it.

Depends on `graphcanvas-decomposition.md` (the new `visibilityController` is
the right plug point for arbitrary node-set scope) and
`shared-ui-primitives.md` (workspace picker, "open as tab" affordance).

## Goal

Today, graph workspace tabs exist only for the Global graph and per-collection
graphs. Generalise that pattern so a graph "tab" is *a scoped node set from
any source*, not just Global + collections.

Most bottom-pane lists are already node sets. The analyst should be able to
take any of them whose members are real graph nodes and open it as its own
graph tab showing the induced subgraph — visualise just the flagged nodes,
just one domain's pages, just a label query, just a fingerprint cluster.

Two sources that look list-like — Live Crawl and external search results —
deliberately do **not** become NodeSet tabs; see the "Explicitly excluded"
section below.

## Sources That Can Open as a Graph Tab

Only sources whose members are guaranteed to be in the loaded graph payload
(or trivially derivable from it) get the "Open as graph tab" affordance.
This keeps v1 purely frontend-filtered — no scoped-payload endpoint
required.

In scope for v1:

- **Collection** — already has workspace tabs (the existing template).
- **Bookmarks**
- **Domains** — open one domain's nodes as a tab.
- **Flags** — every node carrying a given flag.
- **Fingerprints** — every node in a fingerprint cluster.
- **Hidden** — hidden nodes as their own scope (useful for review).
- **Labels** — every node carrying a label (when
  label-system work shipped; see
  [`../2026-06-10-label-system/outcome.md`](../2026-06-10-label-system/outcome.md)).
- **Label query / filter result** (shipped by
  [`../2026-06-10-label-system/outcome.md`](../2026-06-10-label-system/outcome.md)).
- **Multi-selection from the graph** — current cluster workspace pattern
  generalised.

### Explicitly excluded — handled by native surfaces instead

- **Live Crawl** stays in the bottom pane as a streaming-log tab and does
  **not** get an "Open as graph tab" action. The graph view of in-progress
  crawl activity is the Global tab, which already updates live as nodes
  land. A static subgraph snapshot of the current frontier would be more
  confusing than useful.
- **External search results** (F8 dark-web engine search) stay in F8's own
  top-level Search tab — the existing peer-of-Graph workspace specced in
  `docs/specs/search-tab.md`. The subgraph metaphor does not fit: most
  search-result sets are unrelated URLs with no edges between them, and
  the uncrawled rows are not graph nodes at all until they are crawled.
- **Local crawled-content search results** (F5 left-pane search) are real
  graph nodes. The result list itself lives in the bottom pane as its own
  tab (composer in left, list in bottom, detail in right — see item 9 in
  `NEXT.md`). "Open as graph tab" on the F5 result list is a small
  additive follow-on once F5 ships: F5 result rows are valid NodeSet
  members and use the same affordance every other bottom-pane list does.
- **Analyses** as a standalone NodeSet source disappears entirely — the
  Activity tab from `unified-activity-view.md` is the home for analysis
  rows, and Activity is a *work set*, not a *node set*.

The general rule: NodeSet tabs exist for "show me the subgraph of these
specific entities and how they relate." If the source doesn't satisfy that
intent, it belongs in its native surface, not in the workspace picker.

## Behaviour

- "Open as graph tab" takes the list's node ids and opens a new workspace
  tab.
- The tab shows the **induced subgraph** over those nodes.
- The tab is labelled by its source (e.g. "Flags: marketplace",
  "<domain> pages", a label name, search query summary).
- Workspace picker lists every open tab regardless of source — Global,
  collections, and node-set tabs share one picker UI.
- The Global tab and existing collection tabs remain unchanged in behaviour;
  this only adds new sources for a tab.
- Close behaviour: node-set tabs close like collection tabs do.

## Implementation Notes

### Frontend — typed `NodeSet` scope

Replace the current "global vs collection id" workspace shape with a typed
scope:

```ts
type WorkspaceScope =
  | { type: 'global' }
  | { type: 'collection'; id: number }
  | { type: 'nodeset'; source: NodeSetSource; nodeIds: number[]; label: string };

type NodeSetSource =
  | { kind: 'domain'; host: string }
  | { kind: 'flag'; flag: string }
  | { kind: 'fingerprint'; clusterId: string }
  | { kind: 'label'; labelId: number }
  | { kind: 'selection' }
  | { kind: 'hidden' }
  | { kind: 'bookmarks' }
  | { kind: 'local-search'; query: string };  // post-F5; covered by additive follow-on
```

The `visibilityController` (from `graphcanvas-decomposition.md`) accepts a
predicate built from this scope.

### Backend — frontend filtering first

Two viable approaches:

1. A new endpoint returning a graph payload scoped to a supplied node-id set.
2. The frontend filters the already-loaded full graph payload down to the
   set.

**Recommended for v1: option 2.** The full graph payload is already in
memory; filtering avoids a round trip and avoids backend complexity. Switch
to option 1 only if graph size grows past what the frontend should hold in
memory — that's a future scalability call, not a v1 decision.

### Workspace persistence

Today persistence only stores collection tabs. Extend to persist node-set
tabs:

- Persist the full `WorkspaceScope` including source metadata.
- For derived sources (domain, flag, label, hidden, bookmarks), the
  persisted scope re-derives the node id set on reopen (so newly-added
  matches appear). Only `selection` scopes persist the literal node id
  list.

## User-Visible Changes

- "Open as graph tab" affordance appears on every bottom-pane list row, in
  list headers (open all visible), and in the graph context menu where
  appropriate.
- Workspace picker lists all node-set tabs alongside Global and collections.
- Right-pane Cluster workspace continues to exist for transient multi-select
  exploration; node-set tabs are the *persistent* form of the same idea.
- New tabs created from a list inherit the list's label (e.g. "Flags:
  marketplace") and the user can rename them.

## Affected Surfaces

Frontend:

- `frontend/src/lib/stores/workspace.svelte.ts` — typed scope replacing
  global/collection branching.
- `frontend/src/lib/stores/workspace-persistence.ts` — persist new scope.
- `frontend/src/components/graph/WorkspacePicker.svelte` — show all tab
  sources.
- `frontend/src/lib/graph/visibilityController.ts` — accept scope-based
  predicates (added by `graphcanvas-decomposition.md`).
- Every bottom-pane list component (Domains, Flags, Fingerprints, Bookmarks,
  Hidden, etc.) — add "Open as graph tab" action.

Backend (minimal for v1):

- Workspace state schema update if persistence shape changes.

## Code Size Expectation

Net change: roughly flat to slightly negative. The hard-coded
global/collection branching in the workspace store deletes; replaced by the
typed scope machinery. Per-list "open as tab" actions add small amounts of
code. The verified affected frontend surface from the original proposal was
~4,184 LOC; most of it is list-specific code that stays as-is.

## Relationship to Other Work

- Depends on `graphcanvas-decomposition.md` for `visibilityController`.
- Uses `shared-ui-primitives.md` for the "Open as graph tab" affordance
  pattern.
- Builds on `pane-responsibility-reset.md`'s bottom-pane ownership model.
- Consumed by the label-system work
  ([`../2026-06-10-label-system/`](../2026-06-10-label-system/)) — a label query becomes a node-set
  tab.
- F8 (Search tab completion) does **not** consume this — external search
  results live in the right pane, not as a NodeSet tab. See item 10 in
  `NEXT.md` and `docs/specs/search-tab.md`.
- Right-pane Cluster workspace stays as the transient multi-select form;
  node-set tabs are the persistent version of the same concept.

## Deferred Decisions

- Whether list-spawned tabs are **ephemeral** (close on navigate) or
  **persisted** across sessions. Recommended default: derived-source tabs
  (domain, flag, label, hidden, bookmarks) persist across sessions;
  selection-source tabs (cluster from multi-select) are ephemeral unless
  pinned.
- How the induced subgraph handles **edges to nodes outside the set** — drop
  them, or include 1-hop neighbours as stubs for context. Recommended: drop
  by default, with a "show 1-hop neighbours" toggle on the tab.
- Whether **server-side metrics** (PageRank, betweenness, clusters) recompute
  over the subgraph or are inherited from the full-graph payload.
  Recommended: inherit for v1; recompute is a later option.
- How a node-set tab stays in **sync** when its source list changes (e.g. a
  new flag is added). Recommended: re-derive on tab focus for derived
  sources; manual refresh button visible.
- How this reconciles with any future workspace/snapshot refactor — the
  typed scope is the bridge.
