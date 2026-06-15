# Checklist — Wave 1

## Backend
- [x] `db/search_engines.py::update_engine`
- [x] `db/watchlist.py::update_term`
- [x] `PATCH /api/search-engines/:id`
- [x] `PATCH /api/watchlist/:id`
- [x] route tests (engines + watchlist PATCH)

## Frontend API
- [x] `lib/api/engines.ts` + `SearchEngine`/`EngineBody`/`EmbedModel` types + index export
- [x] `updateWatchlistTerm`
- [x] `listEmbedModels` + `startEmbed`

## Frontend UI
- [x] `SettingsModal.svelte` (left-rail shell, vertical arrow-key nav)
- [x] `GraphTab.svelte` (layout + shared filter controls + hide-rules subsection)
- [x] `EnginesTab.svelte` (list, inline edit, enable toggle, add, delete)
- [x] `WatchlistTab.svelte` (list, inline edit, add, delete)
- [x] `BrowserTab.svelte` (path + launch mode)
- [x] `EmbeddingTab.svelte` (model picker + auto-start + recompute)
- [x] `AppShell` swap stub → SettingsModal
- [x] Extracted `GraphFilterControls.svelte`; FilterShelf now wraps it

## Removals
- [x] delete `SettingsStubModal.svelte`
- [x] delete `views/bottom/HiddenTab.svelte` + `hidden.ts` + `hidden.test.ts`
- [x] relocate helpers → `modals/settings/hideRules.ts` (+ test)
- [x] drop `'hidden'` from BottomPane, `bottomGroups.ts` (+ test), and the
      backend `workspace.bottomTab` validator enum (+ `test_b4_settings.py`)

## Verify
- [x] backend pytest — 723 passed
- [x] frontend check — 0 errors / 0 warnings
- [x] vitest — 393 passed (incl. relocated hideRules.test.ts)
- [x] production build — single bundle.js + bundle.css
- [x] lint-security — OK
- [x] reference docs updated (features.md, frontend-structure.md)
