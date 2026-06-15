# Crawl — Left Pane Tab

**Crawl** is a sub-tab inside the left sidebar alongside Search and Intel.

The center tab bar entry for "Crawl" is removed. The left sidebar gains a third sub-tab: **Crawl**.

---

### Crawl controls

**Seed URL input** — single URL text field. The analyst types or pastes the seed URL for
this crawl, or receives one automatically via right-click "Send to Crawl" from the bottom
pane — which opens this sub-tab and fills the input with the domain root URL. Enter key
submits. Shows a toast on invalid URL.

**Bookmarks dropdown** — a small ★ button next to the URL input opens a dropdown list of
saved seed bookmarks. Selecting one fills the URL input. Empty state: "No saved seeds."

**Save bookmark** — a + button saves the current URL input to the bookmarks list. Opens
a small popover with a Label input (optional) and Save button.

**Mode** select — one of:

- `Cross-site` — Prioritises links that lead to new `.onion` hosts. Good for broad discovery.
- `BFS` — Breadth-first. Explores all links at the current depth before going deeper. Good for mapping a site completely.
- `DFS` — Depth-first. Follows each path as deep as possible before backtracking. Good for finding buried content.
- `Diverse` — Balances exploration across many sites simultaneously. Good for wide surveys.
- `Focused` — Scores pages by relevance to your Watchlist terms and prioritises the most relevant. Good for targeted investigations.

When `Focused` is selected, a contextual note appears below the selector:
> "Focused mode uses your Watchlist terms as the relevance signal. Pages matching more terms are crawled first."
> **Manage watchlist →** (opens Settings → Watchlist)

If the Watchlist is empty and Focused is selected, the note changes to a warning:
> "⚠ No Watchlist terms configured — Focused mode has no signal. Add terms in Settings → Watchlist before starting."
> The Start button is disabled until at least one term exists.

**Stay on domain** — checkbox, default off. When checked, the crawler only follows links
that stay on the same `.onion` host as the seed URL — outbound links to other `.onion`
sites are recorded as edges but not queued for crawling. Useful for fully mapping a single
site without drifting to others.

Disabled (greyed out) when `Cross-site` mode is selected — cross-site mode is explicitly
about following links to new hosts, so the two options are mutually exclusive. A tooltip
explains: "Cross-site mode follows links across domains — disable it to use Stay on domain."

**Max depth** — numeric input next to the mode selector, default `3`. Caps how many
hops the crawl follows from the seed URL — a privacy / blast-radius hardening so a
"small look around" can't quietly become tens of thousands of pages. An explicit
**Unlimited** affordance sends `max_depth=null` and surfaces a one-line warning:
"this crawl can run indefinitely." Snapshotted on the queue row at enqueue (changing
the dropdown afterwards doesn't affect already-queued rows).

**Pacing** select — controls how fast the crawler issues requests, default `Polite`:

- `Fast` — no delay between requests. Good for bulk sweeps of low-risk sites.
- `Polite` — a short jittered delay between requests. The default.
- `Stealth` — a human-scale jittered delay. For targets that watch their logs.

The choice persists across crawls (stored as the `crawl.pacing` setting) and is read by
the crawl runtime when a crawl starts. Pacing removes the timing tell of a gap-free
machine cadence; it does not make a crawl's link-following order look human.

**Add results to collection** — optional dropdown of existing collections plus a
`+ New collection…` option. When set, every successfully crawled node from this run is
automatically added to the chosen collection. Leave blank to crawl without collecting.

**Start / Stop buttons**
- **Start** — disabled if URL input is empty or if a crawl is already running.
- **Stop** — disabled if not running.

**Status row** — shown while a crawl is running:
- Seed URL of the active crawl
- Pages crawled / failed / queued counts (live, updates via SSE)
- Elapsed time

---

### Batch-confirm strip

A panel that sits between the Crawl controls and the Crawl queue. Visible only when a
multi-row batch has been staged for confirmation — hidden otherwise.

Multi-row sources stage rows into the strip rather than enqueueing directly: Bulk
Import's `Queue all N URLs` button, the bottom-pane Collection sub-tab's
**Send to Crawl (all uncrawled)**, multi-select **Send to Crawl** from the graph
context menu, and the right panel's cluster-workspace **Send to Crawl** button.
The Crawl sub-tab is switched into view automatically when staging happens.

Layout:

- Header: "Batch from {source} — N URLs" plus a `✕` button that discards the staged
  rows without enqueueing.
- One mode / collection / stay-on-domain / depth row whose values apply to every
  staged URL. Defaults mirror the current values from the Crawl controls above so
  the common "use the same settings I already had picked" path is one click.
- A summary row showing how many URLs are new vs already in the queue (the
  enqueue dedupe rule still applies on the backend regardless).
- **Queue N** button — enqueues every staged row in a single `POST /api/crawl/queue`
  call with the chosen options, then hides the strip.

The strip is single-batch: starting a second staging operation while one is staged
replaces the first (with a toast: "Replaced previous batch — N URLs").

---

### Crawl Queue

The durable crawl queue lives directly below the batch-confirm strip and above
Bulk Import. It is the project-wide FIFO that every intake surface drains into,
backed by the `crawl_queue` table. Rows persist across crawls and process
restarts.

**Header controls**:

- **Pause / Resume queue** toggle — single project-level flag persisted in
  `settings`. When paused, new rows still insert; the runner does not advance.
- **Clear completed** button — removes terminal-state rows (`completed`,
  `cancelled`, `skipped`) from the list. Status-filtered so `failed` rows are
  preserved (they need explicit Retry or Remove).
- Count line: "N queued · M running · K done · F failed".

**Rows** — one per queue entry. Each shows:

- URL (truncated with ellipsis; full URL on hover).
- Lookup badge — `unknown` / `crawled` / `stub`.
- Status — `queued` / `running` / `completed` / `failed` / `cancelled` /
  `skipped`.
- Mode chip and collection chip (resolved name or pending-name placeholder).
- Source badge (e.g. `bulk`, `manual`, `schedule`).

**Row actions**:

- **Start next** — bumps this row's `priority` so the runner picks it up next.
  Available on `queued` rows.
- **Remove / Cancel** — for `queued` rows: status → `cancelled`. For `running`
  rows: invokes the cooperative stop and lets the runner's completion path mark
  the row `cancelled`. For terminal rows: deletes the row from the table.
- **Retry** — `failed` rows only. Resets to `queued`, clears `error`, bumps
  `attempts`.
- **Edit** — `queued` rows only. Inline edit for mode / collection /
  stay-on-domain / `max_depth`. Refuses on non-`queued` rows.

The list updates live via the `crawl_queue.changed` SSE channel.

---

### Bulk Import

For when the analyst has a list of domains from an external source — a forum post, a paste
dump, a tip — and wants to act on them without entering each one individually.

**Paste area** — multi-line textarea (placeholder: "Paste domains or URLs, one per line…").
On paste or input, the list is parsed immediately — one entry per line, whitespace trimmed,
blank lines ignored.

**Parsed list** — each entry appears as a row below the textarea showing the URL and one of
three states:
- `crawled` — already crawled; shown in teal with page count
- `stub` — added by the analyst but not yet crawled; shown in amber
- `unknown` — not in the DB at all; shown in grey

Each row has action buttons:
- **▶ Send to Crawl** — loads this URL into the Crawl controls' manual single-URL input above and focuses it. Use for the "I want this single one on different options" path. Does not enqueue on its own — the analyst picks options and presses Start.
- **+ Stub** — creates a stub node for this URL (uncrawled rows only). The URL is added to the system immediately and appears as a hollow node in the graph. The analyst can then add it to a collection, flag it, or crawl it later.
- **+ Collection** — opens the collection picker. Available for both crawled rows and stub rows (creating a stub first if needed).

Clicking a row that is crawled or already a stub performs a highlight-only selection — graph and right panel update to show that node without affecting the bottom pane.

Below the parsed list:

- **Queue all N URLs** button — stages every parsed row into the batch-confirm strip above (analyst confirms mode / collection / depth once; rows enqueue on `Queue N`). The common multi-URL paste path.
- **Clear** button — dismisses all entries and resets the textarea.

---

### Scheduled Crawls

Auto-triggered crawls on a repeating timer. Each schedule has one seed URL.

**Add schedule form:**
- **URL** input — the seed URL for this schedule
- **Label** input (optional)
- **Interval** input — hours between runs (minimum 0.25)
- **Mode** select — same five options as the main crawl mode
- **+ Add** button — submits the form and adds the schedule to the list

**Schedule list** — each row shows label/URL, interval, mode, and two action buttons:
- ⏸ / ▶ — pause or resume the schedule
- ✕ — remove it
