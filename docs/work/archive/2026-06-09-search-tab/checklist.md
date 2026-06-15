# Checklist — Search tab completion (item 10)

## Frontend — SSE client

- [x] API client for `GET /api/harvest/search` (`lib/api/harvest.ts`: typed
      result + the `probe` / `done` / `error` / `status` / `all_done` event
      union + `harvestSearchPath`). Start/Stop over the shared `$lib/sse`
      EventSource manager; closes on `all_done` to defeat auto-reconnect.
- [x] Session store (`lib/stores/searchHarvest.svelte.ts`) for query / selected
      sources / per-source status / results / passive toggle; results upsert by
      URL, probe patches in place. Pure reducer + empty-state classifier split
      to `searchHarvestModel.ts` (+ vitest).

## Frontend — composer

- [x] Search bar: input + Search/Stop (red Stop only while searching), Enter to
      start, input disabled while in progress.
- [x] Source-selector row: one checkbox pill per *enabled* engine (all
      pre-selected, min one), plus the **Passive** toggle pill backed by
      `search.passive_mode`.
- [x] Per-source status badges (`…` / `N` / `error` / `timed out`) +
      "searching via Tor…" label.

## Frontend — results list

- [x] Crawled rows (darker bg): source badge, `crawled` badge, URL, title,
      detail row (category chip + last-seen). *Description is uncrawled-only —
      there is no stored crawled-page meta description in the data model; see
      decisions.*
- [x] Uncrawled rows: source badge, URL, "probing…" → title/description on probe.
- [x] Row click: crawled → highlight node + right Page tab; uncrawled → local
      row selection (no node yet).

## Frontend — per-row actions (one inline button + shared right-click menu)

- [x] Each row keeps ONE inline button: crawled → **→ Graph** (switch center to
      Explore + highlight), uncrawled → **Send to Crawl** (left Crawl sub-tab +
      load URL).
- [x] Everything else moved into the shared row right-click menu
      (`$lib/contextMenu`, item 2026-06-09-centralize-context-menu). The bottom-
      pane row menu (`bottomPaneMenu`/`BottomPaneContextMenu`) was promoted to
      `lib/contextMenu/rowMenu.svelte` + `RowContextMenu.svelte`, mounted once in
      AppShell, and the Search tab points at it. **Open in Tor Browser** now
      available on Search rows (Tor-gated) — the gap that prompted this package.
- [x] id-bound actions on a URL-only (uncrawled) row mint a stub node on demand
      (`ensureNodeId`), so Open in Tor / Flag / Queue Analysis / Add to
      Collection all work without a prior crawl; stubs are never created
      speculatively. Same upgrade applies to bottom-pane Bookmark rows for free.
- [x] **Add to Collection** added to the single-target menu (graph + rows);
      `sections.test.ts` covers it.

## Frontend — empty states

- [x] No engines / before-first-search / no-results / all-sources-failed
      (connection vs. other, keyed off the new error `reason`).

## Backend — gaps closed while wiring the client

- [x] **Crawled enrichment.** URL-result events now carry `{node_id, title,
      category, last_seen}` for crawled hits (`resources.crawled_meta_by_url`),
      so "→ Graph" has a node id and the row renders per spec.
- [x] **Per-session source selection.** New `engines` query param (comma ids,
      intersected with enabled) backs the source-selector override.
- [x] **Error reason.** `_bounded_get` now raises `_FetchError(reason)`; error
      events carry `connection|timeout|unreadable|invalid` for the badge +
      two-way "all sources failed" empty state.
- [x] **Robust result extraction** (`_extract_result_links`): unwraps
      redirect-wrapped result links (`redirect_url=` etc.), scrapes bare onion
      URLs from result-page text, and drops the engine's own self-links. Crawler
      `parse_html` untouched.
- [x] **Engine fetch acts like a browser** (`_fetch_engine_links`, 2026-06-09).
      Root cause of the "~1 result" symptom was the *fetch*, not extraction:
      Ahmia 302-bounces a bare query GET to its homepage (per-page hidden form
      token), and three of the four old defaults were dead (Torch = stale onion,
      Haystak = unreachable, DDG-onion = Tor block page + clearnet-only index).
      When a direct query yields no links we now prime the engine's search form
      — fetch its homepage, scrape the form's hidden fields, retry the query
      with them — on the same isolated Tor circuit. `allow_redirects=False`
      kept (egress stays onion-only). Defaults trimmed to two live-verified
      engines: **Ahmia** (primed) + **OnionLand** (plain GET). Live check:
      `aliens` → Ahmia 275 links / 123 hosts, OnionLand 22.

## Verify

- [x] Frontend check 0/0 + 422 vitest + single bundle.
- [x] Backend 741 pytest (incl. +6 harvest: enrichment, engines filter, error
      reason, extractor unwrap/dedup/self-link).
- [x] `make lint-security` OK.
- [x] Backend live "aliens" search returns many results (Ahmia 275 / OnionLand
      22 via `_fetch_engine_links` through Tor, 2026-06-09).
- [ ] **Manual (owner):** in-app "aliens" search returns many results after a
      **backend restart**; Stop halts; passive skips probes; both action bars
      behave. Existing projects keep the old 4 engines — recreate the project or
      fix the set under Settings → Engines to get the trimmed defaults.
