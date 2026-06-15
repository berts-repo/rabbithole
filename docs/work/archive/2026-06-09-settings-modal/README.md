# Settings Modal Completion (item 8) — Wave 1

Closed Wave 1 package. Replaced the dead-end `SettingsStubModal.svelte` with a real
multi-tab Settings modal — the documented home for all app configuration.

Wave 2 remains queued separately; see [`../../NEXT.md`](../../NEXT.md).

## Scope (Wave 1)

Five tabs in a **left-rail** modal, all controls **autosave** per change:

1. **Graph** — layout / color / visibility defaults + hide-rules (absorbs the
   bottom-pane Hidden tab's `graph_filters` CRUD).
2. **Engines** — search-engine list: add / edit / delete / enable-disable.
3. **Watchlist** — watch-term list: add / edit / delete.
4. **Browser** — external browser path + launch mode.
5. **Embedding** — model selection + auto-start + recompute.

Plus the two missing backend edit routes: `PATCH /api/search-engines/:id`
and `PATCH /api/watchlist/:id`.

When Wave 1 landed, the bottom-pane **Hidden** tab was deleted (its CRUD now
lives in the Graph tab) and the F5 Settings-modal component is complete.

## What changed since the spec was written

The spec assumed the backend needed a typed validation layer built. It already
exists — `db/settings.py::validators_for_key` is a per-key validator dispatch
covering every Wave-1 (and most Wave-2) key. So Wave 1 backend work is just the
two `PATCH` routes; everything else is frontend wiring onto the existing
`GET/PUT /api/settings/:key` seam.

## Read order

1. This README + [`outcome.md`](outcome.md)
2. [`plan.md`](plan.md) + [`decisions.md`](decisions.md)
3. `frontend/src/lib/stores/graphFilters.svelte.ts` /
   `graphLayout.svelte.ts` (the settings round-trip pattern the tabs reuse)
4. `frontend/src/views/bottom/HiddenTab.svelte` (the CRUD the Graph tab absorbs)

## Status

Closed 2026-06-09 — see [`outcome.md`](outcome.md).
