# F5 — Left-pane Find sub-tab (item 9)

Closed package. Built the **Find** sub-tab: an inbound lookup over data
already crawled (keyword FTS5 + semantic), distinct from the outbound **Search**
engine tab (item 10). Terminology fixed by item 8.5 — see
[`docs/specs/naming.md`](../../../specs/naming.md) §"Search vs. Find".

Spec: [`docs/specs/explore-left-pane-find.md`](../../../specs/explore-left-pane-find.md).

## Shape

Three panes cooperate (CLAUDE.md selection model):

- **Left** — the composer: text input (debounced 300 ms, min 2 chars, ✕ clear)
  + a Keyword / Semantic mode toggle. `views/left/FindTab.svelte`, mounted from
  `LeftSidebar.svelte` (currently an F5 placeholder).
- **Bottom** — the result list, as its own new bottom-pane tab `find`
  (`views/bottom/FindResultsTab.svelte`). Running a search reveals + focuses it
  via the `workspaceStore.setBottom` auto-add built in the tab-strip refactor.
- **Right** — clicking a result is **highlight-only**
  (`selectionStore.highlight(node_id)` + `navigationStore.setRight('page')`):
  graph highlight + right panel, *without* moving the bottom active row.

Find state (query / mode / results) lives in a session store
(`lib/stores/find.svelte.ts`) so it survives sub-tab switches; it drains the
existing `findPendingStore` on mount for "Send to Find".

## Backend — what existed vs. what this adds

The two endpoints already exist and are wired (`routes/search.py`,
`main.py:201`):

- `GET /api/search/keyword?q=&limit=` — FTS5 over current page text.
- `GET /api/search/semantic?q=&limit=` — ANN over `embeddings`, `503
  embed_unavailable` when the worker isn't ready.

**Gap closed here:** the spec's Keyword mode returns **page + entity + note**
results, but the endpoint returned pages only. This package extends keyword
search to also query the `findings` table (`kind IN ('entity','note')`) and
merges the three result types — see [`decisions.md`](decisions.md).

## Read order

1. This README + [`outcome.md`](outcome.md) + [`decisions.md`](decisions.md)
2. `docs/specs/explore-left-pane-find.md` (intent)
3. `backend/backend/routes/search.py` + `backend/backend/db/pages.py`
   (`keyword_search`) + `backend/backend/db/findings.py`
4. `frontend/src/views/bottom/FlagsTab.svelte` (node-list → highlight pattern),
   `frontend/src/lib/stores/selection.svelte.ts` (`highlight`)
5. `frontend/src/lib/stores/bottomTabs.ts` (the customizable strip the `find`
   results tab slots into)
