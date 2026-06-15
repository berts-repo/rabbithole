# Outcome — Settings Modal Completion (item 8), Wave 1

Shipped 2026-06-09. The gear icon now opens a real left-rail, autosave
multi-tab Settings modal, replacing the 84-LOC dead-end stub.

## What shipped

- **`SettingsModal.svelte`** — wide (880px) left-rail shell with vertical
  arrow-key tab navigation, Escape / backdrop dismissal. Autosave model: no
  Save button, no dirty state.
- **Five tabs** under `components/modals/settings/`:
  - **Graph** — default layout + the Topology/Colour/Overlay filters + a
    hide-rules subsection over `graph_filters`. The hide-rules CRUD absorbed
    the former bottom-pane Hidden tab, which is now deleted.
  - **Engines** — search-engine add / edit / delete + per-engine enable toggle
    (templated `search.engine.{id}.enabled` setting).
  - **Watchlist** — term add / edit / delete.
  - **Browser** — executable path + launch mode.
  - **Embedding** — 384-dim model picker, auto-start toggle, recompute.
- **Backend** — the two missing edit routes (`PATCH /api/search-engines/:id`,
  `PATCH /api/watchlist/:id`) + their db helpers + tests.

## Key decisions (see `decisions.md`)

- Left rail + autosave (owner-confirmed).
- No new validation layer — reused the existing per-key
  `db/settings.py::validators_for_key` dispatch; the spec's "build a typed
  validation layer" framing was already satisfied.
- Extracted `components/graph/GraphFilterControls.svelte` so the toolbar
  filter shelf and the Settings Graph tab share one control set instead of
  duplicating ~250 LOC.
- Relocated the hide-rule helpers to `modals/settings/hideRules.ts` (cleaner
  dependency direction now the bottom-pane Hidden tab is gone).
- Dropped `'hidden'` from the `BottomTab` union, the bottom-pane groups, and
  the backend `workspace.bottomTab` validator enum. A stale persisted
  `bottomTab = 'hidden'` falls back to the default tab gracefully.

## Verification

Backend 723 pytest passed; lint-security OK. Frontend check 0/0, vitest 393
passed, production build emits the single `bundle.js` + `bundle.css`.

## Deferred

- **Wave 2** tabs (Tor/Privacy, Crawl & Queue, LLM/Ollama, Retention) — most
  of their setting keys already exist (items 6/7), but the tabs are out of
  scope here. Re-enters `NEXT.md` after this closes.
- Settings export/import, per-project vs global (UI-only) split.
- Clearing `browser.path` back to auto-detect isn't supported (the strict path
  validator rejects empty and there is no settings-DELETE route) — the tab
  only persists non-empty paths. A "reset to auto-detect" affordance is a
  small Wave 2 follow-up.

## Pre-existing bug fixed alongside

The backend `workspace.bottomTab` validator enum had drifted from the frontend
`BottomTab` union: it listed the renamed-away `analyses` and omitted `activity`
/ `inventory` (the renames/additions from items 6/5). Effect: selecting the
Activity or Inventory tab silently failed to persist (400, swallowed
fire-and-forget), so those two tabs were never remembered across reloads.
Synced the enum to match the frontend union and added a sync comment + test
coverage for `activity` / `inventory`. Latent since items 5/6, unrelated to the
modal work but found while editing this enum to drop `hidden`.
