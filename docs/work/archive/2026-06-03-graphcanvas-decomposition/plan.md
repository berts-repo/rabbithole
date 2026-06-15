# Plan — GraphCanvas Decomposition

Frontend only. No user-visible change. Extract seven controllers from
`frontend/src/components/graph/GraphCanvas.svelte` one at a time,
smallest first; each lands with a vitest file. WebGL rendering itself
stays untouched.

## 0. Controller boundary contract

Before extracting anything, set the shared shape so each controller
follows the same pattern (avoids retrofit churn):

- One file per controller under
  `frontend/src/lib/graph/controllers/<name>.ts`.
- Plain TypeScript. No Svelte `$state` inside controllers — they own
  an internal state object and expose:
  - getters for the values `GraphCanvas` reads;
  - imperative mutators (`setHover`, `focusOn`, …);
  - a `subscribe(listener)` returning an unsubscribe function so the
    Svelte component can wrap with `$derived` at the boundary.
- A `createXController(deps)` factory that takes typed dependencies
  (graph store, filter store, sigma handle, etc.) and returns the
  controller. Constructors stay narrow — no hidden side effects.
- A matching `<name>.test.ts` next to the controller. Tests build
  synthetic graphs / state and assert on getters.

## 1. `hoverController.ts` — first, smallest, lowest risk

- Owns: `hoveredNodeId | null`, derived `fadeMap: Map<nodeId, number>`.
- Reads: current graph payload (passed in via factory dep).
- Replaces the inline hover state + fade calculations in `GraphCanvas`.
- Tests: hover toggle, fade map for a node with neighbors, no-hover
  state.

## 2. `egoFocusController.ts`

- Owns: `focusedNodeId | null`, expansion depth, reachability cache.
- Exposes: `focusOn(id)`, `unfocus()`, `isReachable(id)`.
- Pure graph BFS; reachability cache invalidates when focus or graph
  payload changes.
- Tests: synthetic graphs (linear, branching, disconnected); cache
  invalidation on payload swap.

## 3. `visibilityController.ts`

- Owns: visibility predicate composed from filters, scope, and
  collection membership.
- Exposes: `isVisible(id)`, reactive `visibleCount`.
- Pure derivation over graph store + filter store. Designed so the
  later NodeSet workspaces (item 4) can plug in a scope without
  reshaping the controller.
- Tests: each filter dimension in isolation + combined; visible-count
  matches predicate count.

## 4. `reducerController.ts`

- Owns: per-node Sigma `nodeReducer` / `edgeReducer` builders.
- Composes inputs from hover, ego focus, visibility, and color-mode
  state.
- Exposes ready-to-hand reducer functions.
- Tests: each input dimension's effect on the reducer output (color,
  size, label) given a synthetic node.

## 5. `layoutController.ts`

- Owns: current layout name, layout worker lifecycle (start/stop/
  freeze), position application.
- Wraps existing `layouts/force.ts` and friends — no algorithm change.
- Exposes: `runLayout(name)`, `stopLayout()`, reactive `isRunning`.
- Tests: lifecycle transitions (`idle → running → settled → frozen`),
  layout-name routing, worker cleanup on dispose.

## 6. `sigmaEventController.ts`

- Owns: Sigma event binding lifecycle.
- Translates Sigma events → app actions: selection, context menu open,
  drag start/move/end, keyboard.
- Drag handling stays here for v1 (`dragController.ts` deferred per
  the README carve-out).
- Tests: event-to-action mapping with mocked Sigma events; cleanup on
  controller dispose.

## 7. `contextMenuAdapter.ts`

- Owns: mapping click / right-click events to context-menu state.
- Connects to the existing `$lib/contextMenu/*` system.
- Tests: input event → menu spec.

## 8. Shrink `GraphCanvas.svelte`

After the seven extractions, the component contains only:

- `sigmaRuntime` mount + dispose.
- Controller instantiation (`createHoverController(...)` etc.).
- Reactive bridges (`$derived` on controller getters, `$effect` on
  payload-driven controller reset).
- Canvas DOM + overlays + toolbar slot.

Target: 300–400 LOC.

## 9. Verification rules per step

For every controller extraction commit:

- `npm run build` clean; TS strict; no new `any`.
- `vitest` green (the new test file plus the existing suite).
- Manual smoke check: pan, zoom, hover, click select, multi-select,
  context menu, draw-edge, ego focus, layout switch, filter toggle.
  Behavior must be identical to the baseline. If anything differs,
  revert and re-attempt the extraction.
- Browser smoke pass after each step is cheap (no UI changes); use it
  as the safety net the spec calls for.

## 10. Verify (end of package)

- `npm run build` clean (TS strict, no new `any`).
- `vitest` green via test-runner subagent; per-controller spec count
  matches the seven controllers.
- Browser smoke pass: full graph interaction parity with the
  pre-decomposition baseline.
- `GraphCanvas.svelte` LOC ≤ 500.
