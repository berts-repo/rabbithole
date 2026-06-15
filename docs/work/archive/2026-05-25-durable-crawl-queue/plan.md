# Durable Crawl Queue — Implementation Plan

Status: Phase A shipped (backend queue + minimum frontend, all checklist
items done). Phase B ready to start — source spec revised to Option B
(single-verb intake + batch-confirm strip) on 2026-05-26; see audit-trail
item 8 below.
Date: 2026-05-25 (Phase B sections re-cut 2026-05-26)
Source spec: `source-spec.md` (revised 2026-05-26 to the Option B verb
model)

The spec recorded owner-resolved decisions on the table model, FIFO runner,
duplicate handling, queue pause, lazy collection create, schedule-daemon
producer rewrite, and history retention. Those are treated as fixed. This plan
covers everything the spec leaves to implementation: where the code lives, how
the migration runs, how each intake surface plugs into the queue, and what
still needs owner input.

## Decisions taken during planning review (2026-05-25)

Captured here so they don't get lost in the punch-list as it shrinks. Each is
folded into the relevant section below; this list is the audit trail.

- **1 — Runner wake-up: hybrid.** Event-driven pokes + 5–10s safety tick.
  The code shape in "Architecture decisions → How the runner advances"
  reflects this. Rationale: pokes give the UI an instant feel; the safety
  tick prevents a class of silent-stall bugs where a future refactor forgets
  to poke from a new intake site.

- **2 — `max_depth` cap per crawl.** Privacy / blast-radius hardening, not
  a network-layer privacy lever. Adds a `max_depth` column to `crawl_queue`,
  snapshotted at enqueue (same lifecycle as `mode` / `stay_on_domain` /
  `collection_id`). Default `3` for every new crawl. User-overridable per
  crawl, including an explicit "unlimited" choice that surfaces a one-line
  warning. Phase A ships the column + default + a Crawl-tab depth input;
  Phase B adds per-row inline edit for `queued` rows. Rationale: without a
  cap, a "small look around" can quietly become tens of thousands of pages,
  drifting through adversary-controlled honeypots and accumulating
  untargeted pages on disk — the content that's hardest to defend if the
  device is ever seized. Tied to the at-rest exposure threat model in
  `docs/security/at-rest-data-exposure.md`. Note that the underlying
  `CrawlRunner` already accepts `max_depth: int | None` (see
  `crawler/runtime.py:129` and `crawler/frontier.py:129,159-164`); today
  it's nullable end-to-end and nothing sets it, so this work introduces the
  default + UI rather than new runner behaviour.

- **3 — Canonical record: queue is canonical.** `crawl_queue` rows are the
  intake/intent log and persist forever (per spec's "keep forever, manual
  clear"). `crawls` becomes a per-execution detail row. Consequences folded
  into the relevant sections below: (a) the nullable `crawl_id` FK on
  `crawl_queue` stays — UI can jump queue row → crawl detail; (b) schedule
  retiming reads `crawl_queue` rows with `source='schedule'` (when we
  intended to run), not `crawls` (when it actually ran) — prevents the
  schedule-double-fire bug when the queue is paused longer than the
  schedule interval; (c) `POST /api/crawl/start` becomes a Phase A alias
  and is removed in Phase B once frontend callers migrate. Resolves the
  three formerly-separate punch-list items #5, #6, and #7.

- **4 — Schedule daemon under the kill-switch: insert anyway, drain on
  resume.** When the kill-switch is engaged, due schedules still insert
  `crawl_queue` rows; the runner's "try advance" hook blocks dispatch
  while the switch is engaged. Mirrors the pause-toggle's
  insert-allowed-dispatch-blocked shape, so both gates behave identically.
  Schedules pile up rows during outages and drain in FIFO order on resume.
  Rationale: missing scheduled fires silently is the worse surprise for an
  analyst whose tool is supposed to be comprehensive.

- **5 — Lazy-collection name matching: case-insensitive at the column
  level.** v2 migration rebuilds `collections.name` as
  `TEXT NOT NULL UNIQUE COLLATE NOCASE`. Database-level enforcement matches
  the spec's "matching names = same destination" principle and removes the
  need for every collection-creating code path to remember a case-
  insensitive lookup pattern. Stored values retain whatever casing the user
  typed (COLLATE NOCASE only affects comparisons). Pre-flight check aborts
  the migration with a clear error if existing data has case-duplicate
  names; the developer can wipe the local dev DB if needed (see
  [[project-rabbithole-dev-db]]). Detail in the "Collections table rebuild"
  subsection.

- **6 — Route file location: new `routes/crawl_queue.py`.** Six endpoints
  is enough surface to justify its own module, and it matches the `db/`
  split. Resolves the formerly-separate punch-list item #3.

- **7 — Cancel-running coupling: coupled.** `DELETE /api/crawl/queue/:id`
  on a `running` row calls `CrawlRunnerRegistry.stop()` and marks the row
  `cancelled` in the runner's completion path. Same code path as
  `POST /api/crawl/stop`. The "cancel queue row but let the crawl finish"
  scenario isn't a real workflow; if it ever becomes one, a separate
  "Detach from queue" action is the right shape, not pre-decoupling.

- **8 — Phase B verb model: Option B — drop the silent verb.** Every
  single-URL intake routes through the Crawl tab's manual input (today's
  `Send to Crawl` behaviour, promoted to primary). Multi-row surfaces
  (Bulk Import paste, "crawl all in this collection," multi-select bottom-
  pane, graph multi-select, right-pane cluster workspace) stage rows into
  a **batch-confirm strip** in the Crawl sub-tab — a panel between
  `CrawlControls` and `CrawlQueuePanel` where the analyst picks
  mode/collection/stay-on-domain/depth once for the whole batch and
  presses `Queue N` before rows enter the queue. Rationale: matches the
  app's existing pane↔graph interaction model (`CLAUDE.md` selection
  model) — every "do something with this node" action already routes
  through a pane; silent push was the outlier. Side effect: no
  `crawl.default_mode` setting is needed; the Crawl tab dropdown the
  analyst is looking at *is* the default by construction. Source spec
  revised 2026-05-26; Crawl-tab restructure scoped down to "surgery only"
  per the same dated review (no `SeedIntake` extraction, no drawer-wrap
  of Bulk Import — Phase A's `CrawlQueuePanel` already sits between
  `CrawlControls` and `BulkImport` and the batch-confirm strip slots in
  above the queue). Phase B ready to start.

- **9 — `'dead'` lookup state: dropped from CHECK.** v1 has no producer for
  this value; shipping it as a placeholder forces future readers to wonder
  what fires it. Reintroduced via a small migration when monitor data
  provides a real signal (probably tied to the unbuilt
  monitor-confirms-dead-link path).

- **10 — Schedule production folded into the queue runner.** Decided after
  Phase A's schedule-daemon rewrite landed and the daemon's body collapsed
  to "compute next fire, push a row, sleep." Producer and dispatcher now
  live on the same `CrawlQueueRunner` and share its safety tick: each
  pass calls `produce_scheduled_rows()` (always) followed by
  `try_advance()` (gated). Two cooperating steps, one service, one async
  task. Rationale: the post-queue daemon's only job was a single SQL
  scan and an `enqueue` call; a separate async task with its own
  lifecycle, start/stop, and 60-second cadence earned nothing. The split
  responsibilities (audit-trail item 4 — producer never gated by kill
  switch / pause; dispatcher always is) are preserved by keeping the two
  methods independent inside the runner. Side benefits: schedule fires
  surface within ~10 s of their interval elapsing instead of within 60 s,
  and a process restart catches up overdue schedules before the first
  dispatch attempt (`start()` runs the producer once before scheduling
  the safety tick).

## Goal

One persistent FIFO of "URLs to crawl" for the whole project, fed by every
intake surface and drained by a single runner under the existing one-active-
crawl rule. Schedule fires become rows in this queue. The current
`POST /api/crawl/start` keeps working during the transition.

## Scope split

The package ships in two phases inside this one active package. Phase A is
the load-bearing change; Phase B is the cross-surface UX restructure.

### Phase A — backend queue + minimum frontend (ship first)

- `crawl_queue` table + `schema_version` 1 → 2 migration.
- Queue runner module (`services/crawl_queue_runner.py`).
- Queue REST + SSE surface.
- Schedule daemon rewritten to insert into the queue instead of calling the
  runtime directly.
- Existing `POST /api/crawl/start` becomes a thin alias that inserts a
  high-priority row and triggers the runner (no caller churn).
- Minimum frontend: a queue list panel on the Crawl tab and a "pause queue"
  toggle. Existing intake surfaces continue to call `startCrawl` (the alias)
  unchanged.

Phase A delivers the persistence + restart-recovery wins on its own.

### Phase B — cross-surface intake + Crawl-tab surgery (ships next, same package)

Single verb across the app: `Send to Crawl`. Single-URL surfaces load the URL
into `CrawlControls`' manual input; multi-row surfaces stage into the
batch-confirm strip. No silent push to the queue.

- New **batch-confirm strip** component in the Crawl sub-tab, between
  `CrawlControls` and `CrawlQueuePanel`. Visible only when a multi-row batch
  is staged. Owns mode / collection / stay-on-domain / depth pickers for the
  batch (defaults mirror current `CrawlControls` values) and a `Queue N` /
  `Cancel` pair. Staging replaces any prior staged batch.
- Migrate every `startCrawl(...)` call site in the frontend to
  `POST /api/crawl/queue` with the right `source` value. Remove the
  `POST /api/crawl/start` Phase A alias when no callers remain
  (audit-trail item 3).
- Add a single `Send to Crawl` action to every intake surface:
  - **Single-URL surfaces** (load URL into `CrawlControls`): graph
    right-click (any node, not stub-only — drop the stub gate at
    `lib/graph/interactions/contextMenu.ts:104`), search results
    uncrawled-row action bar, right-panel stub-node `Send to Crawl`
    button (existing — rename if needed), right-panel entity context
    menu (existing — verb already matches), right-panel domain-tab
    page-list context menu (existing — verb already matches),
    bottom-pane row context menu (existing — verb already matches),
    bottom-pane bookmarks sub-tab `▶ Send to Crawl` row action (rename
    from `▶ Crawl`), seed bookmarks dropdown picker (existing — verb
    already matches).
  - **Multi-row surfaces** (stage into batch-confirm strip): Bulk
    Import bottom-of-list `Queue all N URLs`, bottom-pane Collection
    sub-tab `Send to Crawl (all uncrawled)`, graph multi-select
    `Send to Crawl` (replaces the stub-only `Crawl selected`),
    right-pane cluster-workspace `Send to Crawl` (replaces
    `Crawl selected`).
- Bulk Import surgery: rename per-row `▶ Crawl` → `▶ Send to Crawl`
  (behaviour unchanged — load into `CrawlControls`), add bottom-of-list
  `Queue all N URLs` that stages the parsed rows.
- Per-row inline edit (mode / collection / stay-on-domain / `max_depth`)
  in `CrawlQueuePanel` for `queued` rows.
- `CrawlQueuePanel` header: pause/resume toggle (exists from Phase A),
  **Clear completed** button, "N queued · M running · K done · F failed"
  count line.
- Cross-doc spec updates already landed alongside the source-spec revision
  (2026-05-26): `crawl-left-pane.md`, `explore-graph.md`, `search-tab.md`,
  `right-pane.md`, `explore-bottom-pane.md`, `stack.md`. Re-check before
  closeout in case implementation surfaces wording gaps.

Out of scope for Phase B (deferred):
- `SeedIntake`/`CrawlIntake` extraction.
- Drawer-wrap of Bulk Import as a "Paste URLs" panel.
- Drag-and-drop reorder in the queue list.

Phase B closes the package; the `outcome.md` is written then.

## Architecture decisions

### Where does the runner live

New module: `backend/backend/services/crawl_queue_runner.py`. Owns two
cooperating steps that share one safety tick:

- `produce_scheduled_rows()` — schedule producer (replaces the original
  `ScheduleDaemon` per audit-trail item 10). Polls `crawl_schedules`,
  enqueues a `crawl_queue` row with `source='schedule'` for any schedule
  whose `interval_hours` has elapsed. Never gated by the kill switch or
  the pause flag.
- `try_advance()` — dispatcher. Claims the next queued row and starts a
  `CrawlRunner` when capacity frees up. Gated by kill switch, pause
  flag, and "registry already running."

Reasoning: `docs/reference/backend-structure.md` defines services as "long-
running process behavior and cross-route state" — exactly what this is. It
becomes a sibling of `MonitorDaemon`, `EmbedWorker`, and `LlmWorker`, all
already wired into `main.py`'s lifespan. The existing
`crawler/frontier.py` is the per-crawl frontier (the in-crawl BFS/DFS/etc.
expander) — different abstraction, stays where it is. `CrawlRunnerRegistry`
remains the one-slot dispatcher; the queue runner's `try_advance` is the
producer that feeds it.

### How the runner advances

Primary trigger: event-driven via `EventBus`. `CrawlRunnerRegistry._drive()`
already self-evicts on completion (`crawler/runtime.py:547-552`); we publish a
new `crawl.finished` event from that same finally-block (or extend an existing
`crawl.status` payload). The queue runner subscribes and immediately tries to
claim the next row.

Secondary trigger: a 5–10s safety tick. Covers three narrow cases the event
path can miss:
1. Process startup with rows already queued from a prior run.
2. Kill-switch resume — the switch clears, queued rows should start moving
   without waiting for an unrelated event.
3. The race between "runner went idle" and "subscription wired up."

Explicit triggers: `POST /api/crawl/queue` and the pause-resume route call
the runner's "try advance" hook directly so the UI feels instant.

Pause flag: `settings['crawl.queue_paused']`. When `true`, "try advance"
returns without dispatching; new rows still insert. Same idempotent shape as
the existing kill-switch gate.

### Atomic claim-next

The runner's claim uses `CrawlDB.transaction(immediate=True)` per the seam
closure:

```sql
BEGIN IMMEDIATE;
  SELECT id, url, mode, stay_on_domain, max_depth, collection_id,
         collection_name_pending
  FROM crawl_queue
  WHERE status='queued'
  ORDER BY priority DESC, created_at ASC
  LIMIT 1;
  -- (in Python) resolve collection_name_pending → collection_id if needed
  UPDATE crawl_queue
  SET status='running', started_at=?, updated_at=?
  WHERE id=? AND status='queued';
COMMIT;
```

The `AND status='queued'` guard makes the UPDATE idempotent under retry. The
lazy-collection find-or-create + rebind-siblings step happens in the same
transaction so a crash between "create collection" and "set collection_id on
queue rows" is impossible.

### Mapping a claimed row to a `CrawlRunner`

After the claim, the runner builds a `CrawlRunner` exactly the way
`routes/crawl.py:112-130` does today: `crawl_db.create_crawl(...)` for the
history row, `CrawlRunner(...)` with the snapshotted mode/collection_id, then
`CrawlRunnerRegistry.start(runner)`. On completion the queue row's
`finished_at`, `status`, and any `error` are written by listening to the
runner's terminal event (or by passing a small completion callback to the
runner so we don't depend on cross-module pub/sub for correctness).

### `POST /api/crawl/start` disposition

Phase A: the route keeps its current contract from the caller's perspective.
Implementation changes to:
1. Insert a `crawl_queue` row with `priority=1000` (or any constant above the
   default `0`) and `source='manual'`.
2. Trigger the queue runner's "try advance" synchronously.
3. Return the `crawl_id` of the newly-created `crawls` history row.

Frontend callers see no change. Phase B migrates each call site to the
explicit `/api/crawl/queue` endpoint and removes the alias.

## Schema migration

### New table

```sql
CREATE TABLE IF NOT EXISTS crawl_queue (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    url                      TEXT    NOT NULL,
    status                   TEXT    NOT NULL CHECK (status IN
        ('queued','running','completed','failed','cancelled','skipped')),
    mode                     TEXT    NOT NULL CHECK (mode IN
        ('Cross-site','BFS','DFS','Diverse','Focused')),
    stay_on_domain           INTEGER NOT NULL DEFAULT 0,
    max_depth                INTEGER,  -- NULL = unlimited (explicit opt-in); default 3 applied at enqueue
    collection_id            INTEGER REFERENCES collections(id) ON DELETE SET NULL,
    collection_name_pending  TEXT,
    source                   TEXT    NOT NULL CHECK (source IN
        ('manual','bulk','bookmark','collection','bottom_pane',
         'search','graph_menu','right_pane','schedule')),
    priority                 INTEGER NOT NULL DEFAULT 0,
    lookup_state             TEXT    CHECK (lookup_state IN
        ('unknown','crawled','stub')),
    attempts                 INTEGER NOT NULL DEFAULT 0,
    error                    TEXT,
    created_at               TEXT    NOT NULL,
    updated_at               TEXT    NOT NULL,
    started_at               TEXT,
    finished_at              TEXT,
    crawl_id                 INTEGER REFERENCES crawls(id) ON DELETE SET NULL
);
```

Notes:
- `crawl_id` (not in the spec) links a queue row to its `crawls` history row
  once dispatched. Lets the UI jump from a queue row to crawl detail. Per
  audit-trail item 3, the queue is canonical, so this FK is the lookup path
  (queue row → execution detail), not the other way around.
- `lookup_state` CHECK excludes `'dead'` (audit-trail item 9); reintroduce
  via a small migration when monitor data provides a producer.
- `stay_on_domain` is INTEGER 0/1 to match the project's existing bool idiom
  (`docs/reference/data-model.md`).

### Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_crawl_queue_pick
    ON crawl_queue(priority DESC, created_at)
    WHERE status='queued';

CREATE UNIQUE INDEX IF NOT EXISTS idx_crawl_queue_active_url
    ON crawl_queue(url)
    WHERE status IN ('queued','running');

CREATE INDEX IF NOT EXISTS idx_crawl_queue_status
    ON crawl_queue(status);
```

The partial unique on `(url) WHERE status IN ('queued','running')` enforces
the spec's dedupe rule — a URL can be re-queued after a previous run finished
(legitimate re-crawl), but cannot stack two active intents. The partial pick
index keeps the runner's claim query O(log n) regardless of terminal-status
tail size.

### Version bump

`schema_version` 1 → 2. This work claims version 2; the label-system follow-up
(currently NEXT.md item 3) bumps to 3 when its turn comes.

### Migration mechanics

The migration lives in `CrawlDB`, runs under `transaction(immediate=True)`,
and is idempotent — same shape as the existing `_migrate_flags_table` at
`db/core.py:457`. The v2 bump packages two changes into one atomic
transaction: creating `crawl_queue` and rebuilding `collections.name` for
case-insensitive uniqueness (see "Collections table rebuild" below).
Pseudocode:

```python
def _migrate_to_v2(self) -> None:
    current = self._conn.execute(
        "SELECT version FROM schema_version"
    ).fetchone()
    if current and current["version"] >= 2:
        return
    with self.transaction(immediate=True) as c:
        # Step 1 — collections table rebuild (only if existing data
        # would need migrating; fresh DBs already get COLLATE NOCASE
        # from _init_schema). Pre-flight check first; abort with a
        # clear error if existing case-duplicate names are present.
        # Step 2 — CREATE TABLE IF NOT EXISTS crawl_queue (...)
        # Step 3 — CREATE INDEX IF NOT EXISTS ...
        c.execute("UPDATE schema_version SET version=2 WHERE version=1")
        # If the row didn't exist, the INSERT in _init_schema seeded v1.
```

Ordering inside `CrawlDB.__init__`:
1. `_configure_connection()`
2. `_init_schema()` — creates `crawl_queue` and (on fresh DBs) the
   `collections` table with `name TEXT NOT NULL UNIQUE COLLATE NOCASE`, via
   `CREATE TABLE IF NOT EXISTS` (covers fresh databases without needing the
   migration path).
3. `_migrate_flags_table()` — existing.
4. `_migrate_to_v2()` — new. Handles both the collections rebuild (for
   existing DBs whose `collections.name` doesn't yet use `COLLATE NOCASE`)
   and the `crawl_queue` setup. For fresh DBs the work is just the version
   row bump; the schema is already correct from step 2.
5. `_seed_defaults()` — extend `DEFAULT_SETTINGS` with
   `"crawl.queue_paused": "false"`.
6. `_backfill_response_headers()`
7. `_sweep_stale_crawls()` — existing. Add a sibling
   `_sweep_stale_queue_rows()` that sweeps `crawl_queue` rows left `running`
   from a prior process. Per the spec: rows revert to `queued` unless they
   had already produced partial output (in which case mark `failed` with
   `error='process restarted'`). "Partial output" check is "exists a `crawls`
   row referenced by `crawl_queue.crawl_id` whose `pages_crawled > 0`".

Add `crawl_queue` to `EXPECTED_TABLES` in `db/core.py:367`.

### Collections table rebuild (case-insensitive matching)

Per audit-trail item 5, v2 rebuilds `collections.name` to use `COLLATE
NOCASE` so paste batches with mixed casing ("Investigations" vs
"investigations") can never silently fragment into separate collections.
Database-level enforcement matches the spec's "matching names = same
destination" principle and removes the need for every collection-creating
code path to remember the case-insensitive lookup pattern.

`COLLATE NOCASE` only affects comparisons; stored values retain whatever
casing the user typed. The first creator's casing wins as the display name;
a later rename can change it without code changes.

Pre-flight check, run before the rebuild and inside the same transaction:

```sql
SELECT lower(name) AS k, COUNT(*) AS n, GROUP_CONCAT(name, ', ') AS names
FROM collections
GROUP BY lower(name)
HAVING n > 1;
```

If any rows return, abort the migration with an error naming the colliding
groups and instructing the developer to merge or rename manually. Silent
merge would lose collection bindings; silent skip would ship the weaker
enforcement we're trying to eliminate.

Rebuild mechanics (standard SQLite table-rebuild recipe — SQLite can't
alter column COLLATE in place):
1. `CREATE TABLE collections_new (... name TEXT NOT NULL UNIQUE COLLATE
   NOCASE ...)` — all other columns and constraints identical to the
   current `collections` definition.
2. `INSERT INTO collections_new SELECT * FROM collections`.
3. `DROP TABLE collections`; `ALTER TABLE collections_new RENAME TO
   collections`.
4. Recreate any indexes on `collections` that were dropped with the old
   table.

FK-referencing tables (e.g. `crawl_queue.collection_id`, any node/page
references): SQLite `ON DELETE SET NULL` references resolve by table name,
so the rename preserves them without code changes. Verify after rebuild
with `PRAGMA foreign_key_check`.

Local development DB: per [[project-rabbithole-dev-db]] the developer may
drop the SQLite file rather than carry pre-existing duplicates through the
pre-flight error path. Shipped migration code still does the rigorous path
for real users.

## DB module ownership

New: `backend/backend/db/crawl_queue.py`. Owns all SQL for the queue table.
Helper functions the spec implies:

- `enqueue(db, *, url, mode, stay_on_domain, max_depth, collection_id,
  collection_name_pending, source, priority=0, now)` — with the partial-unique-
  index dedupe; returns `(row_id, was_inserted)`. `max_depth=None` is the
  explicit "unlimited" choice; callers that omit it get the default `3`
  applied inside the helper so every intake surface gets the same default.
- `enqueue_batch(db, items, *, now)` — single transaction; in-batch dedupe by
  URL is silent (the spec calls this out).
- `list_queue(db, *, status=None, source=None, limit=None, offset=None)`.
- `get_queue_row(db, row_id)`.
- `update_queue_row(db, row_id, **fields)` — `mode`, `stay_on_domain`,
  `max_depth`, `collection_id`, `priority`. Refuses on non-`queued` status
  (per the spec's "inline edit before it runs").
- `cancel_queue_row(db, row_id)` — sets `status='cancelled'`. For a `running`
  row, also fires the runner's stop path (described under "Cancellation"
  below).
- `retry_queue_row(db, row_id)` — `failed` → `queued`, clears `error`,
  bumps `attempts` and `updated_at`.
- `claim_next(db, *, now)` — the atomic claim above; returns the snapshotted
  row or `None`.
- `mark_terminal(db, row_id, *, status, error=None, now)` — single helper for
  the runner's completion path (`completed` / `failed` / `cancelled`).
- `resolve_pending_collection(db, *, name, now)` — find-or-create on
  `collections.name`, then rebind every still-`queued` row sharing the same
  `collection_name_pending` (per spec "two batches same pending name").
- `sweep_stale_queue_rows(db, *, now)` — restart-recovery helper called from
  `CrawlDB.__init__`.

Why a dedicated module: matches the project pattern (`db/crawl.py`,
`db/collections.py`, etc.). Keeps `db/crawl.py` focused on the `crawls`
history table; queue is a separate concern.

## REST + SSE surface

New route module: `backend/backend/routes/crawl_queue.py` (audit-trail item
6). Symmetric with `db/crawl_queue.py`; keeps `routes/crawl.py` focused on
the `crawls` history surface.

Endpoints per the spec:

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/crawl/queue` | Enqueue one URL or many (`urls: string[]`). Per-row result with `lookup_state`, `inserted_id`, dedupe reason if skipped. |
| GET | `/api/crawl/queue` | List rows, filterable by `status`, `source`. |
| PATCH | `/api/crawl/queue/:id` | Edit mode / collection / priority (priority bump powers the "start next" row action). |
| DELETE | `/api/crawl/queue/:id` | Cancel `queued` or remove terminal rows. |
| POST | `/api/crawl/queue/:id/retry` | Reset failed → queued. |
| PUT | `/api/settings/crawl.queue_paused` | Pause / resume runner. Existing settings route already covers this — verify the validator allows the key. |

All accept `Depends(get_active_db)`. Lookup-state is computed inside the
enqueue helper with one SQL probe per URL: `SELECT stub FROM nodes WHERE url=?`.
No Tor traffic at enqueue.

SSE: add channel `crawl_queue.changed` published on every state transition
(insert, claim, terminal). Payload carries `{row_id, status, source}` so the
frontend can patch without re-listing. The existing `crawl.status` /
`crawl.page` channels continue to carry the active crawl's progress; nothing
moves.

Export route (`GET /api/crawl/queue/export?format=csv|json`) is a follow-up
per the spec and is not in this package.

## Cancellation semantics

- `DELETE /api/crawl/queue/:id` on a `queued` row → `status='cancelled'`,
  done.
- `DELETE /api/crawl/queue/:id` on a `running` row → call
  `CrawlRunnerRegistry.stop()` (the existing cooperative stop), then mark the
  queue row `cancelled` in the runner's completion path. Same code path as
  `POST /api/crawl/stop` so kill-switch / half-state reaping behavior is
  unchanged.
- `DELETE` on terminal rows (`completed`, `failed`, `cancelled`, `skipped`)
  → row deleted from the table. Powers "Clear completed" header button
  behavior at the row level.

## Schedule production (folded into the queue runner)

Per audit-trail item 10, the standalone `ScheduleDaemon` is retired. Its
body — already reduced by Phase A to "compute next fire time, push to
queue, return" — becomes a method on the queue runner:

- `CrawlQueueRunner.produce_scheduled_rows()` keeps the "no active
  project" early-return; the registry-is-running gate goes away, since
  the runner's other half (`try_advance`) owns dispatch.
- The producer is never gated by the kill switch or the pause flag —
  schedules continue to enqueue queue rows during a Tor outage, and the
  dispatcher blocks execution while the switch is engaged. Mirrors the
  pause-toggle's insert-allowed-dispatch-blocked shape (audit-trail item
  4).
- For each due schedule row, the producer inserts into `crawl_queue`
  with `source='schedule'`, the schedule's `mode`/`collection_id`
  snapshotted, `priority=0`. Per audit-trail item 3, the
  `last_started_at` tracking that decides "is this schedule due" reads
  `crawl_queue` rows with `source='schedule'` (when we *intended* to
  run), not `crawls` rows. Helper in `db/crawl_queue.py`; old
  `db/crawl.py:last_started_at` is retired.
- The producer no longer builds `CrawlRunner` instances. All that code
  goes away.
- One schedule still fires per producer pass — no need to drain
  multiple due rows in one tick; the dispatcher picks them up FIFO
  anyway, and the next pass catches the next due schedule.

`crawl.status='scheduled_fired'` event payload: keep it, emit on the
queue *insert* instead of registry start. Frontend that listens for this
to refresh schedule UI keeps working.

Lifecycle: producer runs once during `CrawlQueueRunner.start()` (so a
restart catches up overdue schedules before the first dispatch attempt)
and on every safety tick of `_run`. The two steps are wrapped in
independent `try/except` blocks so a failure in one doesn't suppress the
other on the same tick.

## Frontend intake mapping (Phase B detail)

Under Option B (audit-trail item 8) every intake routes through the Crawl
sub-tab. Single-URL surfaces load into `CrawlControls`' manual input;
multi-row surfaces stage into the batch-confirm strip. Nothing enters the
queue silently.

| Surface | Behaviour | Notes |
| --- | --- | --- |
| Crawl tab `CrawlControls` Start button | Direct enqueue (single-URL, immediate dispatch) | `CrawlControls.svelte:209` migrates from `startCrawl` to `POST /api/crawl/queue` via `lib/api/crawlQueue.ts`. The "Start" button still does what the analyst expects (queue + immediate dispatch) because the runner advances on insert when idle. `source='manual'`. |
| Bulk Import per-row `▶ Send to Crawl` | Single-URL (load into `CrawlControls`) | `BulkImport.svelte` — rename label, keep current `onSendToCrawl` callback behaviour. |
| Bulk Import bottom-of-list `Queue all N URLs` | Multi-row (stage in batch-confirm strip) | New button below the parsed rows. Calls the staging API on the Crawl tab; the strip then enqueues with `source='bulk'`. |
| Seed bookmarks dropdown (Crawl controls) | Single-URL (fills `CrawlControls`) | Already matches Option B — selection fills the manual input; no code change required. |
| Bottom-pane Bookmarks `▶ Send to Crawl` | Single-URL (load into `CrawlControls`) | Rename from `▶ Crawl`; behaviour unchanged. `source='bookmark'`. |
| Graph right-click single node | Single-URL (load into `CrawlControls`) | `lib/graph/interactions/contextMenu.ts:104` — drop the stub-only gate; broaden to any node. Test at `contextMenu.test.ts:141,153` needs the gate-removal expectation. Existing single-node `Send to Crawl` flow already loads `CrawlControls`. |
| Graph right-click multi-select | Multi-row (stage in batch-confirm strip) | Rename `Crawl selected` → `Send to Crawl`; drop the stub-only gate; stage all selected URLs. `source='graph_menu'`. |
| Search results uncrawled row | Single-URL (load into `CrawlControls`) | `search-tab.md` rewrite — `Send to Crawl` replaces the old `Queue Crawl`. `source='search'`. |
| Right-panel stub node `Send to Crawl` button | Single-URL (load into `CrawlControls`) | Existing button (was `Crawl now`); rename label, behaviour unchanged. `source='right_pane'`. |
| Right-panel entity context menu `Send to Crawl` | Single-URL (load into `CrawlControls`) | Existing — verb already matches Option B. No code change. |
| Right-panel domain-tab page-list `Send to Crawl` | Single-URL (load into `CrawlControls`) | Existing — verb already matches. No code change. |
| Right-pane cluster workspace `Send to Crawl` button | Multi-row (stage in batch-confirm strip) | Renames `Crawl selected`; stages the cluster selection regardless of stub state. `source='right_pane'`. |
| Bottom-pane row context menu `Send to Crawl` | Single-URL (load into `CrawlControls`) | Existing — verb already matches. No code change beyond `source='bottom_pane'` wiring. |
| Bottom-pane Collection sub-tab `Send to Crawl (all uncrawled)` | Multi-row (stage in batch-confirm strip) | Renames `Crawl all uncrawled`; replaces the inline popover with the batch-confirm strip. `source='collection'`. |

All paths funnel through a single frontend helper (`lib/api/crawlQueue.ts`)
that wraps `POST /api/crawl/queue`. Single-URL paths call into a shared
"load into CrawlControls" handler; multi-row paths call a shared "stage
batch" handler on the Crawl sub-tab. Toast text comes from one place.

GraphCanvas has two `startCrawl` call sites
(`GraphCanvas.svelte:1138,1196`) that participate in the graph
context-menu flow; both migrate alongside the context-menu Phase B work.

## Test plan

Backend:
- Schema creates `crawl_queue`, indexes, version row.
- Migration is idempotent (run twice in one process, then re-open DB).
- `_sweep_stale_queue_rows` flips `running` → `queued` for partial-output-less
  rows and `running` → `failed` for rows with partial output.
- `enqueue` dedupes against `queued`+`running` rows; allows re-enqueue after
  terminal.
- `enqueue_batch` dedupes silently within the batch.
- `claim_next` is atomic under concurrent calls (loop two threads, only one
  wins).
- Pause flag blocks dispatch but not enqueue.
- Cancel on a `queued` row updates status.
- Cancel on a `running` row triggers `CrawlRunnerRegistry.stop()` and the
  completion path marks `cancelled`.
- Schedule daemon `_tick` inserts a `crawl_queue` row with `source='schedule'`.
- Lazy-collection: enqueue with `collection_name_pending='X'`; the runner
  claims the row, creates the collection, rebinds sibling pending rows.
- Lazy-collection collision: a collection named `X` already exists at claim
  time → silently use it.
- Existing crawler/route tests for `/api/crawl/start` still pass under the
  alias.
- `max_depth` default: `enqueue` called without `max_depth` writes `3` to the
  row; explicit `max_depth=None` writes NULL (unlimited). Claimed row's
  `max_depth` is passed through to the `CrawlRunner` and the frontier
  rejects entries deeper than the cap (`crawler/frontier.py:159-164`).
- Collections rebuild — fresh DB: a fresh-init `collections` table accepts
  `"Foo"` then rejects `"foo"` on UNIQUE (proves the `COLLATE NOCASE`
  declaration is in `_init_schema`, no rebuild path taken).
- Collections rebuild — clean v1 upgrade: seed a v1-shaped DB with a few
  collections (no case-duplicates), run `_migrate_to_v2()`, assert rows
  preserved, `PRAGMA foreign_key_check` empty, and post-rebuild
  `INSERT INTO collections (name) VALUES ('Foo')` then `('foo')` raises
  UNIQUE.
- Collections rebuild — abort on case-duplicates: seed a v1-shaped DB with
  `"Foo"` and `"foo"`, run `_migrate_to_v2()`, assert the migration raises
  the expected error and no partial state is committed (schema_version
  still `1`, `crawl_queue` table absent if not already created).
- `resolve_pending_collection` is case-insensitive: enqueue
  `collection_name_pending='Investigations'` when `collections` already
  has `"investigations"`; assert the runner binds to the existing row, not
  a new one.

Frontend (Phase B):
- Queue list view updates on `crawl_queue.changed` SSE.
- Pause toggle persists.
- Per-row inline edit only available while `queued`.
- "Start next" bumps `priority` and the runner picks that row next.

## Phase B status

Ready to start. Source spec was revised to Option B on 2026-05-26;
cross-doc specs (`crawl-left-pane.md`, `explore-graph.md`,
`search-tab.md`, `right-pane.md`, `explore-bottom-pane.md`, `stack.md`)
were updated alongside; the "Frontend intake mapping" table above and
`checklist.md`'s Phase B section were rewritten to the surgery-only
scope.

Recommended sequencing:

1. Build the batch-confirm strip component in the Crawl sub-tab (no
   intake surface wired up yet) — establishes the staging API that the
   rest of Phase B targets. Visible-when-staged, defaults from
   `CrawlControls`, `Queue N` enqueues via `lib/api/crawlQueue.ts`.
2. Migrate `CrawlControls.svelte:209` from `startCrawl` to
   `POST /api/crawl/queue` with `source='manual'`. Existing tests verify
   queue + immediate dispatch is unchanged.
3. Bulk Import surgery: rename per-row `▶ Crawl` → `▶ Send to Crawl`
   (behaviour unchanged), add bottom-of-list `Queue all N URLs` that
   calls the staging API.
4. Remaining surfaces, in any order — each lands with its menu item +
   test: graph right-click (single + multi-select, drop stub-only gate);
   bottom-pane Bookmarks rename; bottom-pane Collection sub-tab
   `Send to Crawl (all uncrawled)`; search results uncrawled-row
   `Send to Crawl`; right-pane cluster workspace `Send to Crawl`;
   right-pane stub-node button rename.
5. `CrawlQueuePanel` enhancements: per-row inline edit on `queued` rows,
   `Clear completed` button, count line.
6. Remove `POST /api/crawl/start` alias once no `startCrawl(...)` callers
   remain. Verify with grep.
7. Re-run backend + frontend tests; address any surface gaps in the
   cross-doc specs found during implementation.
8. Write `outcome.md`; archive the package; repoint `ACTIVE.md`.
