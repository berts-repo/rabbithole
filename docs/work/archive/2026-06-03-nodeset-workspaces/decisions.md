# Decisions — NodeSet Workspaces

Owner-recommended defaults are recorded in the spec's "Deferred Decisions".
This package adopts them; each is a technical/product default the analyst can
revisit, not a blocking choice.

- **Frontend-filtered (spec option 2).** NodeSet tabs filter the already-loaded
  global payload client-side. No scoped-payload endpoint. Revisit only if graph
  size outgrows the frontend memory budget.
- **Induced subgraph, drop outside edges.** A tab shows only edges whose *both*
  endpoints are in the set — which is exactly what `visibilityController`'s edge
  pass already does. No "show 1-hop neighbours" toggle in v1.
- **Inherit metrics.** PageRank / betweenness / clusters are read from the full
  payload, not recomputed over the subgraph.
- **Derived sources re-derive; captured sources freeze members.** Domain and
  hidden re-evaluate on every compute (new matches appear). Flag, fingerprint,
  bookmarks, and selection freeze their member set at open; reopening the same
  source re-captures.
- **All nodeset tabs persist across sessions.** Derived tabs persist their
  descriptor and re-derive on reload; captured tabs persist their literal member
  list. One persistence path instead of an ephemeral/pinned split — smaller code,
  and the spec's persistence note already says derived re-derive while selection
  persists literal ids.
- **Dedup by source signature.** Reopening a domain/fingerprint/hidden/bookmarks
  source focuses the existing tab (and re-captures members) rather than stacking
  duplicates. Distinct selections / distinct flag filters are distinct tabs.

## Hidden source — engine-ready, no v1 consumer

The spec lists **Hidden** as an openable source, but it does not satisfy the
spec's *own* gating rule ("members guaranteed to be in the loaded payload"):

- The bottom-pane **Hidden** tab manages server-side `graph_filters` substring
  terms. The backend matches them during `/api/graph` build and **excludes**
  matching nodes from the payload. A frontend-only nodeset tab over the global
  payload therefore cannot show them — it would be empty.
- The `domainVisibilityStore` ●/○ hides are *client-side*: those nodes **are**
  in the payload and the engine can show them (the `setScope(..., {
  includeHidden })` path + the `{ kind: 'hidden' }` predicate). But there is no
  bottom-pane *list* of client-hidden nodes to hang an affordance on.

Decision: ship the engine capability (it is the documented, unit-tested seam,
mirroring how item 3 shipped `setScope` ahead of its first consumer) but do
**not** wire a Hidden consumer in v1 — shipping one would be a broken/empty
affordance. A real consumer needs either a backend opt-in that returns
server-hidden nodes with a flag, or a dedicated "review what I've hidden"
surface for the client-side hides. Tracked in `handoff.md`.

## Deferred to follow-ons (unchanged from spec)

- Label and label-query sources — shipped by
  [`../2026-06-10-label-system/outcome.md`](../2026-06-10-label-system/outcome.md).
- Local crawled-content search results — wait for F5 (item 9).
- Live Crawl and external search are intentionally excluded, not deferred.
