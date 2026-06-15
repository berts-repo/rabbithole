# Graph Controllers — Boundary Contract

Each controller is a **plain TypeScript module** (no Svelte `$state` inside).
A controller owns an internal state object and exposes: typed **getters** for
the values `GraphCanvas` reads; **imperative mutators** (`setHover`,
`focusOn`, …); and a `subscribe(listener: () => void) => () => void` function
that the Svelte component can call inside `$effect` to invalidate a `$derived`
whenever the controller's state changes.

A `createXController(deps)` factory takes explicitly typed dependencies (graph
store handle, filter store handle, sigma instance reference, etc.) and returns
the controller object. Constructors have no hidden side effects — all resource
acquisition happens in `init()` or equivalent explicit calls, and a `dispose()`
method cleans up subscriptions, timers, and worker threads.
