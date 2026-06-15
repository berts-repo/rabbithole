# Outcome — GraphCanvas Decomposition

Closed: 2026-06-03

Third post-F6 cleanup package (item 3). Frontend only — no schema, no backend
routes, **no user-visible change**. Built in an isolated worktree in parallel
with Shared UI Primitives (item 2); merged to `main` after integrated build +
test passed across both packages.

## What shipped

The 1,951-LOC `GraphCanvas.svelte` god component was split into seven plain
TypeScript controllers under `lib/graph/controllers/`, each extracted in its
own commit (smallest first) with a matching vitest file:

1. `hoverController.ts` — hovered node id + derived fade map.
2. `egoFocusController.ts` — focused node id, reachability cache, expansion
   depth.
3. `visibilityController.ts` — visibility predicate over filters, scope, and
   collection membership. Exposes a `setScope()` seam designed for NodeSet
   Workspaces (item 4) to plug a workspace-membership predicate in without
   reshaping the controller.
4. `reducerController.ts` — Sigma node/edge reducers composed from hover, ego
   focus, visibility, and color-mode.
5. `layoutController.ts` — layout name + worker lifecycle, wraps the existing
   `layouts/force.ts` (no algorithm change).
6. `sigmaEventController.ts` — Sigma event binding lifecycle; events → app
   actions. Drag handling stays here for v1 (no separate `dragController`).
7. `contextMenuAdapter.ts` — click / right-click → context-menu state, wired
   to the existing `$lib/contextMenu/*` system.

Controllers are plain TS (no Svelte `$state`): each owns an internal state
object and exposes getters + imperative mutators + `subscribe(listener)`, via
a `createXController(deps)` factory. `GraphCanvas.svelte` wraps them in
`$derived` / `$effect` at the boundary. The contract is documented in
`lib/graph/controllers/README.md`.

`GraphCanvas.svelte` shrank from 1,951 to **498 LOC** (hard cap ≤500 met;
the 98-line overshoot of the 300–400 target is import/wiring boilerplate for
seven controllers) — now just sigma mount/dispose, controller instantiation,
reactive bridges, and canvas DOM + overlays + toolbar slot.

## Verification

- `npm run build` clean (TS strict, no new `any`) after each extraction and
  on the merged tree.
- `vitest` green on the integrated tree: 37 files / 342 tests (combined with
  item 2); 108 of those are the seven new controller specs.
- Behavior parity: no user-visible change — all event handling, reducers,
  layout, visibility, hover/fade, ego focus, drag, context menus, keyboard
  shortcuts, and modals preserved by delegation.
- Browser smoke pass (full graph interaction parity): deferred to the
  post-merge check shared with item 2.

## Notes / watch items

- The agent rewrote `drawEdgeStore.requestToken === 0` to
  `!drawEdgeStore.requestToken`. Equivalent only if the token is always a
  non-negative number (differs for `undefined` / `null`). Flagged for
  confirmation during the post-merge browser smoke pass (draw-edge mode).

## Carve-outs (held)

- WebGL rendering path untouched (`sigmaRuntime.ts`, `camera.ts` unchanged;
  Sigma version unchanged).
- `dragController.ts` not split out — drag stays in `sigmaEventController.ts`
  until that file grows past ~250 LOC or a second consumer needs drag state.

## What this unlocks

- **Item 4 — NodeSet Workspaces** plugs its workspace scope into
  `visibilityController.setScope()`.
- **Item 6 — Schema Reset Milestone** page-versioning render mode lands in the
  focused `reducerController` / `visibilityController` instead of the god
  component.
