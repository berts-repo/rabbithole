# Graph Tab — Left Pane — Find Sub-tab

A quick lookup tool across all crawled data in the current project.

**Clicking a result** — highlight only: highlights the node in the graph and opens its
detail in the right panel. Does NOT update the bottom pane's active row. The analyst can
look up any node without losing their investigation position.

**Right-clicking a result** — opens a context menu:
Send to Crawl · Copy URL · Add to collection · Flag · Mark reviewed / Mark unreviewed · Open in Tor Browser.
Entity results also have: Send to Find · Send to Crawl · Copy (for onion URLs) or Copy only (all other types).

**Find state persists** across sub-tab switches. Switching back to Find after navigating
elsewhere shows the same query and results. Results are only cleared when the analyst
clicks ✕ or types a new query.

**Receiving a domain from the bottom pane** — right-clicking a row in the bottom pane and
choosing "Send to Find" opens this sub-tab and fills the search input with that domain
name automatically.

---

## Layout

Text input at top, two mode buttons below it, then results.

---

## Search input

- Placeholder: "Find in crawled data…"
- Typing triggers a debounced search after **300 ms**.
- Minimum query length: **2 characters**.
- A ✕ clear button appears inside the input when it has content.

---

## Mode toggle

Two buttons: **Keyword** and **Semantic**. Only one active at a time.

Switching modes clears results and re-runs the search if the current query is ≥ 2 chars.

---

## Keyword mode

Searches across page content (FTS5 full-text index), entity values, and analyst notes.
Returns a flat list of results ranked by relevance.

Each row shows:
- **Type badge** — `page`, `entity`, or `note` in small grey text
- **URL** — green, truncated
- **Match snippet** — the matched text or value shown below the URL in muted text
- **Title** — shown for page results when available

Clicking a row highlights the associated node in the graph and opens it in the right panel.

Empty state: "No results."

---

## Semantic mode

Returns up to 50 results ranked by vector similarity to the query. Requires the embedding
service to have indexed pages.

Each row shows:
- **Similarity score** — teal, tabular-numeric (0–1, higher = closer match)
- **URL** — green, truncated
- **Title** — shown when available

Empty state: "No semantic matches." If the embedding service has not run: "Semantic search
is unavailable — start the embedding service in Settings → Embedding."

---

## Data shapes

### Keyword mode response

Array of results, mixed types, ranked by relevance:

```
[
  { type: 'page',   url, title, snippet },
  { type: 'entity', url, entity_type, value },
  { type: 'note',   url, snippet }
]
```

### Semantic mode response

Array of `{ url, title, score }` — score is a float 0–1, higher = more similar.
