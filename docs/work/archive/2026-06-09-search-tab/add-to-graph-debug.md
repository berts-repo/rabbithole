# "Add to Graph" — node created but never renders on the canvas

Status: **RESOLVED.** The node *was* rendering all along — it was painted in a
colour indistinguishable from the canvas background, with no border and no
label, so an edgeless orphan was invisible.

## ROOT CAUSE (the thing every prior theory missed)

`reducerController.nodeReducer` painted every uncrawled placeholder
`#0d1916` (the "render hollow" fill). The canvas background `--bg` is
`#0a0f0d` — the two are near-identical near-black greens. Compounding it:

- the default Sigma node program draws **no border** (the `bordered` program
  was opted into only for *flagged* nodes), so the hollow fill had no outline;
- `labelRenderedSizeThreshold: 6` + uncrawled `nodeSize` of `2.5` means these
  nodes draw **no label** either.

A *halo* stub survives this because it sits beside a bright crawled parent with
a connecting edge — you read its position from context. An **orphan** uncrawled
node (the "Add to Graph" case: no parent, no edge, no bright neighbour) is a
2.5px near-black dot on a near-black field: present, framed, counted, invisible.
That is exactly why every static trace concluded "it renders" while the screen
looked empty, and why it survived Reset / fit / refresh — the camera framed
nodes you simply couldn't see.

Verified live this session: `GET /api/graph` (the real route, authed with the
browser's own per-process token, not just `build_payload` in isolation) returns
all 6 nodes, HTTP 200. The data reaches the client. The backend is fully
correct, route included.

## FIX

`reducerController.ts` — uncrawled placeholders now render as a genuine hollow
*ring*: the dark `#0d1916` fill plus a faint `#2eb89a` border via the existing
`bordered` program (a flag ring, if present, still wins). Regression tests in
`reducerController.test.ts` (`uncrawled renders hollow with a visible ring`,
`flag ring wins over the uncrawled hollow ring`). 23/23 pass; svelte-check clean.

The prior-session fixes below were all real and complementary — each removed a
*different* reason the node wouldn't show (missing from payload / filtered out /
not framed). The ring is the final piece that makes the now-present, unfiltered,
framed node actually visible.

---

## Original investigation notes (kept for context)

Backend is confirmed correct. Bug was isolated to **frontend rendering of
uncrawled, edgeless nodes**.

## Symptom (reported by user)

1. Create a new project.
2. Run a Search-tab query (outbound onion search).
3. Right-click an uncrawled result → **Graph › Add to Graph**.
4. The header **node-count indicator goes up**, but the **graph canvas stays empty**.
5. Persists after: pressing **Reset**, manual **fit/zoom-out**, and a **page refresh**.

## What "Add to Graph" does

- Frontend menu action `actAddToGraph(url)` (`frontend/src/lib/contextMenu/actions.ts`)
  → `createStubNode({ url })` → `POST /api/nodes` → `resources_db.upsert_resource(state='known')`.
- A `known` resource **is** a graph node (`backend/backend/db/graph.py` `build_payload`
  selects one row per resource, **no state filter**).

## CONFIRMED FACTS (verified this session, not theory)

### Data is the same source and is correct
- Active project: `test_searchengine`
  (`/home/guy/.local/share/rabbithole/projects/scans/test-searchengine.db`,
  `active_id` in `/home/guy/.local/share/rabbithole/projects/projects.json`).
- DB has 6 resources, **all `state='known'`**, 0 edges. No `graph_filters` (Hidden) terms.
- Persisted setting `graph.show_uncrawled = true`.
- Running the real builder against the live DB returns all of them, well-formed:
  ```
  .venv/bin/python -c "from backend.db.core import CrawlDB; from backend.db.graph import build_payload; \
    p=build_payload(CrawlDB('/home/guy/.local/share/rabbithole/projects/scans/test-searchengine.db')); \
    print(len(p['nodes']), len(p['edges']))"
  # -> 6 0
  ```
  Each node has valid `id, label, raw_url, color, domain, state='known',
  in/out_degree_count=0, depth=null`. (Note: payload key is `raw_url`, not `url`.)

### The count vs. graph divergence (the user's own diagnosis: "reading the same data?")
- **Node count** comes from `/api/stats` → reads DB directly → rises correctly.
- **Graph** comes from `/api/graph` → served from an in-memory **server-side
  `graph_cache`** (`backend/backend/services/graph_cache.py`,
  `request.app.state.project_state.graph_cache`, used in `backend/backend/routes/graph.py` `_payload`).

## FIXES ALREADY APPLIED (committed to working tree, NOT yet git-committed)

### Backend (this was a real root-cause bug, now fixed)
- `backend/backend/routes/nodes.py` `create_node`: added `request: Request` param +
  `request.app.state.project_state.graph_cache.invalidate()` after the upsert.
  **Reason:** `POST /api/nodes` was the *only* node-mutating route that never busted
  the graph cache (flags/edges/domains/crawler/reviewed/analysis_excluded all do).
  So `/api/graph` kept returning the stale pre-node payload.
- Regression test: `backend/tests/test_b5c_routes.py::test_create_node_invalidates_graph_cache`
  (asserts build happens twice AND the new node is in the payload). Passes.
- Backend suite green (node + b5c tests: 48 + 29 pass).

### Frontend hardening (symptom-level, all reasonable to keep)
- `actAddToGraph` (`frontend/src/lib/contextMenu/actions.ts`):
  - Reveals uncrawled nodes when hidden: `graphFiltersStore.setShowUncrawled(true)`,
    toast says "Added to graph — now showing uncrawled nodes".
  - `workspaceSnapshots.invalidatePayloads()` (mirror of `actHideFromGraph`) so the
    client SWR snapshot cache can't re-serve a stale payload on tab switch.
- `frontend/src/lib/contextMenu/RowContextMenu.svelte` `ensureNodeId`: also calls
  `workspaceSnapshots.invalidatePayloads()` after minting a stub (same class of bug
  for Add to Collection / Flag / etc. on uncrawled rows).
- `frontend/src/components/graph/GraphCanvas.svelte` `applyPayloadAndLayout`: in the
  `fetchedCount === 0 && g.order > 0` branch (all-uncrawled graph, e.g. fresh project),
  now calls `fitView(renderer)` — previously it set `firstLayoutDone=true` and framed
  nothing.
- `svelte-check` clean; `frontend` contextMenu + applyPayload tests pass.

### Earlier same-session feature work (context, already done & green)
- Capability system for the shared row menu (`MenuCapability` in
  `frontend/src/lib/contextMenu/sections.ts`), per-surface opt-in. Search tab declares
  intake-only vs crawled cap sets in `frontend/src/views/SearchTab.svelte`.
- The `addToGraph` capability/handler itself (opt-in only; never on graph/bottom-pane).
- Tests in `frontend/src/lib/contextMenu/sections.test.ts` (27 pass).

## STILL BROKEN AFTER ALL OF THE ABOVE

User restarted backend (to clear stale in-memory cache) and reports **"same problem."**
Backend now provably returns the 6 nodes. So the remaining bug is **client-side
rendering of uncrawled, zero-degree nodes**, OR the client isn't actually receiving
the fresh payload (verify first — see step 1 below).

## NEXT STEPS (in priority order)

1. **Confirm the browser actually receives 6 nodes.** In devtools Network, inspect the
   `GET /api/graph` response while on the project. If it's empty → frontend/proxy/auth
   or dev-server-not-rebuilt issue, not rendering. If it has 6 nodes → it's rendering.
   - Also confirm the Vite dev server picked up the edits (HMR/restart `make dev-frontend`)
     and the backend restart actually ran the patched `create_node`.

2. **Trace client render of the 6 orphan stubs.** Files & path:
   - `frontend/src/lib/graph/model/applyPayload.ts` `rebuildInto`: Pass 1 skips uncrawled;
     **Pass 2 is gated on `showUncrawled`** and, with no parent edges, routes them to the
     `orphanStubs` branch → `addNode` with `x/y = Math.random()`, `parent_id: null`.
     VERIFY `showUncrawled` is actually `true` in `currentClusterOptions()` at rebuild time
     (the store value, not just the persisted setting — check load/race in
     `frontend/src/lib/stores/graphFilters.svelte.ts`, loaded in `frontend/src/app.svelte`).
   - `frontend/src/lib/graph/controllers/visibilityController.ts` `compute()` (lines ~94-172):
     orphan uncrawled nodes should pass (defaults: `hideOrphans=false`, `mutualOnly=false`,
     `maxHops=0`, no reachable set, no domain hides, no scope predicate). CONFIRM none of
     these drop them. `hideOrphans` (line 156, drops `i+o===0`) is the prime suspect IF a
     default or persisted value is true — check `domainVisibility`/nodeSet scope too.
   - `frontend/src/lib/graph/controllers/reducerController.ts` `nodeReducer`: hides when
     `!deps.isVisible(node)`. If visibility excludes them, they render `hidden:true`.
   - `frontend/src/components/graph/GraphCanvas.svelte`: `countFetchedNodes` only counts
     non-uncrawled (so `fetchedCount===0` here); the `applyPayloadAndLayout` branches and
     the `showUncrawled` effect (line ~418) call `rebuildFromCurrentPayload`. Camera fit
     just added for this case.

3. **Cheapest decisive probe:** in the running app console, check
   `graphStore.graph().order` (graphology node count) and whether the visible set is empty.
   - If `order === 0` → nodes never entered graphInstance → `showUncrawled` was false at
     rebuild (store/race) OR applyPayload took a path that skipped them.
   - If `order === 6` but canvas empty → visibility/reducer hiding them, or positions/camera.
   This single check splits the remaining problem in half.

## Key file map

- Backend graph payload: `backend/backend/db/graph.py` (`build_payload`, `_load_data`).
- Backend graph route + cache: `backend/backend/routes/graph.py`, `backend/backend/services/graph_cache.py`.
- Node create endpoint: `backend/backend/routes/nodes.py` (`create_node`).
- Client payload→graphology: `frontend/src/lib/graph/model/applyPayload.ts`.
- Client visibility/reducer: `frontend/src/lib/graph/controllers/{visibilityController,reducerController}.ts`.
- Canvas orchestration: `frontend/src/components/graph/GraphCanvas.svelte`.
- Filters store + defaults: `frontend/src/lib/stores/graphFilters.svelte.ts` (DEFAULTS.showUncrawled=false).
- Add-to-graph action: `frontend/src/lib/contextMenu/actions.ts` (`actAddToGraph`).

## Process note for next session
Three client-side theories were wrong before the disk inspection found the backend cache
bug. **Inspect live data first** (DB on disk, the actual `/api/graph` response in the
browser, `graphStore.graph().order` in console) before changing code.
