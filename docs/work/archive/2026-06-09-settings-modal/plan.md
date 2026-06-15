# Plan — Wave 1

## Backend

1. `db/search_engines.py::update_engine(db, engine_id, *, label, url) -> bool`
   — UPDATE label+url, return whether a row matched. Caller validates url shape.
2. `db/watchlist.py::update_term(db, term_id, term) -> bool` — re-run the same
   validation as `add_term` (length, non-empty, dup), UPDATE, return matched.
   Raise `WatchlistError` on bad input.
3. `routes/search_engines.py` — `PATCH /api/search-engines/:id`: validate label
   + onion url (reuse `validate_onion_url`), 404 unknown, 400 dup/bad.
4. `routes/watchlist.py` — `PATCH /api/watchlist/:id`: 404 unknown, 400 bad,
   publish `watchlist.changed` so a live Focused crawl rebuilds its automaton.
5. Tests: extend the existing engines/watchlist route tests with PATCH cases.

## Frontend API

6. New `lib/api/engines.ts` — `listEngines / createEngine / updateEngine /
   deleteEngine` + `getEngineEnabled / setEngineEnabled` (templated
   `search.engine.{id}.enabled` setting). `SearchEngine` type in `types.ts`.
7. `lib/api/watchlist.ts` — add `updateWatchlistTerm(id, body)`.
8. Export both from `lib/api/index.ts`.

## Frontend UI

9. `components/modals/SettingsModal.svelte` — left-rail shell. Owns backdrop,
   Escape/backdrop dismissal, the rail (Graph/Engines/Watchlist/Browser/
   Embedding), and renders the active tab. Wide layout (`min(880px, …)`).
10. `components/modals/settings/GraphTab.svelte` — binds `graphLayoutStore` +
    `graphFiltersStore`; hide-rules subsection ported from `HiddenTab`.
11. `EnginesTab.svelte` — list with inline edit, enable toggle, add row, delete.
12. `WatchlistTab.svelte` — list with inline edit, add row, delete.
13. `BrowserTab.svelte` — `browser.path` text + `browser.launch_mode` select.
14. `EmbeddingTab.svelte` — `embedding.model` select (from `/embed/models`),
    `embedding.auto_start` toggle, recompute button (`/embed/start`).
15. `AppShell.svelte` — swap `SettingsStubModal` → `SettingsModal`.

## Removals

16. Delete `SettingsStubModal.svelte`, `views/bottom/HiddenTab.svelte`.
17. Drop the `'hidden'` tab from `BottomPane.svelte` + the workspace store +
    the `workspace.bottomTab` validator enum in `db/settings.py`.
18. Keep `views/bottom/hidden.ts` (now imported by GraphTab) — or relocate it
    under the settings folder if cleaner.

## Verify

19. Backend pytest green. Frontend `tsc` check + vitest + production build
    (single `bundle.js`/`bundle.css`). Update `frontend-structure.md` +
    `features.md` for the new modal and removed Hidden tab.
