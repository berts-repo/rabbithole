# Graph Tab — Graph Canvas

The graph canvas is the centre column of the Graph tab. It renders the crawled link graph
as an interactive node-link diagram. The graph data is refreshed by **polling every 15 seconds** — this is the only graph update mechanism. The live crawl log (bottom pane, Live Crawl sub-tab) uses SSE separately for real-time log lines; graph updates do not use SSE.

---

## Workspace tabs

A tab bar sits above the graph toolbar. Each tab is an independent graph workspace with
its own layout, node positions, selected node, and ego-focus state.

**Global tab** — always present, cannot be closed. Shows the full DB graph — every crawled
node regardless of collection membership.

**Collection tabs** — each open collection gets its own tab showing only that collection's
nodes and the edges between them. Opening a collection tab does not close others.

**+ button** — opens a collection picker to open a new workspace tab. If the collection
is already open as a tab, switches to it instead of opening a duplicate.

**Closing a tab** (✕) — removes the workspace tab. The collection itself is not deleted.
Global tab cannot be closed.

**Collection deleted while tab is open** — the workspace tab closes automatically. Toast: "Collection deleted — workspace closed."

**Active workspace context** — the active tab propagates its context to the rest of the
shell:
- Bottom pane Collection sub-tab switches to that collection
- Bottom pane Domains sub-tab filters to that collection's domains
- Switching to the Global tab restores all views to full DB scope

Each workspace tab is an independent instance of the graph component — layouts, physics
state, and selections do not bleed between tabs.

---

## Graph toolbar

A 34 px bar at the top of the graph canvas. Left to right:

**Status line** — "updated HH:MM:SS · N nodes · M edges · D domains · P pages", with a
pulsing teal dot. Nodes/edges track the rendered (filtered) graph; domains/pages are the
active workspace's crawled-page total and its distinct-host count, off the raw payload.
While in draw-edge mode, the status line is replaced by instruction text
("Click source node" / "Click destination node").

**Draw analyst edge** (Spline icon) — behaviour depends on how many nodes are currently selected.

**No selection or 1 node selected — sequential mode:**
Enters draw-edge mode. While active, clicking nodes follows a source→destination sequence rather than normal select behaviour. Pressing Escape or clicking Cancel exits the mode.
1. Click a source node (highlighted in canvas).
2. Click a destination node → the **Draw analyst edge** modal opens.

**≥2 nodes selected — batch mode:**
The modal opens immediately — no clicking required. The selection is the node set.

**Draw analyst edge modal:**
- In sequential mode: shows `source URL → destination URL`.
- In batch mode: shows "Connect N selected nodes — will create M edges." Lists the selected URLs.
- **Type** select: `Same operator`, `Shared wallet`, `Mirrors`, `Affiliate`, `Custom…`
- If `Custom…` selected, a free-text **Label** input appears. The same label applies to all created edges.
- **Create** — adds dashed green analyst edges. In batch mode, creates a fully-connected set of edges between every pair in the selection.
- **Cancel** — closes modal; selection and graph unchanged.

**Expand to collection** (FolderPlus icon) — disabled unless at least one node is selected.
Click opens a small popover:
- **Collection** dropdown — lists all collections. Pre-filled with the current workspace collection if one is open; otherwise blank. Includes a **+ New collection** option at the bottom that creates one inline (name input → Enter).
- **Hops** selector: 1 / 2 / 3 — how many hops out from the selected node(s) to expand.
- **Add to collection** button — adds all nodes within the hop radius to the chosen collection. Disabled until a collection is selected.

**Layout picker** — a dropdown selecting from five layouts. A layout is a
transform that runs once and **freezes**: it positions the fetched nodes, then
the poll diff-update and drag-to-move own those positions until the next
explicit re-layout (Reset, or re-picking). There is no perpetually-running
physics simulation.
- `Force` — ForceAtlas2, the default. Runs in a Web Worker over the *fetched*
  subgraph only (stubs are halo-placed, never force-laid-out) and settles in a
  bounded budget, then freezes. Best general "shape of the crawl" view.
- `Radial` — pages grouped into per-domain hubs on a ring; instant geometry.
- `Hierarchical` — top-down tiers by crawl depth (seed depth 0 at the top).
- `Concentric` — rings by crawl depth from the seed (depth 0 at centre).
- `Timeline` — positions nodes by `first_seen` date down the y-axis, same-day
  nodes spread across x columns, undated nodes in a column to the left.
  A timeline legend (date range, day count, undated count) appears
  bottom-centre of the canvas.

**Stop** (Square icon) — visible **only** while the Force layout is settling.
Clicking it freezes the arrangement at its current frame instead of waiting
out the settle budget. (This replaces the old "Pause / Resume physics" control
— with run-to-settle layouts there is no perpetual simulation to pause.)

**Fit** (Maximize2 icon) — fits all visible nodes in view (animated, 300 ms).

**Reset layout** (RotateCcw icon) — re-runs the active layout from scratch
against the current graph.

**Export** (Download icon) — dropdown with:
- `GEXF (.gexf)` — full graph export as GEXF for Gephi
- `Nodes CSV (.csv)` — flat CSV of all visible nodes

**Resume** — visible **only** when the kill-switch FSM is in `cleared_idle`. Hidden otherwise. Clicking it transitions the FSM back to `armed` and re-arms the graph poller and any user-started crawl/worker the user explicitly resumes. The button exists because clearing a tripped kill switch does NOT auto-resume — see `docs/specs/app-shell.md` (kill switch section) and `docs/work/archive/2026-05-20-fixes/checklist.md` §6c for the rationale.

---

## Node interactions

**Stub nodes** — URLs discovered by the crawler (or added by the analyst) but not yet fetched. Rendered as small dots (size 2.5) in a **halo around their parent** fetched node — the fan position encodes the only fact we know about them, "who linked here". A page with 200 dots in its halo visually screams *link directory*; an isolated stub is the only mention of that URL anywhere. Stubs are never run through the force-directed layout — they always orbit their parent — so toggling **Show stubs** is instant regardless of stub count. All other node interactions apply (click, right-click, multi-select). Double-clicking a stub node pre-fills the Crawl sub-tab with that URL and switches focus to it. Stubs are excluded from graph metrics (PageRank, betweenness, cluster) since their only edge is the inbound link from their discoverer.

**Single click** — selects the node and auto-expands the right panel.

**Hover** — dims all non-adjacent nodes and edges (hover-dim). Adjacent nodes and their
connecting edges remain at full opacity. Clears when mouse leaves the node.

**Multi-select** — build a selection using any of:

| Input | Behaviour |
|-------|-----------|
| Ctrl+click a node (`Cmd+click` on macOS; `Shift+click` also works) | Adds or removes that node from the selection |
| Drag on empty canvas | Box-select — rectangle encloses all nodes inside |
| Ctrl+A | Selects all currently visible nodes. If the visible node count exceeds 50, a confirmation dialog appears: "Select all N nodes? Bulk actions will apply to every one." — Select all / Cancel. |
| Click a node (no Shift) | Replaces entire selection with just that node |
| Click empty canvas (no drag) | Deselects all |
| Escape | Deselects all (or exits ego-focus if active) |

When ≥ 2 nodes are selected, only the selected nodes and their shared connections are fully
visible; everything else dims. The graph status line switches to **"N nodes selected"**
replacing the normal updated/node/edge count. The right panel switches to the cluster
workspace (see below).

**Right-click on a node** — opens a context menu. Stateful items show their current state in the label. Dividers have labels.

| Item | Action |
|------|--------|
| **Copy URL** | Copies URL to clipboard |
| **Open in Tor Browser** | Copies URL to clipboard + launches fresh isolated Tor Browser instance. Records `opened_at`. |
| **Rename alias…** | Opens a small inline popover to set or clear the domain alias. Pre-filled with current alias if set. Enter to save, Escape to close. |
| *— CRAWL —* | |
| **Send to Crawl** | Switches to the Crawl sub-tab and loads this URL into the manual single-URL input. Available on any node (not stub-only). The analyst picks mode/collection/stay-on-domain/depth in `CrawlControls` and presses Start to queue + dispatch. |
| **Save as Seed Bookmark** | Saves the URL to the crawl bookmarks list for future use. |
| *— INVESTIGATION —* | |
| **Flag** / **Remove Flag** | Toggles flag on the node |
| **Mark Reviewed** / **Mark Unreviewed** | Toggles reviewed state |
| **Add Monitor…** | Opens the Add Monitor modal pre-filled with this URL. Works on stubs — monitors just ping the URL for uptime. |
| *— ANALYSIS —* | |
| **Queue Analysis** | Queues an AI analysis job. On stub nodes the job sits in `waiting` status and fires automatically when the stub is crawled. |
| **Clear Analyses** | Deletes all AI analyses for this node |
| *— GRAPH —* | |
| **Focus** | Enters ego-focus mode for this node |
| **Hide from Graph** | Adds the URL as a graph filter term, permanently hiding it. *(Crawled nodes only)* |

**Add Monitor modal** — opens when "Add Monitor…" is selected. Fields:
- **URL** — pre-filled from the node, read-only
- **Label** — optional text input
- **Interval** — hours between checks (min 0.25, default 24)
- **Alert on content change** — checkbox, default on
- **Alert on restore** — checkbox, default on
- **Downtime alert after N hours** — number input, default 48
- **Add** / **Cancel** buttons

The same form component is used here and in the Domain tab's Add Monitor form.

**Right-click on an analyst edge** — shows a context menu with "Delete analyst edge".
Only appears on dashed analyst edges (source = 'analyst'), not on crawl-derived edges.

**Right-click with multiple nodes selected** — context menu with labelled dividers. Items that don't apply to the current selection are greyed out with a short reason rather than hidden.

| Item | Action |
|------|--------|
| **Add to Collection** | Collection picker — adds all selected nodes (stubs and crawled) |
| **Draw Edge…** | Opens the Draw analyst edge modal in batch mode — creates fully-connected analyst edges across the entire selection. |
| *— CRAWL —* | |
| **Send to Crawl** | Switches to the Crawl sub-tab and stages the selection in the batch-confirm strip — the analyst confirms mode / collection / stay-on-domain / depth once for the whole batch, then `Queue N` enqueues every row. Available regardless of stub state (already-crawled nodes can be re-queued). |
| *— INVESTIGATION —* | |
| **Flag All** | Flags all selected nodes immediately (stubs and crawled) |
| **Mark Reviewed** | Marks all crawled nodes as reviewed. Greyed out if selection is all stubs. |
| *— ANALYSIS —* | |
| **Queue Analysis…** | Opens the Queue Analysis modal. Stubs in the selection receive `waiting` status jobs. |
| *— GRAPH —* | |
| **Hide All** | Adds all crawled nodes to the graph filter. Greyed out if selection is all stubs. |

**Queue Analysis modal** — opens when "Queue Analysis…" is selected from the multi-select
context menu. Fields:
- **Type** dropdown — Summary / Risk Score / Entities / Category / Domain Label / Q&A
- **Question** text input — appears only when Q&A is selected; required; applies to every
  selected node
- **Skip already-queued** checkbox — default on; nodes that already have a pending or
  running job of the selected type are skipped
- **Queue N nodes** button (count excludes stubs)

On confirm a toast shows the result: _"Queued summary for 14 nodes (2 skipped — already queued, 3 stubs excluded)."_ Jobs are stored in the `analyses` table per node as normal and appear in the bottom pane Analyses sub-tab and the Intel queue.

**Double-click on a cluster node** — expands the domain cluster, showing individual pages.

---

## Ego-focus mode

Triggered by the right-click context menu → Focus, or another part of the UI requesting
focus mode.

Shows only the selected node and all nodes reachable within N hops (default 2).
A floating overlay appears top-centre of the canvas:
- Domain name of the focus node.
- `Depth: N` label + range slider (1–3 hops).
- ✕ button to exit (also exits on Escape).

**Clicking another node while in ego-focus** — re-focuses on the clicked node immediately. The overlay updates to show the new domain name; depth setting is preserved. This keeps the analyst in the exploration flow without needing to exit and re-enter focus.

---

## Collection picker modal

Appears when a search result's add-to-collection button is clicked (adds a single URL) or when the
multi-select collection action is triggered. Lists all collections; clicking one adds the URL(s).

---

## Graph data

The graph data includes computed metrics such as PageRank, betweenness, cluster membership,
infrastructure grouping, and bridge status. The UI applies filters client-side and updates
the rendered graph incrementally.

Node fields used by the canvas (from the graph API response):

| Field | Used for |
|-------|---------|
| `id` | Graph node ID |
| `raw_url` | URL selected on click |
| `label` | node label shown on canvas |
| `title_text` | tooltip text shown on hover — always rendered with `textContent`, never as HTML |
| `color` | base fill colour |
| `domain` | grouping, edge filter, domain cluster |
| `depth` | concentric layout, max-depth filter, depth colour |
| `flag_status` | flag overlay border |
| `is_bridge` | bridge overlay |
| `betweenness` | bridge overlay threshold |
| `in_degree_count` | bridge overlay |
| `out_degree_count` | available in graph data |
| `pagerank` | available in graph data |
| `cluster_id` | color-by-cluster |
| `infra_cluster_id` | color-by-infra |
| `first_seen` | timeline layout |
| `is_cluster` | cluster node used for domain grouping |
| `stub` | renders node as hollow with dashed outline; excludes from metrics |
| `analysis_excluded` | renders a small `⊘` icon overlay on the node so excluded pages are identifiable in the graph |

Edge fields:

| Field | Used for |
|-------|---------|
| `from`, `to` | Edge endpoints |
| `source` | Analyst-created edges are rendered as dashed green |
| `label` | shown on analyst edges |
