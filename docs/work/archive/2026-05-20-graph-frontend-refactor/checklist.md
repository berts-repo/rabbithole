# Graph Frontend Refactor — Must-Not-Regress Checklist

Phase 0 deliverable of `docs/work/archive/2026-05-20-graph-frontend-refactor/plan.md`.
Date: 2026-05-20

This is the regression net for the graph refactor (Phases 1–3). Run the
**Baseline checks** after every extraction slice; walk the **Behavior
checklist** before merging a slice; and treat the **Hazards** section as the
list of subtle behaviors that no automated test currently guards — they live
only in code comments today, so an extraction that "looks equivalent" can
silently break them.

Extraction rule (from the plan): move code, do **not** change behavior. If a
slice needs a behavior change, that is a separate, separately-reviewed commit.

---

## Baseline checks (run after every slice)

Captured 2026-05-20 on `feat/f4b-toolbar-modals` before any refactor:

| Check | Command | Baseline result |
|-------|---------|-----------------|
| Type/Svelte check | `cd frontend && npm run check` | 0 errors, 0 warnings (3820 files) |
| Production build | `cd frontend && npm run build` | clean — `bundle.js` 460.71 kB, `bundle.css` 41.29 kB |
| Single-bundle invariant | inspect `backend/public/` | exactly one `bundle.js` + one `bundle.css`, no chunks |
| Graph backend tests | `cd backend && .venv/bin/python -m pytest tests/test_b6_graph.py tests/test_b7_graph_filters.py tests/test_b5a_kill_switch.py tests/test_b7_flags.py tests/test_b7_collections.py -q` | 113 passed |

A slice is not done until `check` and `build` are clean and the backend
tests above still pass (run the backend set only if a slice touched a route
contract).

---

## Behavior checklist (walk before merging a slice)

Grounded in `frontend/src/components/graph/GraphCanvas.svelte` and
`frontend/src/lib/stores/graph.svelte.ts` as of 2026-05-20.

### A. Workspace switching
- [ ] Switching workspace tabs forces a full `rebuildInto`, never `applyDiff` (`graph.svelte.ts` `applyPayload`, `workspaceSwitched` guard). Symptom if broken: switching a large Global tab → a small collection freezes the browser (O(n²) one-by-one node-drop refresh storm).
- [ ] On tab switch the camera either snaps to the snapshot's saved camera state, or `animatedReset`s when none was saved (`consumePending()` in the version `$effect`).
- [ ] Custom bbox is cleared on tab switch so the new tab's layout fits.
- [ ] First visit to a tab with no cached payload shows the "Loading workspace…" skeleton; a tab with a cached payload renders instantly with no skeleton.
- [ ] `expandedDomains` (double-clicked-open clusters) does not bleed across tabs.

### B. SWR payload restore (15 s poll)
- [ ] A poll preserves node positions — nodes do not scatter or re-layout.
- [ ] A poll preserves the camera — no re-fit, no zoom jump.
- [ ] A poll preserves the current selection and ego-focus.
- [ ] User-dragged nodes (`userPositioned`) stay where the analyst put them across polls and across a cluster-transition rebuild.
- [ ] Diff path vs. rebuild path both land a correct graph (see Hazard 6).

### C. Selection
- [ ] Plain left-click highlights the node and opens the right panel `page` view; it does **not** enter ego-focus.
- [ ] Ctrl/Cmd+click and Shift+click toggle multi-select.
- [ ] Clicking empty canvas (`clickStage`) clears the selection.
- [ ] Selected nodes render bright green (`#39ff14`); the highlighted/focus node gets an extra size bump.
- [ ] Ctrl+A with ≤50 visible nodes selects all immediately; with >50 it shows the confirmation modal.

### D. Draw-edge flow
- [ ] Toolbar Draw-edge with ≥2 nodes selected opens the batch modal immediately.
- [ ] Toolbar Draw-edge with <2 selected enters sequential canvas-pick mode.
- [ ] Sequential mode: first node click sets source, second (different) node opens the sequential edge modal.
- [ ] Cluster nodes cannot be picked as a draw-edge endpoint.
- [ ] Escape cancels an in-progress draw-edge (highest-priority Escape branch).
- [ ] Creating an edge triggers an immediate `graphPoller.refresh()` so the edge appears without waiting for the next poll.

### E. Right-click actions
- [ ] Right-click on a node opens the single-node menu; right-click on a node inside a ≥2 selection opens the multi-select menu.
- [ ] Right-click on an analyst (dashed) edge opens the edge menu; right-click on a crawl-derived edge is a no-op but still suppresses the browser context menu.
- [ ] Right-click on a cluster node suppresses the browser menu but opens no menu.
- [ ] Single-node menu gating: "Open in Tor Browser" disabled unless kill-switch armed; "Queue Crawl" disabled unless stub; "Hide from Graph" disabled on stubs.
- [ ] Multi-select menu gating: "Crawl selected" disabled with no stubs; "Mark Reviewed" / "Hide All" disabled with no crawled nodes; counts in labels match the selection.
- [ ] Every action surfaces a success or error toast; "Delete analyst edge" removes the edge immediately.
- [ ] Menu sections re-derive on selection change (counts/reasons) and on graph version (a poll that removed the edge closes a stale edge menu).

### F. Kill-switch trip and resume
- [ ] When the kill-switch is not armed, "Open in Tor Browser" is disabled with the "Tor not connected" reason.
- [ ] When armed but the backend rejects at exec time, the 409/412/422 surfaces as a readable toast (not a silent failure).
- [ ] Graph polling behavior across a kill-switch trip/resume is unchanged (verify against `graphPoller` — the plan flags this as a high-risk interaction).

### G. Filter shelf
- [ ] `showStubs` toggle rebuilds graphology structurally and re-fans the stub halo; fetched-node positions stay put (no FA2 re-layout).
- [ ] `groupByDomain` toggle rebuilds structurally; toggling it off clears `expandedDomains`.
- [ ] Double-click a cluster expands it; double-click a grouped member (groupByDomain on, domain has ≥2 fetched members) collapses the domain.
- [ ] Visual-only filters (maxHops, hideOrphans, mutualOnly, showAllEdges, edgeMode, colorMode, flaggedBorders, isolate, bridgeHighlight + thresholds) only refresh reducers — no structural rebuild, no position drift.
- [ ] Toolbar visible-count status line matches what is actually rendered after each filter change.

### H. Layout stop and reset
- [ ] A layout runs once on first paint; subsequent polls do not re-layout.
- [ ] Reset button re-randomizes positions and re-runs the active layout.
- [ ] Layout-picker change re-runs the newly picked layout.
- [ ] Stop button freezes an in-flight ForceAtlas2 settle at its current frame.
- [ ] Fit button animated-resets the camera without re-laying-out.
- [ ] A fetched subgraph above `MAX_AUTO_LAYOUT_NODES` (3000) skips auto-layout and shows the warning toast; Reset still forces a layout.
- [ ] `F` key focuses the node under the cursor, falling back to the highlighted selection; no-op when neither exists.

---

## Hazards (comment-only — no automated test guards these)

These are the subtle behaviors most likely to be broken by a "looks
equivalent" extraction. Each must survive Phases 1–3 intact.

1. **Stable graphology instance.** `graphInstance` in `graph.svelte.ts:85` is
   created once and never reassigned. Sigma binds to it once and reuses one
   WebGL context for the page's lifetime. Swapping the reference forces Sigma
   to kill its renderer and recompile shaders — 10-20 s on SwiftShader. Any
   model-layer extraction must keep this single stable instance and mutate it
   in place.

2. **`untrack` around every effect-driven refresh.** Every
   `renderer.refresh()` / `applyPayloadAndLayout()` called from an `$effect`
   is wrapped in `untrack()` (see the block at `GraphCanvas.svelte:2011`).
   Sigma's reducers read `$state` (selection, `hoveredNode`,
   `hoverNeighbours`) on every refresh. Without `untrack`, those reads
   register as dependencies of the triggering effect → spurious re-runs, and
   in one case an infinite update loop. When interaction/runtime code moves
   out, the `untrack` boundary must move with it.

3. **`tooltipPos` / `tooltipText` are deliberately split.** `tooltipText` is
   written only from `refreshHover` (mouse enter/leave); `tooltipPos` only
   from the `afterRender` hook. The old combined `{x,y,text}` shape had
   `afterRender` both reading `.text` and writing the object, closing a
   refresh → afterRender → write → effect-rerun loop that only stopped at
   Svelte's `effect_update_depth_exceeded` guard (~10-20 s freeze). Do not
   re-merge them.

4. **Hover fade/hold strobe.** The `HOLD_MS` (250 ms) hold-dim window in
   `refreshHover` exists so flicking the cursor node-to-node does not strobe
   the background bright→dark→bright. The enter branch carefully picks where
   the dim-in starts across four cases (`heldFrom`, `fadeFrom`,
   `hoverStartTs !== null`, `prev === null`). The strobe bug is restarting
   the fade-in from a fully-bright background on every hovered-node change.
   An interaction-layer extraction must preserve all four branches exactly.

5. **rAF fade loop + timer teardown.** `tickFade` self-cancels when no fade
   is active; `fadeRafId` and `holdTimerId` are cleared in the `onMount`
   cleanup. An extraction that moves the fade loop must keep both the
   self-cancel and the unmount teardown, or it leaks a rAF loop / timer.

6. **`applyDiff` bail conditions are correctness-critical.** `applyDiff`
   returns `false` (→ caller falls back to `rebuildInto`) whenever cluster
   topology or stub visibility would change. The bail checks (cluster-domain
   set equality, stub-visibility flip) must not be loosened — a too-eager
   diff corrupts the rendered graph.

7. **Custom bbox lock after layout.** `finishLayout` clears the bbox, lets
   `autoRescale` fit, then re-locks a custom bbox. The re-lock stops Sigma's
   resize handler (fired when the right panel auto-expands on a click) from
   re-fitting and jumping the camera. The clear → refresh → re-lock order
   matters.

8. **`enableEdgeEvents: true` is intentional.** Sigma runs with edge events
   on purely so `rightClickEdge` fires for the analyst-edge menu. It is a
   per-frame edge-picking cost accepted on purpose — do not "optimize" it
   away.

9. **Synchronous ForceAtlas2 + WebGL probe.** Layout settles synchronously
   (no rAF animation): animating the settle pinned the CPU under SwiftShader
   and made clicks miss because `autoRescale` re-fitted every frame. The
   WebGL probe before `new Sigma(...)` surfaces a readable error instead of
   Sigma's opaque `null.blendFunc` crash.

10. **Page-visible / window-focus refresh.** `onPageVisible` / `onWindowFocus`
    force a `refresh()` and clear `egoCache`. Without them, returning to a
    backgrounded tab with ego-focus active shows only the focus node until a
    click (Sigma's rAF is paused while the tab is hidden).

11. **`dragHappened` click-swallow.** Drag-to-move is hand-rolled (Sigma 3
    has no node drag). `dragHappened` swallows the drag-trailing `clickNode`;
    the camera is disabled mid-drag and re-enabled on `mouseup`; the 4 px
    threshold separates click from drag. All three must move together.

12. **`NODE_SPACING` cross-file coupling.** `NODE_SPACING = 6` in
    `graph.svelte.ts` is documented to match a layout constant in
    `GraphCanvas.svelte`. If a layout/model extraction relocates either,
    keep them in sync or unify them into one shared constant.

---

## Sign-off

- [x] **Phase 1 (GraphCanvas runtime extraction) — done 2026-05-20.** Extracted `probeWebGL` + `createGraphRenderer` (with `BorderedNodeProgram` and `drawDarkNodeHover`) to `lib/graph/runtime/sigmaRuntime.ts`, and `graphBBox` + `fitView`/`restoreView`/`refitToGraph` to `lib/graph/runtime/camera.ts`. `GraphCanvas.svelte` 2386 → 2249 lines. Pure code move — `npm run check` 0/0, `npm run build` clean (single bundle). Hazards re-verified by inspection: 1 (renderer still binds the one stable `graphStore.graph()` instance), 7 (`refitToGraph` keeps the clear→autoRescale→refresh→re-lock order), 8 (`enableEdgeEvents` preserved), 9 (probe runs before construction, same message/gate), 10 (page-visible/focus handlers untouched). Event handlers and reducers stayed in the component — Phase 2 scope.
- [x] **Phase 2 (interaction policies extraction) — done 2026-05-20.** Extracted graph-canvas interaction policy into `frontend/src/lib/graph/interactions/`: `contextMenu.ts` (single-node + multi-select menu builders, pure and handler-injected), `drawEdge.ts` (`resolveDrawEdgeRequest` + `resolveDrawEdgeClick`), `egoFocus.ts` (`computeEgoReachable` BFS + `shortestPathEdges`), `keyboard.ts` (`classifyGraphKey`), `selection.ts` (`isMultiSelectModifier`, `shouldOpenMultiMenu`). `GraphCanvas.svelte` 2249 → 2112 lines; the act\*/open\*Modal action wiring, handler factories, and Sigma event registration stayed in the component. Shipped as four slices (2a–2d), each a pure code move — `npm run check` 0/0 and `npm run build` clean (single `bundle.js` + `bundle.css`) after every slice. Added Vitest as the frontend unit-test runner (`npm test`, standalone `vitest.config.ts`) with 44 tests over the extracted modules (menu eligibility, draw-edge state machine, BFS/shortest-path, key classification, click rules). Hazards 2, 3, 4, 5, 11 re-verified by inspection — the interaction-*policy* extraction is orthogonal to the hover/fade/drag/tooltip machinery: `refreshHover`, `tickFade`/`startFadeLoop`, the `tooltipPos`/`tooltipText` split, the drag handlers, and the `onMount` teardown were untouched; hazard 2's `untrack` wrapper on the draw-edge toolbar effect was preserved verbatim. Behavior preservation verified by inspection + unit tests, not a live app walk.
- [x] **Phase 3 (`graph.svelte.ts` model split) — done 2026-05-21.** Split `frontend/src/lib/stores/graph.svelte.ts` into a thin rune-state owner plus pure model modules under `lib/graph/model/`: `clusterDomain.ts` (cluster key scheme + `synthesizeClusterRaw`), `geometry.ts` (`nodeSize`, `haloOffset`, `sunflowerAround`, `NODE_SPACING`, `positionStubsAroundParents`), `applyPayload.ts` (`rebuildInto` + `applyDiff`, taking a `ClusterFilterOptions` snapshot rather than reading `graphFiltersStore` directly so the transforms stay rune-free), and `graphCounts.ts` (`deriveStructuralCounts`). `graph.svelte.ts` 787 → 233 lines — it now owns only the rune state, the stable `graphInstance`, the `currentClusterOptions()` snapshot helper, and the public `graphStore` surface; the apply paths and count derivation are imported. Shipped as four pure-code-move slices (3a–3d); `npm run check` 0/0 and `npm run build` clean (single `bundle.js` + `bundle.css`) after each. Vitest coverage grew 44 → 78 tests — added `clusterDomain.test.ts` (9), `geometry.test.ts` (10), `applyPayload.test.ts` (12), `graphCounts.test.ts` (3), all driven by plain payload/graph fixtures with no runes. Hazards re-verified: **1** — `graphInstance` is never reassigned; the apply paths mutate the `g` parameter in place and the store always passes its one stable instance, never swaps it. **6** — `applyDiff`'s two bail conditions (cluster-domain set equality + stub-visibility flip) moved verbatim into `applyPayload.ts` and are now covered by `applyPayload.test.ts`. **12** — resolved in slice 3b: the duplicate `NODE_SPACING` local const is gone; `geometry.ts` holds the single definition and `radial.ts` + `applyPayload.ts` import it. Behavior preservation verified by inspection + unit tests, not a live app walk.
- [x] **Phase 4 (API client split) — done 2026-05-21.** Split the monolithic `frontend/src/lib/api/` (~630 lines) into a directory `frontend/src/lib/api/`: `core.ts` (`BASE`, `ApiError`, `apiFetch`, `qs` — the fetch machinery, moved verbatim), `types.ts` (all 40 response + request types), and ten per-domain route modules — `health.ts`, `projects.ts` (incl. `getStats`), `settings.ts`, `crawl.ts` (seeds + schedules + crawl + SSE path constants), `watchlist.ts`, `nodes.ts` (nodes + flags + external launch), `graph.ts` (graph payload + graph-filters + edges + export path constants), `collections.ts`, `monitors.ts`, `analyses.ts`. An `index.ts` barrel re-exports `ApiError`, every type, and every route function/path constant; `$lib/api` now resolves to the barrel, so all 34 import sites were untouched (no call-site changes). Shipped as two pure-code-move slices (4a–4b); `npm run check` 0/0, `npm run build` clean (single `bundle.js` + `bundle.css`), and `npm test` green after each. The 89-name public export surface was diffed before/after — identical (`BASE`/`apiFetch`/`qs` stay module-internal, as before). Vitest coverage grew 78 → 85 tests — added `api/core.test.ts` (7) over `qs()` query-string building (null/undefined skipping, key+value encoding, empty input). Behavior preservation verified by inspection + the export-surface diff + unit tests, not a live app walk.
