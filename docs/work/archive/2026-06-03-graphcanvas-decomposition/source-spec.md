# GraphCanvas Decomposition

## Status

Implementation-ready architecture cleanup. Frontend only — no schema work.
Can run in parallel with `shared-ui-primitives.md` since they touch different
code.

## Goal

Split the 1,951-LOC `GraphCanvas.svelte` god component into testable
TypeScript controllers, so graph work is safe to change. This is purely
structural — no user-visible change, no LOC reduction, no new features. The
deliverable is **testability and contained blast radius** when graph behavior
evolves.

## Why Now

Two upcoming items directly increase pressure on `GraphCanvas`:

- **`schema-reset.md`** unlocks page versioning. A "view diff between
  snapshots" mode needs new reducers, new visibility rules, and new overlays
  — all currently tangled in one file.
- **Future workspace/NodeSet work** changes how graph scope is determined,
  affecting visibility, layout, and refresh effects that currently live in
  `GraphCanvas`.

Doing the decomposition first means those changes land in focused controllers
instead of bloating the god component further.

## Current Responsibilities in `GraphCanvas.svelte`

In one 1,951-LOC file, the component owns:

1. WebGL rendering through Sigma.js
2. Hover state and fade calculations
3. Ego-focus reachability cache
4. Click and keyboard event dispatch
5. Drag-to-move node positioning
6. Layout lifecycle (run, settle, freeze)
7. Visibility and visible-node counts
8. Sigma reducers (per-node color/size/label)
9. Context menu and modal wiring
10. Refresh effects driven by graph store

Existing partial extractions: `sigmaRuntime.ts`, `camera.ts`, and pure
interaction helpers for draw-edge, ego-focus, keyboard, and selection.

## Target Controllers

Each controller is a TypeScript module that owns its state and exposes a
narrow reactive interface. The Svelte component instantiates them and renders
the canvas DOM — nothing more.

### `hoverController.ts`

- Owns: hovered node id, hover fade state per node.
- Exposes: `setHover(nodeId | null)`, reactive `fadeMap`.
- Pure logic; trivially unit-testable.

### `egoFocusController.ts`

- Owns: focused node id, reachability cache, expansion depth.
- Exposes: `focusOn(nodeId)`, `unfocus()`, `isReachable(nodeId)`.
- Pure graph algorithm; testable with synthetic graphs.

### `layoutController.ts`

- Owns: current layout name, layout worker lifecycle, position application.
- Exposes: `runLayout(name)`, `stopLayout()`, reactive `isRunning`.
- Wraps existing `layouts/force.ts` and friends.

### `visibilityController.ts`

- Owns: current visibility predicate (filters + scope + collection membership).
- Exposes: `isVisible(nodeId)`, reactive `visibleCount`.
- Pure derivation over graph store + filter store.

### `reducerController.ts`

- Owns: Sigma's per-node reducer functions for color/size/label.
- Exposes: `nodeReducer`, `edgeReducer` ready to hand to Sigma.
- Composes inputs from hover, ego focus, visibility, and color-mode state.

### `sigmaEventController.ts`

- Owns: Sigma event binding lifecycle.
- Translates: Sigma events → app actions (selection, context menu, drag).
- Isolates the "Sigma said X happened" translation layer.

### `contextMenuAdapter.ts`

- Owns: mapping click/right-click events to context menu state.
- Connects to the existing context menu / modal system.

## After Decomposition

`GraphCanvas.svelte` shrinks to:

- Mounting the Sigma instance via `sigmaRuntime.ts`
- Instantiating the controllers and wiring them to props
- Rendering the canvas DOM and overlays
- Maybe 300–400 LOC

The repository's total LOC stays roughly flat — moved logic plus new test
files balance out. The win is structural, not quantitative.

## Testability

Each controller becomes unit-testable in isolation:

- "Given graph G and focus node N, the reachable set is R."
- "Given a hovered node, the fade map dims unrelated nodes correctly."
- "Given filter F and scope S, node N's visibility is V."

None of these tests exist today because the logic lives inside a Svelte
component lifecycle. After decomposition, write a test file per controller as
you extract it — that's where the long-term safety comes from.

## User-Visible Changes

None. Same canvas, same toolbar, same keyboard shortcuts, same context menus,
same ego focus, same draw-edge mode. If anything user-facing changes, the
decomposition broke something — revert and try again.

## Implementation Approach

Extract controllers one at a time, smallest first, validating no behavior
change at each step. Recommended order:

1. `hoverController` (smallest, lowest risk)
2. `egoFocusController`
3. `visibilityController`
4. `reducerController`
5. `layoutController`
6. `sigmaEventController`
7. `contextMenuAdapter`

Write a unit test for each as it lands. Do not refactor the WebGL rendering
itself — that's a separate, deeper project.

## Relationship to Other Work

- Parallel with `shared-ui-primitives.md` — different code, no conflict.
- Required precondition for `schema-reset.md`'s page-versioning rendering
  (snapshot diff mode wants new reducers and visibility).
- Required precondition for future NodeSet workspace work (workspace scope
  plugs into `visibilityController`).
- Independent of `pane-responsibility-reset.md` — does not touch panes.

## Code Size Expectation

Component LOC drops sharply (1,951 → ~300–400). Repository LOC stays flat or
grows slightly once test code is added. This is not a code-shrinking
exercise — it's an investment in safe future changes.

## Deferred Decisions

- Whether to extract a separate `dragController.ts` or keep drag handling
  inside `sigmaEventController.ts`.
- Whether the controllers expose Svelte `$state` directly or go through a
  small store wrapper for testability.
- Whether `contextMenuAdapter.ts` is part of this package or part of
  `pane-responsibility-reset.md` (it spans both).
