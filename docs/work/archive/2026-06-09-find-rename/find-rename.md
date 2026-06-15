# Find Rename — Left-pane lookup "Search" → "Find"

## Status

Implementation-ready terminology rename. Purely cosmetic at the code level —
the left-pane Search sub-tab is still a placeholder (`LeftSidebar.svelte:60`,
*"content lands in F5"*), so there is **no built feature to migrate**, only
labels, a type-enum value, one staging store/action pair, and docs.

**Precursor to item 9 (F5 Find sub-tab).** Land this rename *before* item 9 is
picked up so the sub-tab is built under its final name from the first commit.
This doc folds the rename out of item 9 so item 9's package can assume the
"Find" vocabulary already exists.

## Rationale

The app has **two distinct surfaces that both currently say "Search"**, and
they do opposite things:

| Surface | What it does | Direction | Item |
|---|---|---|---|
| **Search** — engine tab (`SearchTab.svelte`) | Queries external dark-web search engines to discover **new** onions you don't have | Outbound | F8 / item 10 |
| **Search** — left-pane sub-tab (`explore-left-pane-search.md`) | Keyword (FTS5) + semantic lookup over data you **already crawled**; results are graph nodes | Inbound | F5 / item 9 |

The collision is exactly the browser distinction between *Search the web* and
*⌘F Find on page*. Adopting that convention:

- **"Search"** stays the name of the engine tab — go out and find new things.
- **"Find"** becomes the name of the left-pane sub-tab — locate things already
  in your corpus / graph.

## "Send to Search" → "Send to Find"

The existing `actSendToSearch` action (`contextMenu/actions.ts:162`) does
`navigationStore.setLeft('search')` and stages a query into the **left-pane**
lookup — i.e. it targets what we are renaming to "Find." Leaving the action
labelled "Send to Search" while it opens a tab called "Find" would reintroduce
the exact confusion this rename removes. So **"Send to Search" → "Send to
Find"** everywhere, and the internal identifiers move with it
(`actSendToSearch` → `actSendToFind`, `searchPendingStore` →
`findPendingStore`, file `searchPending.svelte.ts` → `findPending.svelte.ts`).

Entity rows keep a "Send to Find" too — pivoting an extracted value (address,
handle, onion URL) into the local lookup is a real, wanted action, and the
operator may be inspecting an entity from the right pane (not already in the
Find tab), so it is not redundant.

### Dropped: routing entities out to the engine Search

An earlier idea was a separate *"Send to **Search**"* on entity rows that
queries the external dark-web engines (F8) for the entity's value. **Dropped
(owner, 2026-06-09)** — not building it. It pushes an operator-chosen term to a
third-party engine, leaking interest in a specific address/handle, which
conflicts with the project's operator-privacy-first stance; many entity types
(onion URLs) do not fit external search anyway. The rare case where an operator
genuinely wants to look an entity up externally is covered by the existing
**Copy** action on entity rows — copy, paste into the engine Search manually.
No engine-targeted "Send to Search" in this rename or in item 10.

## Touchpoint inventory

### Code — user-facing labels & strings

- `frontend/src/views/LeftSidebar.svelte:12` — tab label `'Search'` → `'Find'`
- `frontend/src/views/LeftSidebar.svelte:60` — placeholder still references the
  tab id; reads fine once the id changes
- `frontend/src/lib/contextMenu/actions.ts:165` — toast `Loaded into Search:` →
  `Loaded into Find:`
- `frontend/src/views/right/entityMenu.ts:38,49` — menu label `'Send to Search'`
  → `'Send to Find'`

### Code — type / identifier renames

- `frontend/src/lib/stores/navigation.svelte.ts` — `LeftTab` enum value
  `'search'` → `'find'`; default stays `'crawl'`; `LEFT_TABS` array; the
  `nav.leftTab` persisted setting now stores `'find'` (dev DB is disposable, no
  migration needed — old persisted `'search'` simply falls through to the
  default on load, acceptable)
- `frontend/src/lib/contextMenu/actions.ts:48,162-166` — `actSendToSearch` →
  `actSendToFind`; import of the store
- `frontend/src/lib/stores/searchPending.svelte.ts` → rename file to
  `findPending.svelte.ts`; `searchPendingStore` → `findPendingStore`
- `frontend/src/views/right/entityMenu.ts:16` — import + call sites
- Comment references in `bottomPanePreset.svelte.ts:7`,
  `intelCompose.svelte.ts:8`, `actions.ts:158-161`

### Code — call sites of `setLeft('search')`

- `frontend/src/lib/contextMenu/actions.ts:163` → `setLeft('find')`
- (verify no other `setLeft('search')` exists at implementation time)

### Tests

- `frontend/src/views/right/entityMenu.test.ts:6,36,45` — mock name
  `actSendToSearch` → `actSendToFind`; expected label `'Send to Search'` →
  `'Send to Find'`

### Spec docs

- `docs/specs/explore-left-pane-search.md` → rename file to
  `explore-left-pane-find.md`; retitle `# Graph Tab — Left Pane — Find
  Sub-tab`; placeholder copy `"Search crawled data…"` → `"Find in crawled
  data…"`; entity-row + bottom-pane "Send to Search" → "Send to Find" (lines
  11, 18)
- `docs/specs/index.md:20,24` — left sidebar list `Search · Intel · Crawl` →
  `Find · Intel · Crawl`; doc link + label; Notes line 73
- `docs/specs/explore-bottom-pane.md:39,49,197` — "Send to Search" → "Send to
  Find"; sub-tab name references
- `docs/specs/right-pane.md:100,101,104,158,170,171,382,397` — "Send to Search"
  → "Send to Find"; "left pane Search sub-tab" → "Find sub-tab"
- `docs/specs/security-decisions.md:202,209` — sub-tab heading + checklist item
- `docs/specs/naming.md:56,60,177` — placeholder + "Send to Search" rows; add
  the Search/Find distinction note so the inventory records the decision
- `docs/specs/search-tab.md:5` — cross-reference *"that's the Search sub-tab in
  the left pane"* → *"that's the Find sub-tab in the left pane"* (the engine
  spec itself stays "Search"; only this pointer changes)
- `docs/work/archive/2026-05-28-pane-responsibility-reset/source-spec.md:53` — spec-path reference
  `explore-left-pane-search.md` → `explore-left-pane-find.md`

### Reference / source-of-truth docs

- `CLAUDE.md` selection model — *"left-pane Search result click"* → *"Find"*
- `docs/reference/features.md:78,108` — Search sub-tab capability + entity menu
- `docs/work/NEXT.md:40,57,67,70` — item 9 label "F5 — Left pane Search
  sub-tab" → "Find sub-tab"; spec link → `explore-left-pane-find.md`
- `docs/work/ACTIVE.md:59-60` — follow-up pointer wording
- `docs/work/archive/2026-06-10-label-system/source-spec.md` — former
  additions label-system source; "Search sub-tab" references

### Out of scope (do not change)

- `SearchTab.svelte`, `CenterTab = 'search' | 'explore'`,
  `workspaceStore.centerTab === 'search'`, and **`AppHeader.svelte:17`**
  (`{ id: 'search', label: 'Search' }` — this is the **center/engine** tab, not
  the left tab; it looks exactly like a rename target but must NOT change) —
  these are all the **engine** Search and keep the name. `search-tab.md` keeps
  its title; only its one left-pane cross-reference (line 5, above) changes.
- `crawlQueue.ts:24` `'search'` source enum and the durable-queue source-spec —
  that is a crawl-origin tag, unrelated to either UI surface.
- Archived `docs/work/archive/**` outcome/checklist files — history; leave as
  written.

## Plan

1. **Specs first** — rename `explore-left-pane-search.md` →
   `explore-left-pane-find.md` (git mv), retitle, fix placeholder + Send-to
   copy; update `index.md`, `explore-bottom-pane.md`, `right-pane.md`,
   `security-decisions.md`, `naming.md`.
2. **Frontend types/stores** — `navigation.svelte.ts` enum;
   `searchPending.svelte.ts` → `findPending.svelte.ts`;
   `actSendToSearch` → `actSendToFind` and its callers; `setLeft('search')` →
   `setLeft('find')`; toast + comments.
3. **Frontend labels** — `LeftSidebar.svelte` tab label; `entityMenu.ts`
   labels.
4. **Tests** — update `entityMenu.test.ts`; run `npm run test` and
   `npm run check` (svelte-check / tsc) to confirm no stray `'search'` leftTab
   references.
5. **Reference + queue docs** — `CLAUDE.md`, `features.md`, `NEXT.md` (retitle
   item 9 + repoint spec link), `ACTIVE.md`, label-system source spec.
6. **Grep gate** — final `grep -rn "Send to Search\|leftTab.*search\|left-pane
   Search\|explore-left-pane-search"` across `frontend/src` + `docs` (excluding
   `archive/`) returns nothing.

## Verification

- `npm run check` and `npm run test` pass.
- Manual: left pane shows **Find / Intel / Crawl**; right-click an entity →
  **Send to Find** opens the Find tab and stages the value; toast reads
  "Loaded into Find".

## Estimated size

Small. Frontend: ~6 files + 1 rename + 1 test. Docs: ~10 files + 1 rename. No
backend, no schema, no API change.
