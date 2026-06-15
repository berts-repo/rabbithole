# Outcome — Durable Crawl Queue

Closed: 2026-05-26

## What shipped

### Phase A — backend queue + minimum frontend

- `crawl_queue` table added to schema (`schema_version` → 2). Partial unique
  index on `(url) WHERE status IN ('queued','running')` enforces dedupe.
  `max_depth` column is `NULL` = unlimited; default 3 applied at enqueue.
- `collections.name` rebuilt with `COLLATE NOCASE UNIQUE` in the same v2
  migration. Pre-flight scan aborts on case-duplicate rows; existing data
  preserved intact.
- `CrawlDB._sweep_stale_queue_rows()` resets any rows left `running` at
  startup (process crash recovery).
- `CrawlQueueRunner` service replaces `ScheduleDaemon`. Runs as an asyncio
  task: event-driven pokes + 5–10 s safety tick. Produces schedule-fired rows
  and drains FIFO (priority DESC, created_at ASC). Gated by kill switch and
  pause flag at dispatch time, not enqueue time.
- Six REST endpoints under `/api/crawl/queue` (list, enqueue, get, patch,
  delete, retry) plus SSE channel `crawl_queue.changed`.
- `CrawlQueuePanel.svelte` — queue panel with pause/resume toggle, count line
  (N queued · M running · K done · F failed), Clear completed button, per-row
  inline edit (queued rows only), and SSE-driven refresh.
- Crawl-tab max depth input with Unlimited affordance and warning.
- 672 backend tests passing.

### Phase B — cross-surface intake + Crawl-tab surgery

- Single verb across the app: **Send to Crawl**.
- `BatchConfirmStrip.svelte` — staged between CrawlControls and
  CrawlQueuePanel. Visible only when a multi-row batch is staged. Defaults
  mirror CrawlControls snapshot at stage time. Restage replaces with toast.
- `batchConfirmStore` (`lib/stores/batchConfirm.svelte.ts`) — shared staging
  surface for all intake sites. `stage()`, `discard()`, `clear()`,
  `loadIntoControls()`, `consumePendingLoad()`.
- Migrated intake surfaces:
  - `CrawlControls` Start → `POST /api/crawl/queue` (source `manual`)
  - Bulk Import per-row `▶ Crawl` renamed to `▶ Send to Crawl`
  - Bulk Import `Queue all N URLs` → `batchConfirmStore.stage()`
  - Graph single-node context menu `Send to Crawl` — stub gate removed
  - Graph multi-select context menu `Send to Crawl` — stub gate removed;
    stages batch
  - `GraphCanvas` two double-click call sites → `loadIntoControls()`
- Deferred surfaces (F6/F7/F8 not built): Bookmarks row, Search results row,
  right-pane stub button, Collection sub-tab crawl-all, cluster workspace
  Send to Crawl.
- `POST /api/crawl/start` alias removed from `routes/crawl.py`. Zero
  `startCrawl(` call sites in frontend after migration.
- Cross-doc specs updated: crawl-left-pane, explore-graph, search-tab,
  right-pane, explore-bottom-pane, stack. Final re-check 2026-05-26 — no
  wording corrections needed.

## Schema version on disk

`schema_version = 2`

## Deviations from plan

- Frontend tests (batch-confirm strip, context menu, bulk import,
  CrawlQueuePanel) were not written. The project's vitest config explicitly
  excludes `.svelte` and `.svelte.ts` files; structural correctness is
  verified by `npm run check` + `npm run build`. Owner elected to skip
  extracting pure helpers for unit testing.
- Batch-confirm strip does not show the spec's "summary row" (dedupe preview
  before queuing). Dedupe results are surfaced as a toast after `Queue N`
  returns. Spec wording left as-is — this is a feature gap, not a
  contradiction.
- `Start next`, `Retry`, lookup badge, and mode/collection chips on queue rows
  are spec'd in crawl-left-pane.md but were not part of Phase B scope and
  remain unimplemented.
