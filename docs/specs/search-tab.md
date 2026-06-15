# Search Tab

The Search tab discovers new `.onion` URLs by querying dark-web search engines through the
Tor proxy in real time. Results stream in as they arrive. This is for **discovery** of new
sites, not searching already-crawled data (that's the Find sub-tab in the left pane).

---

## Layout

Top to bottom: search bar → source selector row → (optional) engine management panel →
scrollable results list.

---

## Search bar

- Text input (placeholder: "Search the dark web…") + Search / Stop button.
- Pressing Enter or clicking **Search** starts a search.
- Input is disabled while a search is in progress.
- **Stop** button (red) closes the SSE stream and stops probing. Appears only while searching.

---

## Source selector row

One checkbox pill per *enabled* search engine. On load, all enabled engines are pre-selected.
Each pill can be unchecked to exclude that source from the next search (minimum one selected).

Alongside the engine pills sits a **Passive** toggle pill. When active, the app contacts only
the configured search engines and does not probe discovered result URLs for title/description
previews — uncrawled results appear as URL + anchor text only. When inactive (default), the
Search tab fetches lightweight previews for each unknown onion through Tor. Backed by the
`search.passive_mode` setting (persisted per project; default `false`); toggling writes via
`PUT /api/settings/search.passive_mode`. Useful for analysts who want search to stay strictly
on the configured engines without the additional Tor fan-out.

While searching:
- Status badge appears on each active source:
  - `…` — searching
  - `N` — done, N results found
  - `error` / `timed out` — source failed

A "searching via Tor…" label appears while any source is active.

Engine management (add, edit, delete, set defaults) lives in the Settings modal →
Engines tab. The source selector here reflects the enabled defaults from settings and
can be overridden per-session without changing those defaults.

---

## Results list

Results stream in as the SSE events arrive. Each result is either a previously-crawled URL
or a newly discovered one.

**Crawled results** — background is slightly darker. Show:
- Source badge (engine label)
- `crawled` badge (blue)
- Full URL
- Title (if available) after a dash
- Detail row: category chip + last-seen date + description

**Uncrawled results** — show:
- Source badge
- URL
- While probing: "probing…" italic text in the detail row
- After probe: title and description if the site responded

Clicking anywhere on the main row of a result selects that URL and updates the rest of the UI.

**Per-row action — one inline button + the shared right-click menu.**

Each result keeps a single inline button for its primary verb; every other
action lives in the shared row right-click menu (`$lib/contextMenu`) — the same
menu the graph and every bottom-pane sub-tab use, so the action set (Copy URL,
Open in Tor Browser, Send to Crawl, Save as Seed Bookmark, Flag, Mark Reviewed,
Add Monitor, Queue Analysis, Add to Collection, Focus, Hide from Graph) stays
identical across surfaces.

| Row state | Inline button | Behaviour |
|-----------|---------------|-----------|
| Crawled | **→ Graph** | Switches to the Graph tab and highlights the node |
| Uncrawled | **Send to Crawl** | Switches to the Crawl sub-tab and loads this URL into the manual single-URL input. The analyst picks mode / collection / stay-on-domain / depth in `CrawlControls` and presses Start to queue + dispatch. |

**Right-click menu.** A crawled row carries its node into the menu (plus its
known id, so id-bound actions work even when the node isn't in the loaded graph
payload). An uncrawled row carries only its URL — id-bound actions (**Open in
Tor Browser**, Flag, Queue Analysis, Add to Collection, …) mint a stub node on
demand the first time one is invoked. Stubs are never created speculatively, so
right-clicking or browsing results does not pollute the graph. Open in Tor
Browser is gated on the kill switch being armed, matching the graph menu.

---

## Empty states

- No engines configured: "No search engines set up. Add one in Settings → Engines." (shown instead of the source selector and search bar)
- Before first search: "Enter a search query above to discover .onion sites via Tor."
- After search with no results: "No results found."
- If all sources failed due to connection errors: "All sources failed — is Tor running?"
- If sources failed for other reasons: "All sources failed — search engines may be down or blocking Tor exits."

---

## Stream event types

The search stream emits JSON objects:

| `type` field | Meaning |
|-------------|---------|
| *(absent)* | A URL result — pushed to results list |
| `probe` | Live title/description fetched for an uncrawled URL |
| `done` | Source finished; count field = total results from that source |
| `error` | Source failed; message field = reason |
| `all_done` | All sources finished; stream closes |

A URL result object includes the URL, source, and whether it has already been crawled.
For crawled results it also includes title, description, category, and last-seen date.
