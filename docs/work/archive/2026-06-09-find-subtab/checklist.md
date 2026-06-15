# Checklist — Find sub-tab (item 9)

## Done

- [x] Backend: keyword search extended to page + entity + note (`db/findings.py
      search_findings`, merged in `routes/search.py`); page rows tagged
      `type:'page'`. LIKE wildcards escaped. Note snippets truncated.
- [x] Backend: `find` added to the `workspace.bottomTab(s)` enum
      (`db/settings.py _BOTTOM_TAB_VALUES`).
- [x] Backend tests: page-tag, entity match, note match, snippet truncation,
      literal-wildcard safety (`tests/test_b8_search.py`). 733 pass.
- [x] Frontend API: `lib/api/search.ts` — `keywordSearch` / `semanticSearch`
      (typed union; `distanceToScore`; `EmbedUnavailableError` for the 503).
- [x] Frontend store: `lib/stores/find.svelte.ts` — query/mode/results, 300 ms
      debounce, min-2-chars, runId guard, mode-switch re-run, `drainPending`.
- [x] Left composer: `views/left/FindTab.svelte`, mounted in `LeftSidebar`.
- [x] Bottom results: `views/bottom/FindResultsTab.svelte` + the `find`
      `BottomTab` (`bottomTabs.ts`); BottomPane body case. Running a Find
      auto-reveals the tab via `workspaceStore.setBottom`.
- [x] Result click = highlight-only (`selectionStore.highlight` +
      `setRight('page')`); right-click = shared bottom-pane menu.
- [x] **Security:** keyword snippets carry unescaped onion-page text, so they
      are parsed into auto-escaped text + `<mark>` segments
      (`findResults.ts parseSnippet`) — never `{@html}`. Covered by a test that
      asserts injected markup stays inert text.
- [x] Frontend tests: `parseSnippet`, `resultKey`, `distanceToScore`. 406 pass.

## Deferred (note for owner before close)

- **Entity-value context menu** — the spec gives entity rows their own menu
  (Send to Find / Send to Crawl / Copy on the entity *value*). Today every
  result row uses the standard URL/node bottom-pane menu. The value-scoped menu
  is a follow-up.
- **"Open as graph tab"** on the result list — the spec marks this an additive
  follow-on (results are real graph nodes → a NodeSet source, item 4). Not
  built here.
