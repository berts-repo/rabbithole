# Decisions

## Owner-confirmed (2026-06-09)

- **Tab navigation — left rail.** Vertical tab list down the left of a wide
  modal, content on the right. Chosen over the existing top `PaneTabs` strip
  because it scales cleanly to the eventual 9 tabs and matches the conventional
  settings pattern. The top strip gets cramped past ~5 tabs.
- **Save model — autosave per control.** Each control writes immediately via
  the existing per-key `PUT /api/settings/:key`. No Save button, no dirty-state
  tracking. This matches the key/value backend (each setting is its own key)
  and the list tabs (Engines / Watchlist) are inherently per-row anyway.

## Build decisions

- **No new validation layer.** The spec's headline "typed validation layer" is
  already built (`db/settings.py::validators_for_key`). Wave 1 reuses it; the
  only new backend code is the two `PATCH` routes + their db helpers.
- **Graph tab reuses the existing stores.** `graphFiltersStore` /
  `graphLayoutStore` already round-trip every graph default through
  `settings.graph.*`. The Graph tab binds to those stores rather than issuing
  its own `putSetting` calls, so the toolbar and the modal stay in sync with no
  extra wiring. The hide-rules subsection reuses `hidden.ts` helpers
  (`normalizeTerm` / `isValidTerm` / `isDuplicate`) and the same graph-cache
  invalidation `HiddenTab` used.
- **`hidden.ts` is kept, `HiddenTab.svelte` is deleted.** The helper module is
  pure and now consumed by the Graph tab's hide-rules subsection; only the
  bottom-pane component and its tab registration go away.
- **`workspace.bottomTab` enum loses `"hidden"`.** Removing the bottom-pane tab
  means the persisted-tab validator must drop the value, else a stale
  `settings` row could reselect a tab that no longer exists.

## Deferred (unchanged from spec)

- Wave 2 tabs (Tor/Privacy, Crawl & Queue, LLM/Ollama, Retention).
- Settings export/import as a project profile.
- Per-project vs global (UI-only) preference split.
