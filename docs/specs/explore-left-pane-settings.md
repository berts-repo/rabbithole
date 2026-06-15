# Settings Modal

Accessed via the ⚙ gear icon in the app header (top-right of the tab row). Opens as a
large centered modal overlay. Closed with ✕ or Escape.

All settings are persisted in the `settings` key/value table in the project DB. Changes
take effect immediately — no Save button needed.

The gear icon shows a dot badge when any non-default graph setting is active.

---

## Five tabbed sections: Graph · Engines · Watchlist · Browser · Embedding

---

## Graph tab

Controls how the Graph graph is rendered. Three collapsible sections.

### View section

**Color** select — controls node fill colour:
- `Domain` (default) — each `.onion` host gets a consistent colour from its hash
- `Cluster` — Louvain community cluster ID → colour palette
- `Depth` — crawl depth from seed → gradient (shallow = light, deep = dark)
- `Category` — heuristic category (marketplace, forum, paste, news, wiki, service, credentials)
- `Infra cluster` — infrastructure cluster (shared hosting fingerprint) → colour palette

**Edges** select — filters which edges are shown:
- `All` (default)
- `Cross-site only` — edges that cross `.onion` domain boundaries
- `Same-site only` — edges within the same domain

**Group by domain** checkbox — when checked, pages in the same domain are collapsed into
a single cluster node showing `domain (N)`. Double-clicking a cluster node expands it.
A "Collapse all (N expanded)" link appears when any clusters are expanded.

### Filters section

**Max hops** range slider — hides nodes deeper than the selected value. Range: 0 to the
maximum depth in the current graph. When set to the maximum, all nodes are shown.

**Show stubs** checkbox — when checked (default), stub nodes (not yet crawled) are shown as hollow dashed nodes. Uncheck to hide them entirely and focus on crawled data only.

**Hide orphans** checkbox — removes nodes with no visible edges.

**Show all edges** checkbox — when unchecked (default), deduplicates edges per domain
(shows at most one edge from each source node to each destination domain). When checked,
all individual edges are shown.

**Mutual clusters only** checkbox — shows only nodes belonging to a strongly connected
component containing at least 2 nodes (nodes that have a cycle back to a seed).

### Overlays section

**Flagged nodes** checkbox — adds colour-coded borders to flagged nodes:
- Amber border: `investigating`
- Red border: `pending`

**Isolate** checkbox — when any state overlay is active, hides all nodes *not* matching
the active overlays. Disabled unless at least one state overlay is on. A legend appears
showing the border colours when an overlay is active.

**Highlight bridges** checkbox — marks bridge/bottleneck nodes. When on, two sub-controls
appear:
- `Min betweenness` range slider (0–1, step 0.005) — minimum betweenness centrality for a
  node to get the bridge highlight.
- `Max in-degree` range slider (1–20) — maximum in-degree for the bridge highlight (filters
  out highly-linked hubs that aren't structural bottlenecks).

Bridge highlight uses a red border at the betweenness threshold and amber at the combined
threshold.

---

## Engines tab

Manages the dark-web search engine registry. Replaces the gear panel previously in the
Search tab.

**Engine list** — one row per engine showing label, URL (truncated, monospace), and an
enabled toggle. Enabled state is the default for the Search tab source selector — the
analyst can override per-search session without changing this default.

Each row has **Edit** and **Delete** action buttons.

- **Edit** — inline form with Label and URL inputs (Enter or Save to commit, Cancel to
  dismiss).
- **Delete** — confirmation dialog before removing.

**+ Add engine** button at the top — opens the add form. Both Label and URL are required.

Changes sync immediately to the Search tab source selector on next open.

---

## Watchlist tab

Manages the list of terms that drive two behaviours:

1. **Auto-flag** — when a crawled page contains a watchlist term, its node is automatically flagged for investigation.
2. **Focused mode signal** — when the Crawl sub-tab is set to Focused mode, the crawler scores pages by how many watchlist terms they match and prioritises the most relevant ones.

**Term list** — one row per term showing the term text. Each row has an **Edit** inline
input and a **Delete** button.

- **Edit** — clicking opens an inline input pre-filled with the term. Enter or Save to
  commit; Cancel to dismiss.
- **Delete** — removes immediately (no confirm — terms can be re-added easily).

**+ Add term** button at the top — opens a single text input. Term is required.

Empty state: "No terms configured. Add terms to auto-flag matching pages and enable Focused crawl mode."

---

## Browser tab

Controls how the Open button launches URLs. Settings here are persisted in the `settings`
table under the `browser.*` namespace.

**Browser path** — text input showing the path to the browser executable. The backend
attempts to auto-detect Tor Browser at common install locations on startup and pre-fills
this field if found. The user can override with any path.

Common auto-detect locations tried (in order):
- Linux: `~/tor-browser/Browser/start-tor-browser`, `/opt/tor-browser/Browser/start-tor-browser`
- Mac: `/Applications/Tor Browser.app/Contents/MacOS/firefox`
- Windows: `%USERPROFILE%\Desktop\Tor Browser\Browser\firefox.exe`, `C:\Program Files\Tor Browser\Browser\firefox.exe`

**Test** button — attempts to launch the configured binary with no URL to verify it works.
Shows a toast: "Browser launched successfully" or "Failed — check the path."

**Launch mode** select — two options:
- `Fresh instance` (default) — always opens a new isolated window with a new Tor circuit.
  The URL is never passed as a command line argument; it is copied to clipboard instead.
- `Reuse existing` — opens the URL in an already-running browser session. Less private —
  circuit may be shared with other open tabs. Useful for analysts who manage their own
  sessions manually.

**Tor SOCKS5 proxy** — text input showing the address used for all remote requests. Default `socks5h://127.0.0.1:9050`. Change to `socks5h://127.0.0.1:9150` if using Tor Browser's built-in Tor. Persisted as `tor.proxy` in `settings`. Changes take effect on next crawl or search — does not restart any active connections.

**ℹ How "Open in Tor Browser" works** — a persistent info box shown at the bottom of this
tab. Text:

> *"Open in Tor Browser" copies the URL to your clipboard and launches a fresh, isolated
> Tor Browser window. Paste the URL into the new window. A new circuit is used each time —
> your session is never reused or linked to other open tabs.*
>
> *If "Open in Tor Browser" appears greyed out in the context menu, the browser path above
> is not configured or the last test failed. Set the correct path and run Test to enable it.*

---

## Embedding tab

Controls the background embedding service that generates vector embeddings for semantic
search. These settings are persisted in the `settings` table under the `embedding.*`
namespace.

The embed service starts automatically when the backend starts and restarts itself on
crash. Use the controls here to disable it on low-powered machines or change its model.

**Auto-start** toggle — when on (default), the embed service starts with the backend.
When off, the service stays stopped until manually started here.

**Status row** — same dot/label as the Intel sub-tab: green = running, amber = paused,
grey = stopped.

**Start** button — starts the embed service manually. Disabled when already running.

**Stop** button — stops the embed service cleanly. Disabled when already stopped. Shows
a confirmation: "Stop the embedding service? Semantic search will be unavailable until
it is restarted."

**Model** select — dropdown of available Ollama embedding models (fetched from Ollama on
modal open). Changing the model stops the service, re-initialises with the new model, and
resumes. Shows a warning: "Changing the model will invalidate all existing embeddings and
require a full re-index."

**Progress** — `N / M pages embedded (X%)` — same read-only progress line as the Intel
sub-tab, for reference.
