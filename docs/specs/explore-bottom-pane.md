# Graph Tab — Bottom Pane

The bottom pane is a collapsible strip with eight sub-tabs. It is the primary sequential
investigation list — the analyst steps through nodes here one by one while the graph and
right panel follow.

---

## Selection model

The bottom pane maintains its own independent active row. It is the primary sequential
investigation list — the analyst steps through it node by node while the graph and right
panel follow.

**Clicking a row** — full selection: highlights the node in the graph, opens its detail
in the right panel, and marks this row as active.

**Clicking a node in the graph** — opens its detail in the right panel only. Does NOT
update the bottom pane's active row.

**Left pane search results** — highlight only: highlights the node in the graph, opens
right panel. Bottom pane active row untouched.

**Workspace context** — the bottom pane's Domains and Collection sub-tabs reflect the
active Graph tab workspace. Switching to a collection workspace tab filters Domains to
that collection and switches the Collection sub-tab to match. Bookmarks, Live Crawl,
Hidden, Flags, and Fingerprints sub-tabs always show global data regardless of workspace
context.

---

## Right-click context menu

Right-clicking any row in the bottom pane opens a context menu with actions for that
node or domain:

| Action | Behaviour |
|--------|-----------|
| **Send to Find** | Opens the Find sub-tab in the left pane and fills the search input with the domain name |
| **Send to Crawl** | Opens the Crawl sub-tab in the left pane and fills the seed URL input with the domain root URL |
| **Copy URL** | Copies the full URL to clipboard |
| **Rename alias…** | Opens a small inline popover to set or clear the domain alias. Pre-filled with current alias if set. Enter to save, Escape to close. |
| **Add to collection** | Opens the collection picker for this URL |
| **Flag** | Flags the URL for investigation |
| **Mark reviewed** | Toggles the reviewed state for this URL. Label shows "Mark reviewed" when unreviewed, "Mark unreviewed" when already reviewed. |
| **Open in Tor Browser** | Opens the URL in Tor Browser. Greyed out if the browser path is not configured in Settings → Browser. |
| **Remove from collection** | Removes this URL from the active collection. Only shown in the Collection sub-tab. |

The left pane switches to the correct sub-tab automatically on Send to Find / Send to
Crawl — the analyst does not need to manually switch.

---

## Header Row (always visible)

A single 24px-tall bar that persists even when the strip is collapsed.

- **▽ / △ toggle** — collapses or expands the content area; the header row stays visible
- **Eight sub-tab buttons** — Collection, Bookmarks, Live Crawl, Analyses, Domains, Flags, Fingerprints, Hidden

---

## Shared row interaction pattern

Every content sub-tab uses the same two-element row structure:

- **●/○ visibility button** — immediately hides or shows that domain's nodes in the graph. Filled dot = visible; empty ring = hidden. Hidden rows are dimmed in the list.
- **Content button** — full selection: selects the node in the graph, opens its detail in the right panel, and marks this row as the active bottom pane position.

---

## Sub-tab 1 — Collection

Shows every URL in whichever collection is currently active (set via the workspace tab).

**Sub-tab header** — when a collection is active, the header shows the collection name alongside three actions:
- **✎ Rename** — opens an inline input on the collection name. Enter to save, Escape to cancel.
- **↓ Export** — dropdown: `JSON` · `Nodes CSV` · `GEXF` — downloads the collection as a file.
- **🗑 Delete** — confirms with a dialog ("Delete 'X'? This cannot be undone."), then deletes the collection. Any open workspace tab for this collection closes automatically.

**Controls**
- Search input — filters by URL/domain substring
- Item count badge
- **Send to Crawl (all uncrawled)** button — shown only when the collection contains at least one stub. Switches to the Crawl sub-tab and stages the uncrawled URLs in the batch-confirm strip with the collection pre-selected as the target. The analyst confirms mode / stay-on-domain / depth once for the batch, then `Queue N` enqueues every row. Crawled pages are added to this collection automatically.

**Rows:** URL + page title (if crawled). Stub items show an amber `not crawled` badge in place of a title. Clicking a row selects that node in the graph (hollow node for stubs).

If no collection is active, the list shows "Open a collection workspace tab to view its contents." If the collection is empty, "No items in this collection."

---

## Sub-tab 2 — Bookmarks

Global saved seed bookmarks backed by the same `seeds` data source as the left-pane Crawl
bookmarks dropdown.

**Controls**
- URL/domain filter input
- Bookmark count badge
- Add bookmark button — opens the same URL + optional label save flow as the left Crawl pane

**Rows:** Label (or unlabeled), URL, added date, and actions:
- **▶ Send to Crawl** — switches to the Crawl sub-tab and loads the URL into the manual single-URL input. The analyst picks mode / collection / stay-on-domain / depth in `CrawlControls` and presses Start.
- **✎ Rename label** — inline label edit. Enter saves, Escape cancels.
- **✕ Delete** — removes the bookmark from `seeds`.

Any graph or bottom-pane right-click action labelled **Save as Seed Bookmark** writes to
this same source. The saved URL appears immediately in both this tab and the left-pane
Crawl bookmarks dropdown; duplicates show an already-saved toast and do not create a
second row.

## Sub-tab 3 — Live Crawl

A real-time crawl log fed by a live stream. The connection opens when the page loads and
stays open for the lifetime of the page.

**Controls**
- Domain filter input — narrows displayed log lines to those whose onion URL matches
- Entry count badge

**Rows:** Each log line is scanned for an onion URL. If a URL is found, the row is clickable
and selects that node. Lines are color-coded by HTTP status: green = 200, red = 4xx or error.
Up to 200 log lines are kept in memory (oldest drop off when the buffer fills).

---

## Sub-tab 4 — Analyses

Global log of all analysis records across every node — pending, running, and completed.
Loads on first switch to this tab; polls every **5 seconds** while active to reflect
jobs completing or new jobs being queued.

**Controls**
- Status filter dropdown — All / Pending / Running / Done
- Type filter dropdown — All / Summary / Risk Score / Entities / Category / Domain Label / Q&A
- Record count badge (filtered / total)

**Rows:** Each row shows:
- **URL** (truncated, green) with domain in smaller grey text below
- **Type** badge
- **Model** name in small grey text
- **Status** badge: `done` (teal) · `running` (pulsing teal dot) · `pending` (amber) · `waiting` (muted amber — stub not yet crawled)

**Clicking a row** — full selection: selects the node in the graph, marks this row as
active in the bottom pane, and opens the right panel with the **Analysis tab** active,
scrolled to the matching analysis record.

Empty state: "No analyses yet — queue a job from the Intel sub-tab or right-click a node."

---

## Sub-tab 5 — Domains

All `.onion` hostnames in the dataset, sorted by page count descending. Loads on first switch to this tab.

**Controls**
- Domain / alias filter input
- Domain count badge

**Rows:** Shows either the alias (if one is set) or the raw hostname, plus page count and fail count. Clicking a row triggers a **domain highlight**: all nodes from that host are highlighted in the graph and everything else is dimmed — this is not a multi-select and does not trigger the cluster workspace. The right panel opens the **Domain tab** driven by that domain (using the first crawled page's domain field, by `first_seen` ascending). The visibility toggle hides/shows all nodes from that host in the graph at once.

---

## Sub-tab 6 — Flags

URLs that have been flagged for investigation. Loads on first switch to this tab.

**Controls**
- URL filter input
- Status dropdown — All / Pending / Investigating / Done / Dismissed
- Priority dropdown — All / High / Medium / Low
- Filtered/total count badge

**Rows:** URL + priority badge (High/Med/Low, color-coded red/amber/green) + status label. Clicking a row selects that node and focuses it in the graph.

---

## Sub-tab 7 — Fingerprints

Groups `.onion` sites by shared HTTP response headers — the same unusual header:value appearing across multiple sites is a signal they may share infrastructure (same hosting provider, framework, or operator).

**Controls**
- **Sites ≥ N** — minimum site count threshold for a cluster to appear (default 2). Changing the value immediately reloads the list.
- **⟳** — manual refresh
- **CSV** — exports the visible cluster list as a CSV file

**Cluster list columns:** Header key · Header value · Site count · IDF score

IDF (inverse document frequency) measures how rare the header value is across all sites — a high IDF score means the header is distinctive and therefore a stronger fingerprint signal.

**Expanding a cluster row** (click ▶ or the row) lazy-fetches the member sites and shows them inline:

Each member row follows the same pattern as all other bottom pane rows:
- **●/○ visibility toggle** — immediately hides or shows that node in the graph
- **Content button** — full selection: highlights the node in the graph, opens its detail in the right panel, syncs the Nodes tab, marks this row active in the bottom pane

Right-clicking a member row opens the standard bottom pane context menu (Send to Find, Send to Crawl, Copy URL, Add to collection, Flag).

Member columns: URL · Risk score · Category

---

## Sub-tab 8 — Hidden

Manages the graph filter terms — strings whose presence in a node's URL or title causes that node to be excluded from the graph entirely. These persist across sessions and load at startup.

**Content**
- List of active filter terms, each with an ✕ remove button
- Add-filter input at the bottom — type a term and press Enter or click Add

Removing a term immediately unhides the matching nodes. Adding a term immediately hides them. Useful for decluttering the graph by suppressing known noise domains or path patterns.
