# Pane Responsibility Reset

## Status

Implementation-ready feature spec. First post-F6 cleanup package. Frontend
only — no schema work. Establishes the four-pane mental model and action
taxonomy that every later cleanup depends on.

Supersedes: `additions/pane-action-cleanup.md` (folded in).

## Goal

Give each shell pane one stable, predictable job. Stop equivalent actions from
appearing in many unrelated places. Make every command's location derivable
from a clear rule.

## Pane Responsibilities

Use the shell panes as stable mental zones:

- **Left pane** — compose and start work.
- **Center graph** — investigate relationships.
- **Right pane** — inspect and act on the current selection.
- **Bottom pane** — monitor and manage queues, activity, lists, and datasets.

More concretely:

- Left pane owns crawl / search inputs, seed / bookmark selection, crawl
  options, intel composition, and seed / intake actions. Organised as a
  three-tab sub-strip (see "Left-Pane Sub-Tabs" below).
- Center graph owns visual selection, layout, filters, viewport controls,
  graph navigation, and graph-only tools.
- Right pane owns page / domain / analysis / cluster detail plus actions
  for the current selection.
- Bottom pane owns queues, live crawl state, analysis activity, logs,
  domains, flags, collections, hidden items, recipe lists (Scheduled
  Crawls, Monitors), and operational alerts.

## Left-Pane Sub-Tabs

The left pane uses a `PaneTabs` strip (the same component used by the right
and bottom panes — see `shared-ui-primitives.md`). Three sub-tabs, one
clear purpose each:

1. **Crawl** — `CrawlControls.svelte` (seed input + crawl options) plus
   `BulkImport.svelte`. Default tab on app open (current entry point).
   This is the "start a crawl" composer.
2. **Intel** — the analysis composer specced in
   `../2026-06-05-analysis-intel-pane/source-spec.md` (item 7): target selector, prompt
   template picker, model / worker controls, auto-analysis rules. This is
   the "start an analysis" composer.
3. **Find** — the F5 keyword + semantic search composer specced in
   `docs/specs/explore-left-pane-find.md` (item 9) **and** the label
   browser from the label-system work (item 11, now archived at
   [`../2026-06-10-label-system/`](../2026-06-10-label-system/)). Results land in the
   bottom pane (their own tab) — the left pane only holds the query
   composer and label browser. This is the "find something already in the
   data" surface.

Persisted last-selected tab so reopening the app or navigating back keeps
the analyst's context.

Why three: Crawl and Intel are both *compose work*, but they target
different workers (crawl runner vs analysis worker) with different forms,
so collapsing them into one Compose tab forces a sub-toggle and a tall
scroll. Search is *find work* and is mechanically different (query input
returning a result list). Three sub-tabs map 1:1 to the three actions an
analyst takes from the left pane.

## Action Taxonomy

Every command sorts into one of four categories. The category determines where
the command lives:

| Category | Examples | Home |
|---|---|---|
| **Navigation / view** | tabs, filters, layout, fit, reset | Local to the surface they apply to |
| **Selection action** | crawl, analyze, flag, add to collection, mark reviewed | Right pane (current selection) + graph context menu |
| **Row action** | delete, pause, retry, hide, remove | Bottom-pane rows + context/overflow menus |
| **System action** | kill switch, settings, project switch | App header |

If a command's category is unclear, it probably belongs in an overflow menu or
needs clearer wording.

## Queue Placement

Move queue-management surfaces out of the left pane and into the bottom pane.
The left pane composes work; the bottom pane manages work that already exists.

- `CrawlControls.svelte` stays in the left pane as the crawl composer.
- `CrawlQueuePanel.svelte` **stays in the left sidebar as a named
  carve-out** until the schema reset (item 6) lands. The Activity tab
  delivered by `unified-activity-view.md` then absorbs the queue in one
  user-visible step, eliminating both the left-sidebar location and the
  panel itself. Rationale: a temporary bottom-pane "Queue" tab would
  teach analysts a tab location that gets deleted weeks later and
  yanks affordances away once Activity ships. Carrying the carve-out
  is less disruptive than churning twice.
- `ScheduledCrawls.svelte` moves to the bottom pane as the Scheduled Crawls
  recipe tab.
- A new **Monitors** tab joins the bottom pane alongside Scheduled Crawls,
  mirroring the same recipe-list pattern (row actions: edit / pause /
  resume / delete). The existing `AddMonitorModal.svelte` stays as the
  create flow, reachable from both the tab toolbar (global) and the
  right-pane DomainTab (contextual to one domain). Today monitors are
  per-domain only — this tab is the global list.
- `BatchConfirmStrip.svelte` moves into the bottom-pane queue surface.
- Global analysis queue and monitor probe activity also belong in the
  bottom pane (the firings show up in Activity, delivered by
  `unified-activity-view.md`).
- Right-pane and cluster `Send to Crawl` actions stage work and then focus
  the bottom queue tab.

## Bottom-Pane Tab Grouping

The bottom pane fills with tabs as later items land (Activity, Monitors,
Labels, etc.). A flat strip of 10+ tabs overflows the visible width and
buries new tabs past the fold. Group the tabs under three top-level
labels, each opening a smaller sub-strip:

- **Work** — operations currently or scheduled to happen.
  - Activity (delivered by `unified-activity-view.md` inside the schema
    reset)
  - Live Crawl (kept as the streaming-log view even after Activity
    absorbs crawl-queue rows)
  - Scheduled Crawls (recipes; moved from the left pane by this package)
  - Monitors (recipes; new tab added by this package)
- **Catalog** — the data already in the project.
  - Domains
  - Flags
  - Fingerprints
  - Labels (shipped by item 11; see
    [`../2026-06-10-label-system/outcome.md`](../2026-06-10-label-system/outcome.md))
  - Hidden — kept here **temporarily**; the tab is `graph_filters` CRUD,
    not a node list, and its natural home is Settings modal → Graph (see
    `additions/settings-modal.md` Wave 1). Targeted for removal in item 8
    once the settings Graph tab adopts the hide-list CRUD; until then
    Hidden sits in Catalog.
- **Sets** — analyst-curated working sets.
  - Collection
  - Bookmarks

Search Results (when F5 ships) is **ephemeral** — the tab only exists
when the F5 composer has produced a result set; it dismisses when the
analyst clears the query. Does not occupy a permanent tab slot.

Inventory (the deferred proposal) — if revived, lands in **Catalog**.

Total tabs per group stays at 2–4. New tabs slot into the right group
instead of pushing things off-screen. The group label uses the same
`PaneTabs` styling for visual consistency app-wide.

## Right-Pane Action Bar

Add a consistent action bar at the top of the right pane that surfaces
selection actions for the current node, domain, or cluster:

- `Send to Crawl`
- `Add to collection`
- `Flag`
- `Queue Analysis`
- `More…` (overflow for less frequent actions)

The action bar varies its action set by selection type (page vs domain vs
cluster), but the structure and styling are identical.

## Button Cleanup

Reduce visible button noise on each surface:

- Graph toolbar limited to graph and canvas controls (layout, filters, fit,
  reset, export, draw edge, expansion).
- Right pane uses the action bar plus tab-local controls only.
- Row-specific secondary actions move into right-click context menus or
  compact overflow menus.
- Keep only frequent row actions visible (pause/resume, remove, retry,
  visibility toggle).

## Workflow-Staging Behavior

When a command in one pane stages work that the bottom pane manages, the bottom
pane responds. Default behavior: focus the corresponding bottom-pane tab and
flash the newly added row. No modal toast on the trigger surface.

This applies to right-pane `Send to Crawl`, cluster `Send to Crawl`, queue
analysis from the graph context menu, and bulk import staging.

## Affected Surfaces

Verified surface area (will be moved/recomposed, not all deleted):

- `frontend/src/components/CrawlSidebar.svelte`
- `frontend/src/components/crawl/CrawlControls.svelte`
- `frontend/src/components/crawl/CrawlQueuePanel.svelte` (~580 LOC) —
  **untouched by this package**; absorbed by Activity in item 6
- `frontend/src/components/crawl/ScheduledCrawls.svelte` (~470 LOC)
- `frontend/src/components/crawl/BatchConfirmStrip.svelte` (~334 LOC)
- `frontend/src/views/BottomPane.svelte` (new tabs)
- `frontend/src/views/bottom/MonitorsTab.svelte` — new; mirrors
  `ScheduledCrawls.svelte` structure
- `frontend/src/views/RightPanel.svelte` (action bar host)

## Code Size Expectation

Net LOC change: roughly flat. The verified 1,384 LOC across queue components
mostly moves rather than disappears. The win is structural — clear pane
ownership and a derivable rule for command placement — not deletion.

## User-Visible Changes

- Queue management, scheduled crawls, and batch confirmations disappear from
  the left sidebar and appear in the bottom pane.
- Right pane gains a consistent action bar across Page / Domain / Analysis /
  Cluster tabs.
- Row buttons reduce in number; less-frequent actions move into context menus.
- Triggering a `Send to Crawl` from the graph or right pane focuses the bottom
  queue tab automatically.

## Relationship to Other Work

- Required precondition for `unified-activity-view.md` (bottom pane has to own
  activity first).
- Required precondition for `shared-ui-primitives.md` (pane structure has to
  stabilize before primitives are extracted from it).
- `$lib/contextMenu/actions.ts` is the base for shared action helpers; the
  action bar and context menus should call the same helpers (specced in
  `shared-ui-primitives.md`).

## Deferred Decisions

- Whether the bottom pane gets a dedicated `Queue` tab merging crawl and
  scheduled crawls, or whether they remain separate tabs sharing the same
  styling.
- Whether `ScheduledCrawls` sits inside the queue tab or stays its own
  operational view.
- Exact set of frequent row actions that remain visible vs collapse into
  context menus.
- Whether the right-pane action bar set varies per tab or stays fixed.
- Whether workflow-staging also surfaces a brief toast in addition to focusing
  the bottom tab.
