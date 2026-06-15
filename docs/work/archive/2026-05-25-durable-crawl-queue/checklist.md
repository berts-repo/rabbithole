# Checklist

The plan is in `plan.md`. Phase A is shipped (all checklist items done).
Phase B is ready to start — source spec revised to Option B on
2026-05-26; cross-doc specs updated alongside. See "Phase B status" in
`plan.md` for recommended sequencing.

## Phase A — backend queue + minimum frontend

### Schema + DB module

- [x] Add `crawl_queue` table DDL to `_SCHEMA_STATEMENTS` in `db/core.py`
  (includes the `max_depth INTEGER` column; NULL = unlimited;
  `lookup_state` CHECK excludes `'dead'`).
- [x] Update `collections` table DDL in `_SCHEMA_STATEMENTS` so `name` is
  declared `TEXT NOT NULL UNIQUE COLLATE NOCASE` (fresh DBs get the right
  shape without going through the rebuild path).
- [x] Add the three `crawl_queue` indexes (partial pick, partial unique
  active-url, status) to `_INDEX_STATEMENTS`.
- [x] Add `_migrate_to_v2()` to `CrawlDB`; bump `SCHEMA_VERSION` to `2`.
  Inside the same transaction:
  - [x] Pre-flight scan for case-duplicate `collections.name` rows; abort
    with a clear error if any are found (see plan.md "Collections table
    rebuild").
  - [x] Rebuild `collections` table with `name TEXT NOT NULL UNIQUE COLLATE
    NOCASE`; copy data; drop old; rename new; recreate indexes; verify
    `PRAGMA foreign_key_check`.
  - [x] Create `crawl_queue` table + indexes (no-op if already present from
    `_init_schema` on a fresh DB).
- [x] Add `_sweep_stale_queue_rows()` to `CrawlDB.__init__`.
- [x] Add `crawl_queue` to `EXPECTED_TABLES`.
- [x] Add `"crawl.queue_paused": "false"` to `DEFAULT_SETTINGS`.
- [x] Create `backend/backend/db/crawl_queue.py` with all helpers listed in
  `plan.md` ("DB module ownership"). The `resolve_pending_collection`
  helper does case-insensitive find-or-create — DB-level UNIQUE on
  `name COLLATE NOCASE` enforces it regardless.
- [x] Update `docs/reference/data-model.md` — add the `crawl_queue` table,
  the version bump, the new restart-recovery sweep, and the
  `collections.name` COLLATE NOCASE change.

### Queue runner

- [x] Create `backend/backend/services/crawl_queue_runner.py`.
- [x] Wire it into `main.py`'s `create_app()` and lifespan (stop before
  `crawl_runners.stop()`).
- [x] Subscribe to runner-completion events from `CrawlRunnerRegistry`.
- [x] Implement the 5–10s safety tick.
- [x] Implement the atomic claim + dispatch path that reuses
  `CrawlRunner` / `CrawlRunnerRegistry.start()`.
- [x] Honor the pause flag at "try advance" time, not enqueue time.
- [x] Honor the kill-switch gate at "try advance" time.
- [x] Implement `produce_scheduled_rows` on `CrawlQueueRunner` (replaces
  the standalone `ScheduleDaemon` per audit-trail item 10). Producer
  step is never gated by kill switch / pause; runs on every safety tick
  and once during `start()` to catch up overdue schedules.
- [x] Retire `services/schedule_daemon.py` and remove its `app.state`
  slot from `main.py`'s lifespan.
- [x] Keep the `crawl.status='scheduled_fired'` event payload, emitted
  on queue insert from the producer.
- [x] Migrate `tests/test_b5c_schedule_daemon.py` to
  `tests/test_b5c_schedule_producer.py` driving
  `CrawlQueueRunner.produce_scheduled_rows`.
- [x] Update `docs/reference/backend-structure.md` services table.

### REST + SSE

- [x] Create `backend/backend/routes/crawl_queue.py` (audit-trail item 6)
  implementing all six endpoints listed in `plan.md` ("REST + SSE surface").
- [x] On `DELETE /api/crawl/queue/:id` for a `running` row, call
  `CrawlRunnerRegistry.stop()` and let the runner's completion path mark
  the row `cancelled` (audit-trail item 7 — cancel-running coupling).
- [x] Add `crawl_queue.changed` channel to `EventBus`. (Plain string channel,
  routed via the existing pub/sub — no registration needed; SSE route on
  `GET /api/crawl/queue/events` filters by name.)
- [x] Confirm `PUT /api/settings/crawl.queue_paused` works under the existing
  settings validator. (Covered by `DEFAULT_SETTINGS` seed + the generic
  on/off coercion in `db/settings.py`.)
- [x] Rewrite `POST /api/crawl/start` to insert a `priority=1000` queue row
  and trigger the runner. Existing contract preserved (removed in Phase B
  per audit-trail item 3).

### Minimum frontend (Phase A)

- [x] New `frontend/src/lib/api/crawlQueue.ts` wrapping the queue endpoints.
- [x] New queue list panel on the Crawl tab (read-only is fine for Phase A —
  shows status / URL / source / created_at). `CrawlQueuePanel.svelte` sits
  between `CrawlControls` and `BulkImport` in `CrawlSidebar.svelte`.
- [x] Pause/resume toggle in the same panel, wired to the settings key.
- [x] Crawl-tab depth input: numeric field next to the mode selector, default
  `3`, with an explicit "Unlimited" affordance that shows a one-line
  "this crawl can run indefinitely" warning. Passes `max_depth` on the
  enqueue call.
- [x] SSE subscription for `crawl_queue.changed` updates the panel.

### Tests (Phase A)

- [x] All backend tests listed under "Test plan" in `plan.md`. Coverage in
  `tests/test_crawl_queue_db.py` (helpers, dedupe, atomic claim,
  lazy-collection rebind, max_depth default + explicit unlimited) and
  `tests/test_crawl_queue_routes.py` (HTTP surface, pause blocks dispatch,
  cancel paths, /api/crawl/start alias). Atomic claim under concurrent
  callers uses two CrawlDB handles racing on `BEGIN IMMEDIATE`.
- [x] Collections rebuild migration:
  - [x] Fresh DB starts with `collections.name COLLATE NOCASE` (no rebuild
    path taken).
  - [x] Existing v1 DB with no case-duplicates rebuilds successfully;
    `PRAGMA foreign_key_check` returns no rows; existing rows are intact;
    inserting `"Foo"` then `"foo"` raises UNIQUE constraint.
  - [x] Existing v1 DB with case-duplicates aborts the migration with the
    expected error message; no partial state is committed.
- [x] `resolve_pending_collection` returns the existing row regardless of
  case (e.g. pending `"Investigations"` matches existing `"investigations"`).
- [x] Re-run existing crawler / routes / schedule daemon tests; nothing
  regresses. (672/672 pass after the half-state cancel fix in
  `routes/crawl_queue.py`.)

## Phase B — cross-surface intake + Crawl-tab surgery

Single verb across the app: `Send to Crawl`. Single-URL surfaces load into
`CrawlControls`; multi-row surfaces stage into the batch-confirm strip.
Nothing enters the queue silently. Source spec was revised to Option B on
2026-05-26 (audit-trail item 8 in `plan.md`).

### Batch-confirm strip + Crawl-tab wiring

- [x] New batch-confirm strip component in the Crawl sub-tab, between
  `CrawlControls` and `CrawlQueuePanel`. Visible only when a multi-row
  batch is staged. Defaults mirror current `CrawlControls` values;
  `Queue N` enqueues via `lib/api/crawlQueue.ts` and clears the strip;
  `Cancel` (✕) discards.
- [x] Shared "stage batch" handler (Svelte store or context) reachable
  from every multi-row source. (`lib/stores/batchConfirm.svelte.ts` —
  `stage(...)`, `discard()`, `clear()`.)
- [x] Shared "load into `CrawlControls`" handler reachable from every
  single-URL source. (Same store — `loadIntoControls(url)`; `CrawlSidebar`
  registers the seed-input lift on mount.)
- [x] Restage policy: staging a new batch replaces any prior staged
  batch with a toast ("Replaced previous batch — N URLs").

### Intake surfaces — single-URL

> **Note (2026-05-26):** the Bookmarks sub-tab (BottomPane is a F7
> placeholder), Search results (SearchTab is a F8 placeholder), and
> the right-pane stub-node button + cluster workspace (RightPanel is a
> F6 placeholder) cannot be migrated until those surfaces are built.
> Items below stay unchecked as standing claims; flip when the
> underlying feature lands.

- [x] `CrawlControls.svelte:209` — Start button migrates from
  `startCrawl` to `POST /api/crawl/queue` (via `crawlQueue.ts`),
  `source='manual'`.
- [x] Bulk Import per-row `▶ Crawl` → `▶ Send to Crawl` (rename only;
  behaviour already loads `CrawlControls`).
- [ ] Bottom-pane Bookmarks `▶ Crawl` → `▶ Send to Crawl` row action
  (rename only). _Deferred — F7 not built._
- [x] Graph context menu single-node `Send to Crawl`
  (`lib/graph/interactions/contextMenu.ts`); drop the stub-only gate at
  line 104; update `contextMenu.test.ts:141,153`.
- [x] `GraphCanvas.svelte:1138,1196` — migrate the two `startCrawl`
  call sites to the shared load-into-`CrawlControls` handler.
- [ ] Search results uncrawled-row action bar `Queue Crawl` →
  `Send to Crawl`. _Deferred — F8 not built._
- [ ] Right-pane stub-node button: rename `Crawl now` → `Send to Crawl`
  (behaviour already loads `CrawlControls`). _Deferred — F6 not built._

### Intake surfaces — multi-row (stage into batch-confirm strip)

- [x] Bulk Import bottom-of-list `Queue all N URLs` button stages the
  parsed rows.
- [ ] Bottom-pane Collection sub-tab `Crawl all uncrawled` →
  `Send to Crawl (all uncrawled)`; replace the inline popover with
  batch-confirm staging. _Deferred — F7 not built._
- [x] Graph multi-select context menu `Crawl selected` →
  `Send to Crawl`; drop the stub-only gate; stage the whole selection.
- [ ] Right-pane cluster workspace `Crawl selected` → `Send to Crawl`;
  stage regardless of stub state. _Deferred — F6 not built._

### Queue panel enhancements

- [x] Per-row inline edit (mode / collection / stay-on-domain /
  `max_depth`) for `queued` rows only — backend already refuses on
  non-`queued` status via `update_queue_row`.
- [x] Header `Clear completed` button — status-filtered so `failed`
  rows aren't wiped accidentally.
- [x] Header count line: "N queued · M running · K done · F failed".

### Alias removal

- [x] Grep the frontend for `startCrawl(` after the migrations above;
  verify zero call sites remain.
- [x] Remove `POST /api/crawl/start` from `routes/crawl.py` and any
  helper code that only exists to serve the alias.
- [x] Update backend tests that targeted the alias to hit
  `POST /api/crawl/queue` instead (alias-only tests dropped; queue
  coverage already exercises the surface).

### Cross-doc spec updates

- [x] `docs/specs/crawl-left-pane.md` — Bulk Import surgery + new
  batch-confirm strip + new Crawl Queue sections + Max depth control
  (landed alongside the source-spec revision, 2026-05-26).
- [x] `docs/specs/explore-graph.md` — single + multi-select
  `Send to Crawl` (2026-05-26).
- [x] `docs/specs/search-tab.md` — uncrawled-row `Send to Crawl`
  (2026-05-26).
- [x] `docs/specs/right-pane.md` — stub-node button rename + cluster
  workspace `Send to Crawl` (2026-05-26).
- [x] `docs/specs/explore-bottom-pane.md` — Bookmarks row + Collection
  sub-tab updates (2026-05-26).
- [x] `docs/specs/stack.md` — `crawl_queue` schema row (2026-05-26).
- [x] Re-check all six during/after Phase B implementation in case
  wording gaps surface. (2026-05-26 — no wording corrections needed;
  Start next / Retry / lookup badge / mode+collection chips on rows
  and the dedupe-preview row are spec'd but not yet built — aspirational,
  not Phase B scope.)

### Frontend tests

- [ ] Batch-confirm strip: defaults pulled from `CrawlControls`;
  staging populates; `Queue N` enqueues; restage replaces with toast.
- [ ] Graph context menu: gate-removal at line 104; single + multi
  variants call the shared handlers.
- [ ] Bulk Import: per-row rename behaviour; bottom-of-list button
  stages a batch.
- [ ] `CrawlQueuePanel` inline edit only on `queued` rows; refuses on
  others. `Clear completed` only removes terminal rows other than
  `failed`. Count line reflects status.

## Close-out

- [ ] Write `outcome.md` summarizing what shipped, schema version on disk,
  any deviations from the plan.
- [ ] Move the package to `docs/work/archive/` per `LIBRARIAN.md`.
- [ ] Repoint `docs/work/ACTIVE.md` to the next package or `none`.
