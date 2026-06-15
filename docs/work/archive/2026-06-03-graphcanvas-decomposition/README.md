# GraphCanvas Decomposition

Third post-F6 cleanup package. Frontend only — no schema, no backend
routes, no user-visible change. Runs **in parallel** with the
[Shared UI Primitives](../2026-06-03-shared-ui-primitives/README.md)
package; the two touch different code and do not conflict.

Closed package. Prefer [`outcome.md`](outcome.md) for what shipped.

## Goal

Split the 1,951-LOC `GraphCanvas.svelte` god component into testable
TypeScript controllers, so graph behavior is safe to change. The win
is **testability and contained blast radius** — none of the logic in
the component is unit-testable today because it lives inside a Svelte
lifecycle. After this package, each controller is exercised in
isolation, and the upcoming Schema Reset Milestone (page versioning
overlay) plus future NodeSet workspace work land in focused
controllers instead of bloating the component further.

If anything user-facing changes, the decomposition broke something —
revert and try again.

## Scope of this package

Extract controllers one at a time, smallest first, with no behavior
change at each step. Order per the source spec:

1. `hoverController.ts` — hovered node id + fade map.
2. `egoFocusController.ts` — focused node id, reachability cache,
   expansion depth.
3. `visibilityController.ts` — visibility predicate over filters,
   scope, and collection membership.
4. `reducerController.ts` — Sigma per-node color/size/label reducers
   composed from hover, ego focus, visibility, color-mode.
5. `layoutController.ts` — layout name, worker lifecycle, position
   application (wraps the existing `layouts/force.ts`).
6. `sigmaEventController.ts` — Sigma event binding lifecycle; Sigma
   events → app actions (selection, context menu, drag).
7. `contextMenuAdapter.ts` — click/right-click → context-menu state.

After the seven extractions, `GraphCanvas.svelte` shrinks to mounting
the Sigma instance via `sigmaRuntime.ts`, instantiating the
controllers, and rendering the canvas DOM + overlays. Target size:
~300–400 LOC.

Each controller ships with a vitest file. The repository's total LOC
stays roughly flat — moved logic plus new test files balance out.

## Carve-outs (decisions for this package)

1. **WebGL rendering itself stays untouched.** `sigmaRuntime.ts` and
   `camera.ts` are already extracted; we do not refactor the rendering
   path or the Sigma version. That's a separate, deeper project.
2. **`dragController.ts` deferred.** Drag handling stays inside
   `sigmaEventController.ts` for v1. Promote to its own controller
   only if the event controller grows beyond ~250 LOC or a second
   consumer needs drag state.
3. **Controllers expose plain TypeScript state.** They do not use
   Svelte `$state` directly — the spec's deferred decision is
   resolved in favor of testability. Each controller exposes a small
   reactive interface (getters + subscribe hook) that `GraphCanvas`
   wraps in `$derived` at the boundary. This keeps vitest from
   needing a Svelte runes runtime.
4. **`contextMenuAdapter.ts` lives here, not in the panes package.**
   The spec's deferred decision is resolved in favor of this package
   — Pane Responsibility Reset shipped without touching it, and the
   adapter's logic is graph-side translation, not pane wiring.

## Read order

1. [`outcome.md`](outcome.md)
2. [`plan.md`](plan.md), [`checklist.md`](checklist.md)
3. `docs/reference/frontend-structure.md`

## Relationship to the queue

- Parallel with **Shared UI Primitives** (item 2) — different code,
  no conflict. Both packages can land independently.
- Required precondition for **Schema Reset Milestone** (item 6)
  page-versioning rendering — snapshot-diff mode wants new reducers
  and visibility rules to land in focused controllers, not in the god
  component.
- Required precondition for **NodeSet Workspaces** (item 4) — workspace
  scope plugs into `visibilityController`.
- Independent of the now-archived Pane Responsibility Reset (item 1)
  — does not touch panes.
