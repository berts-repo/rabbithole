# Outcome — F5 Left-pane Find sub-tab (item 9)

Closed 2026-06-09 (commit `25254c0`). Built the **Find** sub-tab: an inbound
lookup over data already crawled (keyword FTS5 + semantic), distinct from the
outbound **Search** engine tab (item 10). Three panes cooperate per the
CLAUDE.md selection model — left composer, bottom result list, highlight-only
result→graph/right-pane wiring.

## What shipped

**Backend.**
- Keyword search extended from pages-only to **page + entity + note** (D1):
  pages via FTS5 `MATCH` (`pages.keyword_search`, tagged `type:'page'`);
  entity/note via `findings.value LIKE` over the unified `findings` table,
  merged in `routes/search.py`. LIKE wildcards escaped; entity rows carry
  `entity_type` from `metadata.$.type`.
- Ordering is explicit, not a fake unified score (D2): **pages first
  (FTS-ranked), then entity, then note**, with a findings sub-cap
  (`_FINDINGS_SUBLIMIT = 25`) so structured findings always surface alongside a
  page-hit flood. Note snippets truncated server-side to ~200 chars (D3).
- `find` added to the `workspace.bottomTab(s)` enum (`db/settings.py`).
- Backend tests: page-tag, entity match, note match, snippet truncation,
  literal-wildcard safety (`tests/test_b8_search.py`). 733 pass.

**Frontend.**
- API: `lib/api/search.ts` — `keywordSearch` / `semanticSearch` (typed union;
  `distanceToScore` maps vec0 distance → spec's 0–1 similarity, D5;
  `EmbedUnavailableError` for the 503).
- Store: `lib/stores/find.svelte.ts` — query/mode/results, 300 ms debounce,
  min-2-chars, runId guard, mode-switch re-run, `drainPending` (for "Send to
  Find").
- Left composer `views/left/FindTab.svelte` (mounted in `LeftSidebar`); bottom
  results `views/bottom/FindResultsTab.svelte` as the new `find` `BottomTab`
  (D4) — not in `DEFAULT_VISIBLE_TABS`; running a Find auto-reveals it via the
  `setBottom` auto-add and it persists on the strip afterward.
- Result click = **highlight-only** (`selectionStore.highlight` +
  `setRight('page')`); right-click = shared bottom-pane menu.
- **Security:** keyword snippets carry unescaped onion-page text, so they are
  parsed into auto-escaped text + `<mark>` segments (`findResults.ts
  parseSnippet`) — never `{@html}`. A test asserts injected markup stays inert.
- Frontend tests: `parseSnippet`, `resultKey`, `distanceToScore`. 406 pass.

## Deferred (queued in NEXT.md as a Find follow-on)

- **Entity-value context menu** — the spec gives entity rows their own menu
  (Send to Find / Send to Crawl / Copy on the entity *value*). Today every
  result row uses the standard URL/node bottom-pane menu.
- **"Open as graph tab"** on the result list — results are real graph nodes, so
  a NodeSet source (item 4); the spec marks this an additive follow-on.
