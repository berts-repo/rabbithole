# Inventory Tab (item 5)

Closed package. Promoted from `NEXT.md` item 5 on 2026-06-03, immediately after
NodeSet Workspaces (item 4) closed — the two pair: item 4 multiplies the open
workspace-tab count, this makes the result legible.

A passive, read-only bottom-pane tab that answers "what's currently loaded into
my session?" in one place:

- **Workspace tabs** — every open graph tab with its source/kind and node
  count; click a row to focus that tab.
- **Domains in the current graph** — every distinct host in the
  currently-rendered workspace, sorted by node count; click to highlight its
  nodes + open the right-pane Domain tab (the same gesture the Domains tab
  uses).
- **Aggregate counts** — nodes / edges, crawled / uncrawled, flagged,
  reviewed, categorized.

Rows navigate; they never mutate state. Frontend only — reads the existing
graph and workspace stores; no schema changes, no new endpoints.

## Spec

Historical source spec: [`source-spec.md`](source-spec.md). Its "Deferred
Decisions" were resolved in `decisions.md`.

## Read order

1. This README.
2. `plan.md` — build order and the pure-helper / component split.
3. `decisions.md` — the deferred-decision resolutions.
4. `checklist.md` — task tracker.
5. `handoff.md` — current state for the next agent.

## Key reuse

- Reflects the **active workspace's rendered scope**: when a NodeSet tab (item
  4) is active, the inventory filters the loaded payload through the same
  `buildNodeSetPredicate(source, hiddenDeps)` seam GraphCanvas installs, so the
  overview matches the induced subgraph on screen.
- Domain-row click mirrors `DomainsTab.onSelect` exactly:
  `selectionStore.replaceMulti(ids)` + `navigationStore.setRight('domain')`.
- Workspace-row click is `workspaceStore.setWorkspace(id)`.
</content>
