# Graph Frontend Refactor Plan

Status: reviewed — Option B adopted (see Recommendation)
Date: 2026-05-20
Scope: frontend graph/explore path first, with adjacent API and backend cleanup seams called out where they materially reduce frontend complexity

## Why This Refactor Is Worth Doing

The graph/explore path is the most mature and most valuable part of the app, but it is still organized like a fast-moving implementation phase instead of a stabilized product surface.

Current pressure points:

- `frontend/src/components/graph/GraphCanvas.svelte` is the dominant complexity hotspot.
- `frontend/src/lib/stores/graph.svelte.ts` mixes payload transforms, graph instance lifecycle, cluster synthesis, visibility logic, and rebuild/diff policy.
- `frontend/src/lib/api/` is becoming a monolithic service boundary instead of a domain-organized client.
- Toolbar, context menu, modal orchestration, workspace restore, filters, selection, and kill-switch behavior all intersect inside the graph feature, but their ownership lines are still blurry.
- Several surrounding app surfaces are still placeholders, so future work will tend to pile more responsibilities into the existing graph modules unless the graph area is normalized first.

This refactor should reduce change risk, improve testability, and make future feature work in F5-F8 cheaper.

## Refactor Goals

1. Shrink the graph feature’s blast radius for routine changes.
2. Split rendering, interaction, orchestration, and persistence concerns into named modules with clear ownership.
3. Preserve the current user-facing behavior during the refactor.
4. Make the graph feature testable in smaller units without requiring full canvas integration tests for every change.
5. Normalize the API and store layer so new features stop extending giant files.

## Non-Goals

1. No redesign of the graph product behavior by default.
2. No “rewrite from scratch” of Sigma/Graphology integration.
3. No broad migration of unfinished placeholder surfaces unless they are needed to complete a seam extraction.
4. No schema changes unless a backend seam becomes impossible to cleanly isolate without them.

## Current Hotspots

### Frontend

- `frontend/src/components/graph/GraphCanvas.svelte`
  It appears to own too many responsibilities at once:
  camera lifecycle, Sigma lifecycle, reducers, interaction handlers, right-click behavior, keyboard behavior, selection semantics, draw-edge flow, modal state, layout restore, optimistic refresh handling, and render-specific UI logic.

- `frontend/src/lib/stores/graph.svelte.ts`
  It appears to own both state and heavy transformation logic:
  payload caching, cluster synthesis, structural filtering, graph instance rebuilds, diff-apply policy, counts, and workspace-aware rebuild policy.

- `frontend/src/lib/api/`
  A single large file (~630 lines) for every route surface. It was still well-organized with clear section banners, so this was a "scales poorly as unfinished surfaces come online" risk rather than an active problem. ~25 files import from it — Phase 4 split it into `lib/api/` behind an `index.ts` barrel, so the call sites were untouched (see Phase 4).

- `frontend/src/lib/stores/workspace.svelte.ts`
- `frontend/src/lib/stores/workspaceSnapshots.svelte.ts`
- `frontend/src/lib/stores/graphFilters.svelte.ts`
  These are useful seams already, but they still leak graph-specific coordination logic back into larger components.

### Backend-adjacent seams worth noting

- Many backend read paths use `db._lock` and `db._conn` directly.
- Route and DB boundaries are mostly disciplined, but the DB access pattern is not yet standardized enough to serve as a clean long-term contract.
- This is not the first refactor target, but it should be queued immediately behind the frontend pass.

## Target Architecture

The graph feature should become a small feature package with explicit internal layers.

### 1. Graph Runtime Layer

Owns:

- Sigma creation/destruction
- camera control
- reducer registration
- render refresh hooks
- DOM and renderer lifecycle

Candidate modules:

- `frontend/src/lib/graph/runtime/sigmaRuntime.ts`
- `frontend/src/lib/graph/runtime/camera.ts`
- `frontend/src/lib/graph/runtime/reducers.ts`

### 2. Graph Model Layer

Owns:

- raw payload state
- graphology instance lifecycle
- payload diff/rebuild policy
- cluster synthesis
- structural transforms
- visible count derivation

Candidate modules:

- `frontend/src/lib/graph/model/graphModel.ts`
- `frontend/src/lib/graph/model/applyPayload.ts`
- `frontend/src/lib/graph/model/clusterDomain.ts`
- `frontend/src/lib/graph/model/graphCounts.ts`

This is the best place to reduce the size of `graph.svelte.ts`.

### 3. Graph Interaction Layer

Owns:

- click, double-click, hover, drag, and context-menu behavior
- keyboard shortcuts
- selection semantics
- draw-edge flow
- ego focus behavior
- node and edge action eligibility

Candidate modules:

- `frontend/src/lib/graph/interactions/selection.ts`
- `frontend/src/lib/graph/interactions/contextMenu.ts`
- `frontend/src/lib/graph/interactions/drawEdge.ts`
- `frontend/src/lib/graph/interactions/egoFocus.ts`

### 4. Graph UI Orchestration Layer

Owns:

- toolbar actions
- filter shelf open/close state
- graph modal coordination
- status chip logic
- workspace bridge behavior

Candidate modules:

- `frontend/src/lib/graph/ui/toolbarState.ts`
- `frontend/src/lib/graph/ui/modalCoordinator.ts`
- `frontend/src/lib/graph/ui/statusLine.ts`

This should keep `GraphCanvas.svelte` and `GraphToolbar.svelte` focused on rendering, not orchestration.

### 5. Domain API Client Layer

Replace the single large `api.ts` with a stable fetch core plus domain clients.

Candidate structure:

- `frontend/src/lib/api/core.ts`
- `frontend/src/lib/api/projects.ts`
- `frontend/src/lib/api/settings.ts`
- `frontend/src/lib/api/graph.ts`
- `frontend/src/lib/api/crawl.ts`
- `frontend/src/lib/api/collections.ts`
- `frontend/src/lib/api/analysis.ts`
- `frontend/src/lib/api/types.ts`
- `frontend/src/lib/api/index.ts`

The goal is not complexity for its own sake. The goal is to stop unrelated features from colliding in one file and to make route ownership obvious.

## Recommended Refactor Sequence

This sequence reflects the reviewed and adopted plan (Option B): attack the
real complexity hotspots first and defer the lower-value seams. Do this
incrementally — each phase should leave the app runnable.

**Execution order: Phase 0 → Phase 1 → Phase 2 → Phase 3, then Phase 4.**
Phases 5–7 are deferred until F5 scoping is settled (see Deferred Phases
below).

### Phase 0: Baseline and Safety Rails

Mandatory. Complete before any code moves.

1. Capture current behavior of the graph path.
2. Add a short refactor checklist for:
   - workspace switching
   - SWR payload restore
   - selection persistence
   - draw-edge flow
   - right-click actions
   - kill-switch trip and resume
   - filter shelf behavior
   - layout stop and reset
3. Explicitly capture the hazards that currently live only in code comments
   inside `GraphCanvas.svelte`, since those comments are the only regression
   record today:
   - hover fade/hold strobe behavior
   - the `untrack` infinite-loop guard
   - the stable-graphology-reference requirement
   - SWR / workspace restore timing
   - SwiftShader shader-compile cost assumptions
4. Run frontend checks and backend tests that cover graph-adjacent flows.

Deliverable:

- documented “must not regress” checklist, including the comment-only hazards

Status: **done (2026-05-20)** — see `docs/work/archive/2026-05-20-graph-frontend-refactor/checklist.md`.
Baseline captured: `npm run check` 0/0, `npm run build` clean (single
`bundle.js` + `bundle.css`), 113 graph-adjacent backend tests passing.

### Phase 1: Extract GraphCanvas Runtime Utilities

Rationale:

- `GraphCanvas.svelte` (~2,386 lines) is the biggest single risk surface and
  the file the next F5+ feature will otherwise land in.
- Runtime extraction does not require changing product behavior.

Actions:

1. Move Sigma init and teardown into a runtime helper.
2. Move camera reset, fit, and restore helpers into a camera module.
3. Move reducer registration and refresh hooks into dedicated functions.
4. Keep `GraphCanvas.svelte` as the coordinator initially.

Acceptance criteria:

- renderer lifecycle is isolated from app-specific business logic
- `GraphCanvas.svelte` loses setup and teardown bulk without changing outputs

Status: **done (2026-05-20)**. New modules `lib/graph/runtime/sigmaRuntime.ts`
(WebGL probe, renderer factory, node programs, dark hover) and
`lib/graph/runtime/camera.ts` (bbox, fit/restore/refit). `GraphCanvas.svelte`
2386 → 2249 lines. Pure code move; `npm run check` 0/0, `npm run build` clean.

### Phase 2: Extract Interaction Policies From GraphCanvas

Actions:

1. Move node/edge click rules into pure helper functions where possible.
2. Move context-menu section construction into a separate builder module.
3. Move draw-edge state transitions and validations into their own service/helper.
4. Move keyboard interaction policy out of the component body.
5. Add unit tests for the extracted pure modules (menu eligibility, draw-edge
   validation) as part of this slice, not after — they are only testable in
   isolation once extracted.

Acceptance criteria:

- `GraphCanvas.svelte` reads like a wiring component, not an application brain
- menu item availability rules are unit-testable without mounting the canvas

Status: **done (2026-05-20)**. Interaction policy extracted to
`lib/graph/interactions/`: `contextMenu.ts` (menu builders), `drawEdge.ts`
(request + click resolvers), `egoFocus.ts` (`computeEgoReachable` +
`shortestPathEdges`), `keyboard.ts` (`classifyGraphKey`), `selection.ts`
(click/menu-mode rules). `GraphCanvas.svelte` 2249 → 2112 lines — menu
glue and Sigma event wiring stayed. Vitest added as the frontend
unit-test runner (`npm test`); 44 tests over the extracted modules.
Shipped as four pure-code-move slices (2a–2d); `npm run check` 0/0 and
`npm run build` clean after each. See
`docs/work/archive/2026-05-20-graph-frontend-refactor/checklist.md` Phase 2 sign-off.

### Phase 3: Reduce `graph.svelte.ts` Into State Plus Imported Model Logic

Actions:

1. Extract cluster synthesis and collapsed-domain logic.
2. Extract payload diff policy and rebuild policy (`applyDiff`, `rebuildInto`).
3. Extract graph count derivation.
4. Keep the stable graphology instance strategy intact unless profiling proves it should change.
5. Add unit tests for the extracted transform modules using plain payload
   fixtures as part of this slice.

Acceptance criteria:

- state ownership remains in the store
- transformation logic moves into named modules
- graph model rules become testable with plain payload fixtures

Status: **done (2026-05-21)**. `graph.svelte.ts` split into a thin
rune-state owner (787 → 233 lines) plus pure model modules under
`lib/graph/model/`: `clusterDomain.ts` (cluster key scheme +
`synthesizeClusterRaw`), `geometry.ts` (`nodeSize`, `haloOffset`,
`sunflowerAround`, `NODE_SPACING`, `positionStubsAroundParents`),
`applyPayload.ts` (`rebuildInto` + `applyDiff`, taking a
`ClusterFilterOptions` snapshot instead of reading the filter store),
and `graphCounts.ts` (`deriveStructuralCounts`). Shipped as four
pure-code-move slices (3a–3d); `npm run check` 0/0 and `npm run build`
clean after each. Vitest grew 44 → 78 tests over the extracted modules.
See `docs/work/archive/2026-05-20-graph-frontend-refactor/checklist.md` Phase 3 sign-off.

## Deferred Phases

These phases were originally sequenced earlier and deferred past Phase 3.
Phase 4 (the API split) has since shipped — its status block is kept below
for history. The remaining UI and workspace phases depend on F5 scoping
decisions that have not been made. Revisit this list once the F5
placeholder surfaces are designed.

### Phase 4: Split the API Client

Run opportunistically as a barrel-backed slice once the graph work above is
stable.

1. Keep the current `apiFetch` behavior exactly the same.
2. Move request/response types into stable API modules.
3. Add an `index.ts` barrel to avoid a noisy call-site migration.
4. Preserve existing exported names during the transition.

Acceptance criteria:

- no call-site behavior changes
- same route coverage
- `frontend/src/lib/api/` becomes a compatibility barrel or is removed

Status: **done (2026-05-21)**. `frontend/src/lib/api/` (~630 lines) split
into `frontend/src/lib/api/`: `core.ts` (`BASE`, `ApiError`, `apiFetch`,
`qs`), `types.ts` (all 40 response + request types), and ten per-domain
route modules (`health`, `projects`, `settings`, `crawl`, `watchlist`,
`nodes`, `graph`, `collections`, `monitors`, `analyses`) behind an
`index.ts` barrel. `$lib/api` now resolves to the barrel, so all 34 import
sites were untouched. Shipped as two pure-code-move slices (4a–4b);
`npm run check` 0/0 and `npm run build` clean (single `bundle.js` +
`bundle.css`) after each. The 89-name public export surface was diffed
before/after — identical. Vitest grew 78 → 85 tests — added
`api/core.test.ts` (7) covering `qs()`.
See `docs/work/archive/2026-05-20-graph-frontend-refactor/checklist.md` Phase 4 sign-off.

### Phase 5 (deferred): Centralize Graph UI Orchestration

Depends on F5 scoping.

1. Separate toolbar state and action wiring from view rendering.
2. Centralize graph modal open/close state instead of keeping it buried in the canvas.
3. Isolate status-chip logic and workspace-target chip logic.
4. Normalize graph action execution patterns and error-to-toast mapping.

Acceptance criteria:

- toolbar, modal, and status logic can evolve without re-opening low-level canvas code

### Phase 6 (deferred): Normalize Workspace and Snapshot Boundaries

Depends on F5 scoping.

1. Clarify whether workspace state is a generic app concern or a graph feature concern with app exposure.
2. Move graph-specific restore semantics closer to the graph feature if appropriate.
3. Keep the persisted workspace settings contract stable unless the interview phase decides otherwise.

Acceptance criteria:

- workspace switching semantics are explicit
- snapshot restore responsibilities are easy to locate

### Phase 7 (deferred): Backend Follow-On Cleanup

This should be a second program, not mixed into the first unless required.

1. Standardize read access in `CrawlDB` so modules stop reaching into `db._lock` and `db._conn` directly.
2. Define a small read helper contract in `db/core.py`.
3. Reduce route-level direct SQL calls where DB helpers should own them.

Acceptance criteria:

- direct `_lock` and `_conn` access materially reduced
- DB read ownership becomes more uniform

## Proposed File/Module Moves

This is a suggested end state, not a mandatory exact tree.

```text
frontend/src/lib/api/
  core.ts
  types.ts
  projects.ts
  settings.ts
  graph.ts
  crawl.ts
  collections.ts
  analyses.ts
  index.ts

frontend/src/lib/graph/
  runtime/
    sigmaRuntime.ts
    camera.ts
    reducers.ts
  model/
    applyPayload.ts
    clusterDomain.ts
    graphCounts.ts
  interactions/
    contextMenu.ts
    drawEdge.ts
    selection.ts
    egoFocus.ts
  ui/
    toolbarState.ts
    modalCoordinator.ts
    statusLine.ts
```

## Rollout Strategy

Recommended rollout style:

1. Extract code without behavior changes.
2. Keep compatibility exports during migration.
3. Ship in thin slices rather than one long-lived branch.
4. After each phase, run:
   - `cd frontend && npm run check`
   - `cd frontend && npm run build`
   - relevant backend tests if route contracts were touched

## Risks

### Highest-risk behaviors

- workspace snapshot restore timing
- SWR payload application during workspace switches
- Sigma camera and reducer synchronization
- kill-switch pause/resume interactions with graph polling
- right-click menu actions that bridge graph, selection, and modal state

### Main failure mode to avoid

A “helpful” refactor that changes architecture and behavior at the same time. This plan assumes the current user-visible behavior stays stable until a separate product decision changes it.

## Success Metrics

The refactor is succeeding when:

1. `GraphCanvas.svelte` becomes substantially smaller and mostly wiring-focused.
2. `graph.svelte.ts` becomes a thin state owner backed by imported model logic.
3. `api.ts` is no longer the default dumping ground for every new route.
4. New graph changes can usually be made in one focused module instead of across component, store, and ad hoc helper code.
5. Follow-up agents can explain ownership boundaries quickly.

## Questions For The Follow-Up Interview Agent

The next agent should walk through these with you one at a time.

### Product and workflow questions

1. Which graph behaviors are truly stable and must remain unchanged during refactor?
2. Which graph workflows are most important in real investigations?
3. Which placeholder surfaces are likely to become active next:
   left search/intel panes, right panel, bottom pane, or search tab?
4. Do you want the graph feature to remain the primary product center, or should the next phases rebalance toward non-graph workflows?

### Technical preference questions

1. Do you want a feature-folder structure for graph code, or do you prefer keeping stores/components/lib separated by type?
2. Are compatibility barrels acceptable during the transition, or do you want direct imports updated immediately?
3. Do you want aggressive module extraction even if file count grows, or a smaller number of medium-sized modules?
4. Do you want tests added during each extraction slice, or do you prefer structure first and tests after stabilization?

### Refactor-risk questions

1. Are there known flaky graph behaviors that we should preserve carefully rather than “clean up”?
2. Are there performance thresholds that matter more than code structure right now?
3. Are there active branches or upcoming changes likely to touch `GraphCanvas.svelte`, `graph.svelte.ts`, or `api.ts` soon?

## Recommendation

Adopted: Option B (reviewed 2026-05-20). Execute Phase 0 through Phase 3 in
order — the safety checklist, then the GraphCanvas runtime and interaction
extractions, then the `graph.svelte.ts` model split. These attack the genuine
complexity hotspots (`GraphCanvas.svelte` at ~2,386 lines and the ~730 lines
of transform logic inside `graph.svelte.ts`) and buy down risk for F5+ feature
work that would otherwise land directly in those files.

Defer Phases 5–7. The UI and workspace phases depend on unresolved F5
scoping; the backend cleanup is a separate program. Phase 4 (the API client
split) was run opportunistically once Phase 3 was stable — see its status
block. Keep the rollout discipline in every slice: extract without
behavior change, keep compatibility exports, ship thin slices, and add unit
tests for extracted pure modules during the slice rather than after.
