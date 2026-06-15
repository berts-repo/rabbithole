# Outcome — F8 Search tab completion (item 10)

Closed 2026-06-09 (commit `9315252`). Completed the outbound **Search** tab:
discovery of new `.onion` URLs by querying dark-web engines through Tor, results
streaming in over SSE. The *outbound* counterpart to the *inbound* **Find**
sub-tab (item 9). Replaced the 22-line `SearchTab.svelte` stub with the full
spec surface, and — because Search rows needed **Open in Tor** — centralized the
right-click menu so the graph, bottom-pane sub-tabs, and Search rows share one
action set (see [`source-centralize-context-menu.md`](source-centralize-context-menu.md)).

## What shipped

**Frontend — SSE client + UI.**
- API client for `GET /api/harvest/search` (`lib/api/harvest.ts`): typed result
  + the `probe` / `done` / `error` / `status` / `all_done` event union over the
  shared `$lib/sse` EventSource manager (closes on `all_done` to defeat
  auto-reconnect).
- Session store (`lib/stores/searchHarvest.svelte.ts`): query / selected
  sources / per-source status / results / passive toggle; results upsert by URL,
  probe patches in place. Pure reducer + empty-state classifier split to
  `searchHarvestModel.ts` (+ vitest).
- Composer: search bar (Enter to start, red Stop only while searching), a
  source-selector row (one pill per *enabled* engine, all pre-selected, min one)
  plus the **Passive** toggle backed by `search.passive_mode`, and per-source
  status badges (`…` / `N` / `error` / `timed out`).
- Results list: crawled rows (badge + title + category chip + last-seen) and
  uncrawled rows (`probing…` → title/description on probe). Row click is
  highlight-only per the CLAUDE.md selection model. Untrusted onion-page text is
  rendered auto-escaped — never `{@html}`.
- Empty states: no-engines / before-first-search / no-results /
  all-sources-failed (connection vs. other, keyed off the error `reason`).

**Frontend — per-row actions (one inline button + shared right-click menu).**
- Each row keeps ONE inline button: crawled → **→ Graph** (switch + highlight),
  uncrawled → **Send to Crawl** (left Crawl sub-tab + load URL). Everything else
  moved into the shared row menu.
- The bottom-pane row menu (`bottomPaneMenu` / `BottomPaneContextMenu`) was
  promoted to `lib/contextMenu/rowMenu.svelte` + `RowContextMenu.svelte`,
  mounted once in `AppShell`, and the Search tab points at it. **Open in Tor
  Browser** is now available on Search rows (Tor-gated) — the gap that prompted
  this package.
- id-bound actions on a URL-only (uncrawled) row mint a stub node on demand
  (`ensureNodeId`), so Open in Tor / Flag / Queue Analysis / Add to Collection
  all work without a prior crawl; stubs are never created speculatively. The
  same upgrade fixes bottom-pane Bookmark rows for free.
- **Add to Collection** added to the single-target menu (graph + rows);
  `sections.test.ts` covers it.

**Backend — gaps closed while wiring the client.**
- Crawled enrichment: URL-result events carry `{node_id, title, category,
  last_seen}` for crawled hits (`resources.crawled_meta_by_url`).
- Per-session source selection: new `engines` query param (comma ids,
  intersected with enabled).
- Error reason: `_bounded_get` raises `_FetchError(reason)`; error events carry
  `connection|timeout|unreadable|invalid`.
- Robust result extraction (`_extract_result_links`): unwraps redirect-wrapped
  links, scrapes bare onion URLs from result text, drops engine self-links.
- **Engine fetch acts like a browser** (`_fetch_engine_links`): the "~1 result"
  symptom was the *fetch*, not extraction — Ahmia 302-bounces a bare query GET
  (per-page hidden form token) and three of the four old defaults were dead.
  When a direct query yields no links we now prime the engine's search form
  (fetch homepage, scrape hidden fields, retry the query with them) on the same
  isolated Tor circuit. Defaults trimmed to two live-verified engines: **Ahmia**
  (primed) + **OnionLand** (plain GET).

## Verify

- Frontend check 0/0 + 422 vitest + single bundle.
- Backend 741 pytest (incl. +6 harvest: enrichment, engines filter, error
  reason, extractor unwrap/dedup/self-link). `make lint-security` OK.
- Backend live "aliens" search through Tor: Ahmia 275 links / 123 hosts,
  OnionLand 22.

## Open

- **Owner manual sweep** (the one unchecked checklist line): in-app "aliens"
  search after a backend restart returns many results; Stop halts; passive skips
  probes; the menu behaves across surfaces. Existing projects keep the old 4
  engines — recreate the project or fix the set under Settings → Engines to get
  the trimmed live-verified defaults.
