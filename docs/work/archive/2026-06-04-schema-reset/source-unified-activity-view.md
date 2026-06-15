# Unified Activity View

## Status

Implementation-ready feature spec. Ships as part of the Schema Reset
Milestone (`schema-reset.md`) — the `jobs` table and the consuming
`ActivityTab.svelte` land together in one cutover. No separate
frontend-only adapter phase: the schema and the UI were designed together,
the cutover is already being taken for the wider schema reset, and an
intermediate client-side adapter would be throwaway work.

## Goal

One bottom-pane tab that answers "what is the system doing right now?"
across every kind of work — crawls, scheduled crawls, analyses, monitor
probes, live crawl progress, staged batch intake. Single place to monitor,
pause, retry, cancel.

Today the answer requires checking three places: left pane (crawl queue,
schedules), bottom pane (Live Crawl, Analyses), and domain surfaces (monitor
probes). Each uses its own status vocabulary. That fragmentation is the most
visible "this app feels unfinished" pain point.

## Schema — `jobs` Table

One row per piece of work across every source. Workers write directly to
this table instead of to per-source status columns.

```sql
CREATE TABLE jobs (
    id          INTEGER PRIMARY KEY,
    kind        TEXT    NOT NULL,        -- crawl, schedule, analysis, probe, live-crawl, batch
    target_type TEXT    NOT NULL,        -- url, domain, collection, cluster
    target_id   INTEGER NOT NULL,
    status      TEXT    NOT NULL,        -- unified vocabulary (below)
    payload     TEXT,                    -- JSON, kind-specific config
    result      TEXT,                    -- JSON, completion data
    error       TEXT,
    created_at  TEXT,
    started_at  TEXT,
    finished_at TEXT
);

CREATE INDEX jobs_status_idx ON jobs(status);
CREATE INDEX jobs_kind_idx ON jobs(kind);
```

Source-specific configuration lives in `payload`; results in `result`. The
work itself stays domain-specific — only the status/queue tracking layer
unifies.

## Unified Status Vocabulary

One vocabulary for every kind of job:

```
pending | running | done | failed | cancelled | paused
```

Workers translate their internal lifecycle to this vocabulary at write
time, so the UI never sees `queued`/`in_progress`/`completed` or
`waiting`/`processing`/`success` variants.

## Worker Changes

Each existing worker writes to `jobs` instead of its own status table:

- **Crawl queue runner** — writes `kind = 'crawl'` rows; live-crawl progress
  writes `kind = 'live-crawl'` rows.
- **Scheduled crawl scheduler** — writes `kind = 'schedule'` rows for
  upcoming scheduled crawls and spawns `kind = 'crawl'` children on fire.
- **LLM / analysis worker** — writes `kind = 'analysis'` rows for every
  analysis run. The result row continues to land in the appropriate typed
  analyses table (`analyses` for page/resource targets,
  `collection_analyses` for collection targets, and `cluster_analyses` if
  Cluster Q&A is later added); the `jobs` row carries the work-tracking
  status and a `payload` back-reference to the analyses row.
- **Monitor daemon** — writes `kind = 'probe'` rows.
- **Batch intake** — writes `kind = 'batch'` rows for staged-but-not-yet-run
  batches.

## API

One endpoint replaces the per-source status/history endpoints:

```
GET    /api/jobs            -- list, with filters: kind, status, target_type, since, limit
GET    /api/jobs/:id        -- single job detail
POST   /api/jobs/:id/cancel
POST   /api/jobs/:id/retry
POST   /api/jobs/:id/pause
POST   /api/jobs/:id/resume
SSE    /api/jobs/stream     -- live updates as jobs change state
```

## Activity Tab UI

New bottom-pane tab: `ActivityTab.svelte`.

### Row Shape

```ts
type ActivityRow = {
  id: string;                    // "job:42"
  kind: 'crawl' | 'schedule' | 'analysis' | 'probe' | 'live-crawl' | 'batch';
  target: { type: 'url' | 'domain' | 'collection' | 'cluster'; label: string };
  status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled' | 'paused';
  startedAt?: string;
  finishedAt?: string;
  progress?: { current: number; total: number };
  error?: string;
};
```

### Behaviour

- Filter by kind (all / crawls / analyses / probes / schedules / batches /
  live-crawl).
- Sort by recency (started / finished).
- Group by status or by target (toggle).
- Row actions: pause, resume, retry, cancel, inspect. Actions call the new
  `POST /api/jobs/:id/*` endpoints.
- Click a row → opens the target in the right pane.
- Live updates via `/api/jobs/stream` SSE.

## Replacement of Existing Tabs

When the cutover lands:

- **Live Crawl tab** → becomes a filter of Activity (`kind = live-crawl`)
  but the streaming log view is valuable enough to keep as its own tab.
- **Analyses tab** → folds entirely into Activity (`kind = analysis`) and is
  removed.
- **Crawl Queue tab** (moved to the bottom pane by
  `pane-responsibility-reset.md`) → folds into Activity (`kind = crawl`)
  and is removed.
- **Scheduled Crawls** → keep as a separate tab; schedules are a planning
  view, not an activity view.

## What Gets Deleted

In the same cutover:

- Source-specific status columns in `crawls`, `crawl_queue`, `analyses`,
  `collection_analyses`, `monitors`.
- Three separate worker-state query paths in the API.
- Per-source history endpoints (merged into `GET /api/jobs`).
- `AnalysesTab.svelte` and the bottom-pane Crawl Queue tab UI (absorbed).

Rough estimate: 400–700 LOC backend deletion plus the absorbed bottom-pane
tabs on the frontend.

## User-Visible Changes

- New Activity tab in the bottom pane showing every in-flight piece of work
  across crawls, schedules, analyses, probes, live crawl, and batches.
- Consistent status badges and vocabulary across all kinds.
- One filter / sort / group control instead of per-tab repeats.
- Job history queryable across all kinds, with retention managed from the
  Retention tab in `settings-modal.md`.
- Analyses tab disappears (absorbed). Crawl Queue tab absorbed.

## Affected Surfaces

Backend:

- New: `backend/backend/db/jobs.py`, `backend/backend/routes/jobs.py`.
- Worker changes in crawl queue runner, scheduled-crawl scheduler, LLM /
  analysis worker, monitor daemon, batch intake.
- Removals across existing per-source status/history code.

Frontend:

- New: `frontend/src/views/bottom/ActivityTab.svelte`.
- New: `frontend/src/lib/api/jobs.ts`.
- New: `frontend/src/lib/stores/jobs.svelte.ts` (live SSE stream).
- Removed: `frontend/src/views/bottom/AnalysesTab.svelte`.
- Removed: the bottom-pane Crawl Queue tab component (after
  `pane-responsibility-reset.md` moves it there from the left pane).

## Relationship to Other Work

- Bundled into `schema-reset.md` — the `jobs` table is one of the four
  schema-touching cleanups in that milestone, and the Activity tab ships in
  the same cutover.
- Depends on `pane-responsibility-reset.md` (bottom pane owns activity).
- Depends on `shared-ui-primitives.md` (Activity tab built on shared
  primitives — `StatusBadge`, `EmptyState`, `IconButton`, `PaneTabs`).
- Required by `analysis-intel-pane.md` — Intel pane assumes Activity has
  already absorbed the bottom-pane Analyses tab.
- Required by `settings-modal.md` Wave 2 — the Crawl & Queue and Retention
  tabs target the real `jobs` table.
- Activity is a **work set**, not a node set. `list-to-graph-tabs.md` does
  not generalise to it.

## Deferred Decisions

- Whether scheduled crawls render in Activity as `pending` rows with a
  future `startedAt`, or stay entirely separate.
- Job retention policy (how long completed jobs stay in `jobs` before being
  purged). Ties into Retention tab in `settings-modal.md`.
- Whether `jobs` is the right table name or whether `activity` reads better
  in the SQL / API.
- Whether the unified table introduces job retries with backoff or keeps
  the existing per-source retry logic.
- Whether `StatusBadge` needs a distinct `paused` variant or reuses the
  existing pending styling with an icon overlay.
