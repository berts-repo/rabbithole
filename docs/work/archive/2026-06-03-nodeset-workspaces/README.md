# NodeSet Workspaces (item 4)

Closed package. Promoted from `NEXT.md` item 4 on 2026-06-03 once its
dependencies (item 2 Shared UI Primitives, item 3 GraphCanvas Decomposition)
closed.

Generalises the graph workspace-tab system so any bottom-pane node set —
a domain's pages, the flagged nodes, a fingerprint cluster's members,
bookmarks, hidden nodes, or a graph multi-selection — can open as its own
graph tab showing the induced subgraph. Replaces the hard-coded
"global vs collection id" workspace shape with a typed `WorkspaceScope`.

## Spec

Historical source spec: [`source-spec.md`](source-spec.md).
Owner-recommended defaults from its "Deferred Decisions" were adopted here; see
`decisions.md` and `outcome.md`.

## Read order

1. This README.
2. `outcome.md` — what shipped and final status.
3. `plan.md` — the build order and the typed-scope design.
4. `decisions.md` — the owner-recommended defaults adopted and why.
5. `checklist.md` — task tracker.

## Key seam

`visibilityController.setScope()` (shipped with item 3) is the plug point.
NodeSet tabs load the **global** graph payload (no collection id) and the
controller filters it client-side to the scope's membership predicate —
v1 is purely frontend-filtered, no scoped-payload endpoint.
</invoke>
