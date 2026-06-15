# Decisions — Inventory Tab

Resolutions for the spec's "Deferred Decisions". The two the analyst will
actually feel (tab name, placement) are surfaced to the owner; the rest are
internal defaults, reversible later.

## Surfaced (user-facing)

- **Tab name → "Inventory".** Matches the spec's primary title and stays
  distinct from the Activity tab (item 6). One-word rename if the owner
  prefers "Overview"/"Workspace".
- **Placement → first tab of the Catalog group, and the Catalog group's
  default landing tab.** Catalog is the "data already in the project" group
  (Domains, Flags, Fingerprints, Hidden); an at-a-glance overview belongs at
  its head. Making it the default landing means opening Catalog shows the
  overview first. (Previously Catalog landed on Domains.)

## Internal defaults (decided, reversible)

- **Live, not on-focus.** The tab is a `$derived` over the graph + workspace
  stores, so it updates as scope changes for free. Still passive — it reflects
  state, never drives a poll. (The spec's static-vs-live question; live is
  strictly more useful and costs nothing under runes.)
- **Domain-row click = highlight + open right-pane Domain.** Mirrors
  `DomainsTab.onSelect` exactly (`selectionStore.replaceMulti(ids)` +
  `navigationStore.setRight('domain')`) so the two surfaces behave
  identically. Highlight-only per the app selection model — does not move the
  bottom-pane active row or trip the cluster workspace.
- **Breakdowns fixed, not configurable.** v1 ships the three core sections;
  the optional per-flag / per-category / per-review breakdowns are deferred
  (spec marks them optional). No per-user config surface.
- **Inventory reflects the active workspace's scope.** For a NodeSet tab it
  filters the loaded payload through the tab's own predicate (induced
  subgraph), so "what am I looking at" is literally the active tab. It does
  **not** additionally subtract graph-filter visibility (stub toggle,
  per-domain ●/○ hides) — those are render-time view options, and Inventory
  surveys the loaded/scoped set, matching how `graphStore.nodeCount` already
  counts.

## Deferred counts (blocked on upstream items)

- **Crawled / uncrawled / dead split** — only crawled (`!stub`) / uncrawled
  (`stub`) ship now. The three-way split with `dead` waits on the
  `resources.state` machine from the Schema Reset (item 6); the spec already
  notes Inventory inherits it when item 6 lands.
- **Labeled count** — shipped by
  [`../2026-06-10-label-system/outcome.md`](../2026-06-10-label-system/outcome.md).
  The available
  `category` field (LLM analysis category) ships as the **Categorized** count
  instead — related but distinct from analyst labels.
</content>
