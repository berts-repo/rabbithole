# Right Panel — Node Detail & Analysis

The right panel is a collapsible detail pane on the far right of the shell. It is
context-aware: it shows information about whichever node is currently selected across the
whole app.

---

## Panel-level behaviour

**Collapsed / expanded**
- Default state: collapsed (shows a 24 px sliver with only the toggle button).
- Toggle button (◀ / ▶) in the top-left corner of the panel collapses/expands it.
- Selecting any node **auto-expands** the panel — unless the user has explicitly collapsed
  it themselves.
- Collapse state is not persisted; the panel always starts collapsed on page load.

**Tab bar**
Three tabs across the top of the expanded panel:
- **Page** — page-level metadata, collections, flag, and notes.
- **Domain** — domain-wide profile, pages, entities, and uptime monitors.
- **Analysis** — LLM analysis results for the selected page.

Active tab persists across sessions; the default is Page.

When no node is selected both tab contents show a placeholder message and make no API calls.

**Stub node selected** — when the selected node is a stub (not yet crawled), the panel shows a simplified state across all three tabs:
- **Page tab** — shows the URL, the amber `not crawled` badge, collection membership, flag section (if flagged), and notes. No title, content, entities, headers, or version history. A prominent **Send to Crawl** button switches to the Crawl sub-tab and loads this URL into the manual single-URL input — the analyst picks mode / collection / stay-on-domain / depth in `CrawlControls` and presses Start.
- **Domain tab** — shows uptime monitors for the domain (monitors work on stubs — they just ping the URL for uptime). The Add Monitor form is fully functional. Domain profile stats and pages list show "Not yet crawled."
- **Analysis tab** — shows any queued analysis jobs with `waiting` status. The Queue Analysis form is available — jobs queued here will fire automatically when the stub is crawled. Shows a notice: "Jobs will run when this URL is crawled."

---

## Page tab

Loaded when the Page tab is active. It fetches node detail, collection membership, and notes
in parallel on every URL change.
While loading shows "Loading…". If the API returns an error for the node detail shows "Node not found".

### Header block

- **URL** — full URL in small green text, wrapping as needed.
- **Domain alias** — if an alias is set it appears below the URL in italic grey. A ✎ pencil icon beside it opens the **Rename alias** popover:
  - Full URL shown read-only for context.
  - Text input pre-filled with current alias (blank to clear). Enter to save, Escape to close.
  - On save: toast "Renamed to X" or "Alias cleared"; graph label refreshes.
- **Title** — page title if present, slightly larger and lighter.
- **Meta chips** — shown as small pill badges:
  - HTTP status code (e.g. `HTTP 200`)
  - Crawl depth from seed (e.g. `depth 2`)
  - Category label if set
- **Reviewed toggle** — a `✓ Reviewed` button in the header. When the node's `reviewed`
  field is true the button is filled/active; clicking it toggles the state and saves
  immediately. When false the button is outlined/inactive.
- **Exclude from analysis toggle** — a `⊘ Exclude` button alongside Reviewed. When active
  the page is skipped by the crawl auto-queue and will not appear in the Intel queue list.
  Toggling off re-enables auto-queuing for this page.

- **Summary** — if the node has an AI-generated summary, it is shown
  here as a block of body text.

### Collections section

Header: `In collections` with an `+ Add` button.

- If the node belongs to any collections, they are shown as green pill badges. Each pill has a ✕ button that removes the node from that collection immediately (no confirm). The pill disappears on removal.
- Clicking `+ Add` opens a floating dropdown picker. The picker fetches all collections lazily on first open (fetched once, cached in component state). Collections the node already belongs to are shown with a checkmark and are not re-selectable.
- Clicking a collection name in the picker adds the node to that collection and shows a toast (`Added to collection`). The picker closes and the pills update.

### Flag section

Shown only when the node has an active flag. Header: `Flag`.

- **Status select** — `pending` | `investigating` | `done` | `dismissed`. Saved immediately on change.
- **Priority select** — `High` (1) | `Medium` (2) | `Low` (3). Saved immediately on change.
- **Note textarea** — free text, saved on blur.
- **Remove flag** button — deletes the flag record. The section disappears without reload.

### Details toggle

A Details toggle button shows or hides the expanded detail block.
Starts expanded on every node load.

### Expanded detail block

Visible when the Details toggle is open.

**Content preview** — first ~500 chars of visible page text, monospace, max 80 px tall
with internal scroll.

**Entities** — shown when the node has extracted entities. Header: `Entities (N)`.
Each row shows the entity type label and value. Common types include email, BTC, XMR, PGP,
onion, handle, and blob.

Clicking or right-clicking an entity row opens a context menu. Available actions depend on type:

| Type | Actions |
|------|---------|
| Onion URL | Send to Find · Send to Crawl · Copy |
| Handle | Send to Find · Copy |
| Email / BTC / XMR / PGP / blob | Copy |

Send to Find opens the Find sub-tab in the left pane and fills the input with the entity value. Send to Crawl opens the Crawl sub-tab and fills the seed URL input.

**Response Headers** — collapsible `<details>` block, open by default. Header:
`Response Headers (N)`. Shows a two-column table: header name (green, monospace) / value
(grey, monospace, wraps).

**Version History** — collapsible `<details>` block, open by default. Header:
`Version History (N)`. Shows one row per historical crawl of this URL:
- Timestamp formatted with `toLocaleString()`
- HTTP status code

**Notes** — always shown in the expanded block.
- Existing notes are listed; each has a ✕ button to delete.
- Textarea + `Save note` button to add a new note. Save is disabled for blank input (trimmed).
- Both save and delete refresh the notes list from the API.

---

## Domain tab

Loaded when the Domain tab is active. Uses the `domain` field from the page detail response to
scope all data to the selected node's `.onion` host. Makes no API calls when no node is selected.

### Domain profile card

A compact summary block showing four stat chips:

| Chip | Value |
|------|-------|
| Pages | Total pages crawled for this domain |
| Flags | Total active flag count for this domain |
| Entities | Total entity count for this domain |
| Uptime | Last HTTP status if a monitor exists (`Up` in teal / numeric status in red), or `–` |

Below the chips, a two-column middle row:

**Activity sparkline** — SVG polyline of page discovery over time (bucketed by day). x-axis = time,
y-axis = pages per day. Dots at each data point (tooltip: "YYYY-MM-DD: N pages"). Single-day data
shows as a text label instead. No data shows "No dated pages".

**Entity type breakdown** — horizontal row of small chips, one per entity type extracted from this
domain (e.g. `email 3`, `btc 1`).

### Pages

List of all crawled pages for the domain. Capped at 200 rows. When the cap is hit, a note appears below the list: "Showing 200 of N pages — view all in the Domains tab." Clicking that link switches to the bottom pane Domains sub-tab with this domain pre-selected.

Each row:
- URL path (full URL minus host prefix), truncated with ellipsis.
- Optional title.
- HTTP status code chip.

Clicking a row performs a **highlight-only** selection of that page URL — updates the graph highlight and right panel but does not move the bottom pane active row.

Right-clicking a row opens a context menu: Send to Find · Send to Crawl · Copy URL · Add to collection · Flag · Mark reviewed / Mark unreviewed · Open in Tor Browser.

### Entities

Full list of extracted entities for the domain. Each row: type (fixed-width, grey) + value (monospace).

A **"View fingerprint clusters →"** link sits below the entity list. Clicking it switches to the bottom pane Fingerprints sub-tab pre-filtered to show only clusters that include this domain. Useful for finding other sites that share this domain's response header signatures.

Clicking or right-clicking an entity row opens a context menu. Available actions depend on type:

| Type | Actions |
|------|---------|
| Onion URL | Send to Find · Send to Crawl · Copy |
| Handle | Send to Find · Copy |
| Email / BTC / XMR / PGP / blob | Copy |

### Uptime monitors

Monitor records scoped to the selected node's hostname.

Each monitor row: label/URL, last HTTP status (`Up` in teal if 200, numeric otherwise), and
⏸/▶ toggle + ✕ remove buttons.

**Add monitor form** below the list:
- URL input (Enter to submit)
- Label input + Interval input (hours, min 0.25) + Add button
- Collapsible **Alert settings** section:
  - Alert on content change (checkbox, default on)
  - Alert on restore (checkbox, default on)
  - Downtime alert after N hours (number input, default 48)

---

## Analysis tab

Loaded when the Analysis tab is active. Reloads on every node change.

### Analyses list

One row per analysis record for the selected node. Each row shows:
- **Type** — analysis type label (for example summary, risk score, or Q&A), green.
- **Status** badge:
  - `done` — teal
  - `pending` — amber
  - `running` — pulsing teal dot
  - `waiting` — muted amber; tooltip "Waiting — crawl this URL first."
- **Model** — model name in small grey text below, omitted if null.
- **Re-run** button — shown only on `done` rows. Re-queues the same job type and model, resets status to `pending`, clears the existing result. Toast: "Re-queued."
- **✕ button** — deletes this specific analysis record immediately. No confirm. Toast: "Analysis removed."

Clicking a row selects it (highlighted background) and loads its result.

### Result pane

Appears below the list when a row is selected. Takes up to 50% of the pane height with its own scroll.

- **Meta line** — type, model, and status in small grey text. Status turns teal when done.
- **Question line** — shown only for Q&A analyses. Displays the original question in italic grey above the result body.
- **Result body** — monospace pre-formatted text with line wrapping. Background dark green block.
- If status is pending: shows "In queue…"
- If status is running: shows "Running…"
- If status is done but result is empty: shows "No result yet."

The result is fetched only when the status is `done`; pending/running rows show their
status message without an API call.

---

## Data shapes

### Node detail response

| Field | Type | Notes |
|-------|------|-------|
| `url` | string | Canonical URL |
| `domain` | string | `.onion` hostname — used to fetch domain-section data |
| `title` | string \| null | Page title |
| `status_code` | int \| null | HTTP response code |
| `depth` | int \| null | Crawl depth from seed |
| `category` | string \| null | Heuristic category label |
| `summary` | string \| null | LLM-generated summary |
| `body_text_preview` | string \| null | Short text excerpt (~500 chars of body_text) |
| `reviewed` | boolean | Whether the node has been marked reviewed |
| `entities` | array | See below |
| `response_headers` | object \| null | Key → value string map |
| `history` | array | See below |
| `flag` | object \| null | See below |

**`entities[]`**

| Field | Type |
|-------|------|
| `type` | string |
| `value` | string |

**`history[]`**

| Field | Type |
|-------|------|
| `crawled_at` | ISO-8601 string \| null |
| `status_code` | int \| null |

**`flag`**

| Field | Type |
|-------|------|
| `id` | int |
| `status` | `pending` \| `investigating` \| `done` \| `dismissed` |
| `priority` | `1` (High) \| `2` (Medium) \| `3` (Low) |
| `note` | string \| null |

### Node collections response

Array of `{ id, name }` objects — collections the node belongs to.

### Notes response

Array of `{ id, body }` objects.

### Analyses list response

Array of analysis objects:

| Field | Type |
|-------|------|
| `id` | int |
| `analysis_type` | string |
| `status` | `pending` \| `running` \| `done` \| `waiting` |
| `model` | string \| null |
| `question` | string \| null |

### Analysis result response

`{ result: string }` — the completed analysis text.

### Domain profile response

| Field | Type | Notes |
|-------|------|-------|
| `page_count` | int | Total pages crawled for this domain |
| `flag_count` | int | Total active flags for this domain |
| `entity_count` | int | Total entities extracted for this domain |
| `last_status` | int \| null | Most recent HTTP status from a monitor, or null if no monitor |
| `activity` | array | See below |
| `entity_types` | array | See below |

**`activity[]`**

| Field | Type |
|-------|------|
| `date` | ISO-8601 date string |
| `count` | int |

**`entity_types[]`**

| Field | Type |
|-------|------|
| `type` | string |
| `count` | int |

### Domain pages response

Array (up to 200) of:

| Field | Type |
|-------|------|
| `url` | string |
| `title` | string \| null |
| `status_code` | int \| null |

### Domain entities response

Array of:

| Field | Type |
|-------|------|
| `type` | string |
| `value` | string |

### Domain monitors response

Array of:

| Field | Type |
|-------|------|
| `id` | int |
| `url` | string |
| `label` | string \| null |
| `interval_hours` | number |
| `enabled` | boolean |
| `last_status` | int \| null |
| `alert_on_change` | boolean |
| `alert_on_restore` | boolean |
| `downtime_threshold_hours` | number |

---

## Cluster workspace (multi-select state)

When ≥ 2 nodes are selected in the graph, the right panel switches from the normal three-tab
view (Page / Site / Analysis) into the cluster workspace. The normal tabs are hidden and
replaced with three cluster-specific tabs:

**Nodes** (default) — the managed selection list.
- Each row shows the selected URL. Stub nodes show an amber `not crawled` badge. ✕ button removes that node from the selection. When the selection drops to 1 node the panel snaps back to the normal single-node view immediately.
- **Add to collection** button — opens the collection picker to add all selected nodes to an existing collection.
- **Save as new collection** button — opens a small popover with a name input. Creates a new collection and adds all selected nodes (stubs included) to it.
- **Send to Crawl** button — switches to the Crawl sub-tab and stages the selection in the batch-confirm strip. The analyst confirms mode / collection / stay-on-domain / depth once for the whole batch, then `Queue N` enqueues every row. Available regardless of stub state (already-crawled nodes can be re-queued).
- Clearing the selection (Escape, click empty canvas) returns the panel to the normal single-node view.

**Q&A** — cross-node question and answer.
- If the selection contains stubs, a notice at the top: "N stubs excluded — Q&A requires crawled content."
- Single question textarea (placeholder: "Ask a question about all selected pages…").
- **Ask all** button — queues a Q&A analysis job for every **crawled** node in the selection. Stubs are skipped. Respects the same skip-already-queued logic as the Queue Analysis modal.
- Results appear inline as they complete — one block per node: URL in small green text, answer body below. Polls every 5 s while any jobs are pending or running.
- Empty state before asking: "Enter a question and press Ask all."
- If all selected nodes are stubs: button is disabled, notice reads "No crawled nodes in selection."
- Results are stored in the `analyses` table per node as normal, so they also appear in the bottom pane Analyses sub-tab and the right panel Analysis tab per node.

**Common** — shared entities across the selected nodes.
- If the selection contains stubs, a notice at the top: "N stubs excluded — no entities available until crawled."
- Fetched once on tab open (crawled nodes only); a ⟳ refresh button is available.
- Lists entity values that appear on ≥ 2 of the selected crawled nodes, grouped by type.
- Each entity row shows: type chip · value (monospace) · "seen on N / M nodes" count.
- Clicking or right-clicking an entity opens the same context menu used elsewhere (Onion URL: Send to Find · Send to Crawl · Copy; Handle: Send to Find · Copy; all others: Copy).
- Empty state: "No shared entities across selected nodes."
- Backend: a single query — GROUP BY entity value WHERE node_id IN (...) AND stub = false HAVING count ≥ 2.

---

## Shared selection

All three tabs react to the app's current node selection and update automatically. Two types
of selection exist:

**Full selection** — triggered by clicking a row in the bottom pane. Updates the graph
highlight, the right panel, and the bottom pane's active row.

**Highlight only** — triggered by clicking a node directly in the graph, or a search
result in the left pane Find sub-tab. Updates the graph highlight and the right panel
only. The bottom pane's active row is never affected.
