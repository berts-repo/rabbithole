# Bulk Import Crawl Queue Plan

## What we are trying to accomplish

Turn Bulk Import from a one-row-at-a-time seed picker into the shared intake surface for
URLs that should be crawled later or next.

Today Bulk Import parses a pasted list, looks up each URL, and lets the analyst send one
row into the main Crawl seed input. It does not queue the list, and the crawler currently
runs only one crawl at a time. The new design should preserve the single active crawler
constraint while allowing many URLs to be collected into a crawl queue.

The intended result:

- The Crawl sub-tab is the single intake surface — `CrawlControls` at the top, the
  durable queue below, Bulk Import below that.
- Every "I want this crawled" action across the app uses one verb (`Send to Crawl`)
  that routes through the Crawl sub-tab. Nothing enters the queue silently.
- Analysts can paste many URLs and confirm the batch once in the batch-confirm strip
  before rows enter the queue.
- Other app surfaces (graph, search, right pane, bottom pane, collections, bookmarks)
  send single URLs or multi-row selections through the same Crawl-sub-tab confirm path.
- The backend runs queued crawl jobs sequentially unless and until we explicitly design
  safe crawl concurrency.
- Each queued item can carry crawl options, including target collection and depth cap.

## Current behavior

- `CrawlControls` owns the default seed URL input, bookmarks, mode, collection target,
  start/stop buttons, and running status.
- `BulkImport` owns the paste area, row parsing, lookup badges, `Crawl` row action, and
  stub creation.
- `CrawlSidebar` binds `seedUrl` between them. Clicking `Crawl` in a bulk row only fills
  the top seed input and focuses it.
- Starting a crawl still happens through the normal `Start` button.
- Only one crawl can run at a time. Attempts to start while one is running are rejected
  or skipped.

## New capability

Add a durable crawl queue, separate from active crawl execution.

A queued crawl item should include:

- URL
- Status: queued, running, completed, failed, cancelled, skipped
- Mode
- Stay-on-domain setting if supported by the start API
- Collection target: none, existing collection, or a resolved new collection
- Source surface: manual input, bulk import, collection, bottom pane, search result,
  graph context menu, or other future source
- **Priority (int, default 0)** — higher runs sooner. Mirrors `analyses.priority`
  (see `stack.md:86`). v1 ships FIFO only (priority + `created_at` as tiebreaker, no UI
  to mutate priority); the column exists so schedule-fired rows or future drag-and-drop
  reorder can use it without a migration.
- **Lookup state** — `unknown` / `crawled` / `stub` / `dead`, cached on the row so the
  queue UI can show the same badges Bulk Import shows today. Refreshed by a lightweight
  pre-check pass when a row is enqueued; if the URL is already `crawled` the row resolves
  immediately as `skipped` without burning a crawl slot.
- Created/updated timestamps
- Last error, when applicable

The runtime should keep the current one-active-crawl rule for actual crawling. When the
active crawl finishes, the queue runner starts the next queued item.

### Runtime controls

- **Pause queue toggle** — single project-level flag (persisted in `settings`). When
  paused, the runner stops auto-advancing after the current crawl finishes; new rows pile
  up as `queued`. Useful when loading a large batch you want to review before running.
- **Restart recovery** — any `crawl_queue` row left `running` from a prior process is
  swept back to `queued` (or marked `failed` with `error='process restarted'` if it had
  already produced partial output, matching B5's existing sweep for the `crawls` table).
  Persistent storage means the queue survives reloads and process restarts.

## Source surfaces

The queue should accept URLs from multiple places:

- Crawl tab manual input
- Bulk Import parsed rows
- Seed bookmarks
- Collection views
- Bottom pane lists
- Search results
- Graph context menu actions

Collection and bottom-pane sends are first-class requirements, not later polish. They
should call the same queue API as Bulk Import so there is one path for dedupe, status,
toasts, and error handling.

### Verb convention across surfaces

One verb across the app: **Send to Crawl**. Nothing enters the queue silently — the
Crawl sub-tab is always where rows are confirmed.

- **Single-URL surfaces** — graph right-click, search result row, right-panel entities,
  bottom-pane rows, seed bookmarks. `Send to Crawl` switches to the Crawl sub-tab and
  loads the URL into `CrawlControls`' manual single-URL input. The analyst picks
  mode / collection / stay-on-domain / depth on the controls in front of them and
  presses Start (which queues + dispatches per the resolved decisions below).

- **Multi-row surfaces** — Bulk Import paste, collection view "Crawl all uncrawled",
  bottom-pane multi-select, graph multi-select. `Send to Crawl` switches to the Crawl
  sub-tab and surfaces the **batch-confirm strip** — a panel sitting between
  `CrawlControls` and the queue list. The strip shows `N URLs` with mode / collection /
  stay-on-domain / depth pickers and a `Queue N` button; those values apply to every
  row in the batch. Rows enter the queue only after the analyst confirms. A `Cancel`
  affordance discards the staged rows without enqueueing.

  Default values in the strip mirror whatever the analyst currently has chosen in
  `CrawlControls`, so the common "use the same settings I already had picked" path is
  one click.

Why one verb: every "do something with this node" action in the app already routes
through a pane (`CLAUDE.md` selection model). Silent push to the queue was the outlier
— this convention removes it. Because the analyst is always looking at the Crawl
sub-tab at the moment rows enter the queue, the mode/collection dropdowns visible to
them are by construction the ones whose values are applied. No `crawl.default_mode`
setting is needed.

This convention supersedes today's narrower behaviour in `explore-graph.md:125`,
`search-tab.md:82`, `right-pane.md`, and `explore-bottom-pane.md`. Those docs are
updated alongside this work.

## UX direction

The Crawl sub-tab is the intake surface. Layout, top to bottom (surgery-only — no
`SeedIntake` extraction, no drawer-wrap of Bulk Import; Phase A's `CrawlQueuePanel`
already sits between `CrawlControls` and `BulkImport`):

1. **`CrawlControls`** — manual single-URL input, bookmarks dropdown, mode / collection
   / stay-on-domain / depth, Start / Stop. Unchanged from today.

2. **Batch-confirm strip** — visible only while a multi-row batch is staged. Shows
   "Batch from {source} — N URLs", a compact mode / collection / stay-on-domain / depth
   row, `Queue N` and `Cancel` buttons. Pre-filled from the current `CrawlControls`
   values. Hidden when no batch is staged.

3. **`CrawlQueuePanel`** — the queue list. Each row shows: URL, lookup badge
   (`unknown` / `crawled` / `stub`), status, mode chip, collection chip, and row
   actions.

   Row actions: **Start next** (bumps this row's `priority`), **Cancel / Remove**,
   **Retry** (failed only), and inline edit for mode / collection / stay-on-domain /
   `max_depth` while the row is `queued`.

   Header: pause/resume toggle, **Clear completed** button (status-filtered so
   `failed` rows aren't wiped), "N queued · M done · K failed" count line.

   Drag-and-drop reorder is **deferred** — `priority` ships in v1 so the future PATCH
   reorder endpoint doesn't need a migration.

4. **`BulkImport`** — paste area + per-row parsed list with lookup badges. The
   per-row `▶ Crawl` button is renamed `▶ Send to Crawl` and keeps its current
   behaviour (single-URL load into `CrawlControls`' manual input). A new
   `Queue all N URLs` button at the bottom of the parsed-rows list stages all rows
   into the batch-confirm strip above (where the analyst confirms mode / collection /
   depth once for the whole batch). `+ Stub`, `+ Collection`, and `Clear` keep their
   current behaviour.

5. **`ScheduledCrawls`** — unchanged.

Single-URL flow stays fast: type URL into `CrawlControls`, choose options, press
Start. The batch-confirm strip only appears when one is actually needed.

## Implementation approach

**Decision (2026-05-19):** backend queue with sequential runner. Persistent rows in
`crawl_queue`, a small runner that picks the next item when no crawl is active. Matches
the current one-active-crawl architecture, survives page reloads, and gives every
surface one API for queueing. See the Schema sketch and Resolved decisions sections
below for the details.

### Alternatives considered (rejected)

- **Frontend-only queue.** Keep a queue in frontend state and start crawls one at a time
  from the browser. Rejected: would fail when the browser tab closes, would not coordinate
  between windows, and would duplicate backend crawl-state logic in the UI.
- **Backend queue plus crawler concurrency.** Add a queue and allow multiple crawls to
  run at once. Deferred — not rejected on merit. It changes crawler runtime assumptions,
  Tor/network load, graph write behavior, status reporting, and kill-switch semantics.
  Sequential queueing delivers most of the user value first; revisit when there's a
  concrete need.

## Schema sketch

**Decision (2026-05-19):** separate `crawl_queue` table, distinct from `crawls`. The
queue holds intent (queued / in-flight); `crawls` keeps history. When the runner picks up
a queued row it sets `started_at` and `status='running'`, writes the corresponding
`crawls` history row, and on completion updates both. Smallest blast radius — B5 routes
stay as-is, no migration of the `crawls.status` enum.

```
id                       INTEGER PRIMARY KEY AUTOINCREMENT
url                      TEXT NOT NULL
status                   TEXT NOT NULL CHECK (status IN
                         ('queued','running','completed','failed','cancelled','skipped'))
mode                     TEXT NOT NULL
stay_on_domain           INTEGER NOT NULL DEFAULT 0
collection_id            INTEGER REFERENCES collections(id) ON DELETE SET NULL
collection_name_pending  TEXT     -- set when analyst chose "+ New collection…" at enqueue;
                                  -- resolved to collection_id on first run
source                   TEXT NOT NULL CHECK (source IN
                         ('manual','bulk','bookmark','collection','bottom_pane',
                          'search','graph_menu','right_pane','schedule'))
priority                 INTEGER NOT NULL DEFAULT 0  -- higher runs sooner
lookup_state             TEXT     -- 'unknown' | 'crawled' | 'stub' | 'dead'
attempts                 INTEGER NOT NULL DEFAULT 0
error                    TEXT
created_at               TEXT NOT NULL
updated_at               TEXT NOT NULL
started_at               TEXT
finished_at              TEXT
```

Indices: `(status, priority DESC, created_at)` for the runner pick-next query;
`(url)` for dedupe.

## Recommended plan

1. Add backend crawl queue storage and APIs:
   - `POST /api/crawl/queue` — add one or many URLs (accepts array)
   - `GET /api/crawl/queue` — list with filters (status, source)
   - `PATCH /api/crawl/queue/:id` — edit mode/collection; also accepts a priority bump
     for the "start next" row action
   - `DELETE /api/crawl/queue/:id` — cancel queued or remove completed/failed row
   - `POST /api/crawl/queue/:id/retry` — reset failed row to queued
   - `PUT /api/settings/crawl.queue_paused` — pause/resume the runner
   - *(Deferred to follow-up: `PATCH /api/crawl/queue/reorder` — bulk priority rewrite
     for drag-and-drop)*
2. Add a queue runner that preserves one active crawl at a time. On boot, sweep
   stale `running` rows (per Restart recovery above).
3. Update the Crawl tab so the top intake area can add one or many URLs to the queue.
4. Surgical changes to `BulkImport`: keep the component in place, rename the per-row
   `▶ Crawl` action to `▶ Send to Crawl` (behaviour unchanged — load URL into
   `CrawlControls`), and add a bottom-of-list `Queue all N URLs` button that stages
   the parsed rows into the batch-confirm strip.
5. Add a single `Send to Crawl` action to every intake surface — single-URL surfaces
   load the URL into `CrawlControls`; multi-row surfaces stage their selection in
   the batch-confirm strip. Surfaces to cover: graph right-click (single + multi-
   select), search results, right-panel entity menus, right-panel page-list rows,
   right-panel cluster workspace, bottom-pane rows (single + multi-select), bottom-
   pane bookmarks tab, collection-view "Crawl all uncrawled", seed bookmarks.
6. Remove the `POST /api/crawl/start` Phase A alias once every frontend caller has
   migrated to `POST /api/crawl/queue` (audit-trail item 3 in `plan.md`).
7. Repoint `services/schedule_daemon.py` at the queue — on schedule fire, insert a
   `crawl_queue` row with `source='schedule'` instead of invoking the runtime directly.
   Schedule daemon's only remaining responsibility is "compute next fire time, push to
   queue, sleep." See the resolved decision above.
8. Add tests for queue creation, dedupe (partial unique index), sequential execution,
   cancellation, pause/resume, snapshot at enqueue, lazy-collection find-or-create
   (including collision-with-existing and two-batches-same-pending-name cases), restart
   recovery sweep, and scheduled crawl → queue insertion path.

## Cross-doc alignment (must update when this lands)

- `crawl-left-pane.md` — rewrite the Bulk Import section: per-row `▶ Send to Crawl`
  loads URL into `CrawlControls`; bottom-of-list `Queue all N URLs` stages the
  batch. Add a new section describing the batch-confirm strip and the
  `CrawlQueuePanel` (queue list, header controls, row actions, inline edit).
- `explore-graph.md` — single-URL right-click `Send to Crawl` (any node, not
  stub-only) loads URL into `CrawlControls`. Multi-select `Send to Crawl` stages
  the selection in the batch-confirm strip; the current stub-only "Crawl selected"
  entry is renamed/broadened. Drop the existing "Queue Crawl" entry.
- `search-tab.md` — uncrawled result row `Send to Crawl` loads URL into
  `CrawlControls`. Drop the "Queue Crawl" entry and its toast text.
- `right-pane.md` — entity context menu `Send to Crawl` keeps its current
  fill-the-input behaviour. Domain-tab page-list row context menu `Send to Crawl`
  loads URL into `CrawlControls`. Cluster workspace `Crawl selected` button is
  renamed `Send to Crawl` and stages the selection in the batch-confirm strip
  (instead of silently queuing).
- `explore-bottom-pane.md` — `Send to Crawl` keeps its single-URL fill-the-input
  meaning. For multi-select rows it stages the selection in the batch-confirm strip.
- `stack.md` — add the `crawl_queue` table to the schema reference and the queue
  routes to the API reference. Note that `services/schedule_daemon.py` is retired;
  schedule production lives in `services/crawl_queue_runner.py` (see
  `plan.md` audit-trail item 10).
- `docs/work/active/2026-05-25-durable-crawl-queue/` — the active package
  already exists; its `plan.md` and `checklist.md` are updated alongside this
  spec revision.

## Resolved decisions (2026-05-19 walkthrough)

- **Table model:** separate `crawl_queue` table (see Schema sketch).
- **Start button:** always queues. If the runner is idle and the queue is otherwise empty,
  it picks the row up immediately — so the analyst-perceived behaviour for the common
  solo case is still "press Start, it crawls." One mental model: every crawl goes through
  the queue. Pause-the-queue then becomes a real safety net (paused + start = queued,
  does not auto-run).
- **Duplicates:** block enqueue only while a row with the same URL is `queued` or
  `running`. Already-crawled URLs CAN be re-queued (legitimate re-crawl flow); the row's
  lookup badge shows `crawled` so the analyst sees the state before confirming.
  Duplicates within a single paste are deduped silently. Implementation: a partial unique
  index on `crawl_queue(url) WHERE status IN ('queued','running')`.
- **Mode/collection snapshot:** every queue row freezes `mode`, `collection_id`,
  `collection_name_pending`, and `stay_on_domain` at enqueue time. Changing the Crawl tab
  dropdowns after queueing has zero effect on already-queued rows. Per-row inline edit
  lets the analyst override these fields on a `queued` row before it runs. Matches the
  industry-standard "what you clicked is what you'll get" expectation (print queues, CI
  queues, download managers).
- **Lazy collection create.** When the analyst picks "+ New collection…" at enqueue, the
  row stores `collection_name_pending` (TEXT) — no `collections` row is created yet. When
  the runner picks up the first row with that pending name, it does find-or-create:
  `SELECT id FROM collections WHERE name=? LIMIT 1`; if found, use it; if not, insert.
  Then it rebinds all still-queued rows sharing that pending name to the resolved
  `collection_id` in the same transaction. Avoids the empty-collection cleanup tax when
  batches are cancelled; self-heals across collection deletes; two parallel batches with
  the same pending name merge naturally. Collision rule: if a collection with the same
  name appears via another path during the pending window, silently use it — no prompts,
  no auto-suffix. Principle of least surprise: matching names = same destination.
- **Drag-and-drop reorder deferred.** v1 ships FIFO only (priority + `created_at`
  tiebreaker). The `priority` column ships so the future PATCH-reorder endpoint doesn't
  need a migration. "Start next" row action bumps a single row's priority for the common
  "I want this one first" case.
- **Scheduled crawls feed the queue.** `services/schedule_daemon.py` no longer calls
  `startCrawl` directly. When a schedule fires, it inserts a row into `crawl_queue` with
  `source='schedule'` and the schedule's mode/collection snapshotted. The queue runner
  then picks it up under the same one-active-crawl rule as everything else. Result: one
  runner, one crash-recovery sweep, one kill-switch hook, one set of SSE events. The
  schedule daemon shrinks to "compute next fire time, push to queue, sleep" — all the
  pickup/sequencing logic lives in the queue runner.
- **History retention: keep forever, manual clear.** Completed / failed / cancelled /
  skipped rows stay in `crawl_queue` indefinitely; the analyst clears them via the
  queue header "Clear completed" button (with a status filter so failed rows aren't
  wiped accidentally). Storage cost is negligible (SQLite handles 100k small rows
  without effort); a partial index on `status='queued'` keeps the runner pickup query
  fast regardless of terminal-status tail size. Auto-pruning would silently truncate
  the export/audit trail (see Export below).

## Export (follow-up, no migration needed)

The v1 schema is export-ready by accident — every column you'd want in a CSV is already
there. A one-route follow-up adds:

- `GET /api/crawl/queue/export?format=csv|json[&status=…&source=…&since=…]`

Columns: URL, status, mode, stay_on_domain, collection (resolved name + id, or pending
name), source, priority, lookup_state, attempts, error, created_at, updated_at,
started_at, finished_at. Same csv-injection neutralisation as `routes/graph.py` —
prefix any cell starting with `= + - @ \t \r` with `'`. Keep-forever retention means
this export is the canonical "every crawl I ever initiated in this project" record,
suitable for investigation reports.
