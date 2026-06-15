# F8 — Search tab completion (item 10)

Active package. Completes the **Search** tab: outbound discovery of new `.onion`
URLs by querying dark-web search engines through Tor, results streaming in over
SSE. This is the *outbound* counterpart to the *inbound* **Find** sub-tab (item
9, closed 2026-06-09) — terminology fixed by item 8.5, see
[`docs/specs/naming.md`](../../../specs/naming.md) §"Search vs. Find".

Search stays its own top-level tab (peer of the Graph tab) — not folded into
another pane. Search results do **not** become a NodeSet workspace tab — see
[`../../archive/2026-06-03-nodeset-workspaces/source-spec.md`](../../archive/2026-06-03-nodeset-workspaces/source-spec.md)
for why.

Spec: [`docs/specs/search-tab.md`](../../../specs/search-tab.md).

## What exists vs. what this builds

The backend SSE engine search is **already built and wired** — this is a
frontend-heavy completion, not a from-scratch build.

- **Backend (built):** `routes/harvest_search.py` (`GET /api/harvest/search`)
  drives per-engine queries through Tor, a bounded probe stage for uncrawled
  URLs (title/meta-description), `search.passive_mode` honoring, and the SSE
  event stream (`probe` / `done` / `error` / `all_done`). Engine CRUD lives in
  `routes/search_engines.py`; its management UI already ships in the Settings
  modal → Engines tab (item 8, `components/modals/settings/EnginesTab.svelte`).
- **Frontend (stub):** `views/SearchTab.svelte` is a 22-line placeholder. The
  whole spec surface is unbuilt here: search bar + Search/Stop, the engine +
  Passive source-selector row with per-source status badges, the streaming
  results list (crawled vs. uncrawled rows), both action bars, and the empty
  states.

## Action wiring

Each result row keeps **one inline button** for its primary verb and routes
everything else through the **shared row right-click menu** (`$lib/contextMenu`)
— the same menu the graph and bottom-pane sub-tabs use. This menu centralization
shipped as part of this package; see
[`source-centralize-context-menu.md`](source-centralize-context-menu.md). The
unified Activity tab from item 6 owns the resulting work.

- **Crawled rows:** inline **→ Graph** (switch + highlight); right-click menu
  carries the node (plus its known id) for Copy / Open in Tor / Flag / Queue
  Analysis / Add to Collection / Focus.
- **Uncrawled rows:** inline **Send to Crawl** (switch to the Crawl sub-tab,
  load the URL into the manual single-URL input); right-click menu carries only
  the URL and mints a stub node on demand the first time an id-bound action runs
  (never speculatively, so browsing results doesn't pollute the graph).

## Read order

1. [`outcome.md`](outcome.md) — what shipped (start here)
2. This README + [`checklist.md`](checklist.md) + [`handoff.md`](handoff.md)
3. [`source-centralize-context-menu.md`](source-centralize-context-menu.md) —
   the right-click-menu centralization that shipped alongside this tab
4. [`docs/specs/search-tab.md`](../../../specs/search-tab.md) (intent)
5. `backend/backend/routes/harvest_search.py` (the SSE contract consumed)
6. `frontend/src/views/SearchTab.svelte` +
   `frontend/src/lib/api/engines.ts`
7. `frontend/src/lib/contextMenu/` (the shared row menu the tab now uses)

## Status

**Closed 2026-06-09** — see [`outcome.md`](outcome.md). The only open item is
the owner's in-app manual sweep (the last unchecked line in
[`checklist.md`](checklist.md)); everything build/test-verifiable is green.
