# Inventory Tab

## Status

Implementation-ready feature spec. Promoted to the active queue on
2026-05-27 — slotted as item 5, right after NodeSet Workspaces (item 4),
because that item is what materially raises Inventory's value and the
two pair naturally. Frontend only, no schema changes.

Owner-originated: "a global tab on the bottom that shows all the tabs
and domains in the graph."

Complementary to (but distinct from)
`../2026-06-03-nodeset-workspaces/source-spec.md`:

- **NodeSet Workspaces** (item 4 in `NEXT.md`) = open lists as graph tabs.
  *Creates* workspaces.
- **Inventory Tab** (this) = a bottom-pane tab showing *what's currently
  loaded*. *Surveys* workspaces.

## Goal

Answer "what's currently loaded into my session?" in one place. A passive,
read-only overview of workspace contents and graph composition.

The pain it addresses: as the user accumulates many workspace tabs (especially
after NodeSet Workspaces ships) and the graph contains thousands of nodes
across dozens of domains, there's no single place to ask "what am I looking
at right now?"

## What the Tab Contains

### Workspace tabs

Every open workspace tab listed with its source, label, and node count.
Clicking a row focuses that tab. Useful when many tabs are open from
different sources (collection, domain, flag, label, search).

### Domains in the current graph

Every distinct domain represented in the currently-rendered graph, sorted by
node count. Clicking a domain row highlights its nodes (or opens the
right-pane Domain tab). Answers "what domains are tangled together in this
view?"

### Aggregate counts

Single-line totals for the current workspace:

- Total nodes / edges
- Crawled / uncrawled / dead split (post-`schema-reset.md`)
- Flagged count
- Labeled count (shipped by
  [`../2026-06-10-label-system/outcome.md`](../2026-06-10-label-system/outcome.md))
- Analysis-completed count

### Optional breakdowns

Expandable sub-sections that surface filter dimensions as scannable lists:

- By flag (with counts)
- By category / label
- By review state
- By language (if detection lands)

These are filters that already exist in the graph; the inventory tab surfaces
them as a list you can read rather than a UI you have to drive.

## Why Read-Only

Inventory contrasts intentionally with the Activity tab (delivered by item
6 in `NEXT.md`, which is the operational "what's the system doing?"
surface). Inventory is **static** until the user changes scope; Activity is
a **live stream**. Mixing them creates confusion.

Inventory rows are clickable for navigation (focus tab, highlight domain,
open right-pane Domain tab), but rows do not mutate state.

## Implementation Sketch

- New `frontend/src/views/bottom/InventoryTab.svelte`
- Reads from existing graph store + workspace store
- No schema changes, no new endpoints
- Estimated scope: 300–500 LOC
- Reuses shared primitives from `../2026-06-03-shared-ui-primitives/source-spec.md`

## Dependencies

- `pane-responsibility-reset.md` — bottom-pane ownership of overview surfaces.
- `shared-ui-primitives.md` — tab/list/row primitives.
- `unified-activity-view.md` (delivered inside the schema reset milestone)
  — establishes the bottom-pane tab pattern this builds on.
- `list-to-graph-tabs.md` (NodeSet Workspaces) — without it, inventory only
  lists 2 tab kinds (Global, collections). With it, inventory becomes much
  more valuable.

## User-Visible Changes

- New bottom-pane tab labelled "Inventory" or "Overview" (name TBD).
- One place to see all open workspace tabs and jump between them.
- One place to see which domains are represented in the current graph.
- Quick scannable counts and breakdowns for the current scope.

## Why Slotted Here

Item 4 (NodeSet Workspaces) is what makes the "too many tabs, no
overview" pain real: any bottom-pane list can spawn a graph tab, so an
analyst routinely accumulates 5–15 open workspaces. Building Inventory
immediately after item 4 means the legibility surface lands the moment
the pain does, rather than weeks later after the schema reset and Intel
work pile on.

The tab does not need the schema reset (item 6) — it reads workspace
and graph stores that already exist today. If item 6 ships first
without disruption, Inventory simply inherits the new
crawled/uncrawled/dead split for its aggregate counts; if Inventory
ships first, that count line uses the existing `stub` field until the
reset replaces it.

## Deferred Decisions

- Tab name: "Inventory", "Overview", "Workspace", or other.
- Whether the tab is part of the default bottom-pane tab set or opt-in.
- Whether the breakdowns are configurable per user or fixed.
- Whether clicking a domain row highlights the graph or opens the right-pane
  Domain tab (or both — primary click highlights, secondary opens detail).
- Whether the tab updates live as the graph scope changes or only on focus.
