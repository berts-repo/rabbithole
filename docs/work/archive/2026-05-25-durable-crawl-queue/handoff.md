# Handoff

Status: Phase A shipped. Source spec revised to Option B on 2026-05-26
(single-verb intake + batch-confirm strip); cross-doc specs updated
alongside; Phase B sections of `plan.md` and `checklist.md` rewritten
to the surgery-only scope. Phase B ready to start — see "Phase B
status" at the end of `plan.md` for recommended sequencing.

## Read first

1. `README.md` — package framing + the per-crawl-frontier vs durable-queue
   distinction.
2. `plan.md` — full implementation plan, including the "Decisions taken
   during planning review" audit trail and the "Phase B status" sequencing
   plan.
3. `source-spec.md` — promoted source spec with owner-resolved decisions.
4. `../../../reference/data-model.md` — current schema.
5. `../../../reference/backend-structure.md` — service / route / db module
   conventions.

## Likely files

Backend:
- `backend/backend/db/core.py` — schema DDL, indexes, `_migrate_to_v2`,
  `_sweep_stale_queue_rows`, `EXPECTED_TABLES`, `DEFAULT_SETTINGS`.
- `backend/backend/db/crawl_queue.py` — new module (full helper surface
  listed in `plan.md`).
- `backend/backend/db/crawl.py` — retire `last_started_at`; new equivalent
  lives in `db/crawl_queue.py` and reads `crawl_queue` rows with
  `source='schedule'` (audit-trail item 3).
- `backend/backend/services/crawl_queue_runner.py` — new runner. Owns
  both the schedule producer (`produce_scheduled_rows`) and the
  dispatcher (`try_advance`); the standalone `services/schedule_daemon.py`
  is retired (audit-trail item 10).
- `backend/backend/services/event_bus.py` — register
  `crawl_queue.changed` channel.
- `backend/backend/routes/crawl.py` — rewrite `POST /api/crawl/start` as a
  Phase A alias (removed in Phase B per audit-trail item 3).
- `backend/backend/routes/crawl_queue.py` — new module (audit-trail item 6).
- `backend/backend/main.py` — wire the new runner into the lifespan.

Frontend (Phase B unless noted):
- `frontend/src/lib/api/crawlQueue.ts` — new (Phase A).
- `frontend/src/components/crawl/CrawlControls.svelte` — migrate
  `startCrawl` call site.
- `frontend/src/components/crawl/BulkImport.svelte` — row action + the
  later drawer relocation.
- `frontend/src/lib/graph/interactions/contextMenu.ts` — Queue Crawl /
  Send to Crawl items; drop stub-only gate.
- `frontend/src/lib/graph/interactions/contextMenu.test.ts` — adjust the
  two tests at lines 141 and 153.
- `frontend/src/components/graph/GraphCanvas.svelte` — migrate the two
  `startCrawl` call sites at lines 1138 and 1196.
- Search results, right-panel, bottom-pane, collection view components.

Docs to update when this lands:
- `docs/reference/data-model.md` — new table, version bump.
- `docs/reference/backend-structure.md` — new service module.
- All spec files called out at the end of `plan.md`.

## Recommended sequencing

Phase A is shipped. Phase B sequencing is detailed in `plan.md` "Phase B
status" — eight numbered steps starting with the batch-confirm strip
component, then surface migrations, queue-panel enhancements, alias
removal, test sweep, and close-out. Each surface migration lands with
its component change + test in the same PR.

## Risks worth watching

- The schedule-daemon rewrite changes what "schedule last fired" means.
  Audit-trail item 3 settles this — retiming reads `crawl_queue` rows with
  `source='schedule'` (intent), not `crawls` (actual run). Cover with a
  test that pauses the queue longer than the schedule interval and asserts
  the schedule does NOT double-fire.
- Collections table rebuild needs a pre-flight check for existing
  case-duplicate names; if developer or user data hits this, the migration
  aborts with a clear error. Cover both clean-upgrade and abort paths.
- The atomic claim is the only piece of new code where a race matters. Test
  it under concurrent calls; rely on `transaction(immediate=True)`.
- The lazy-collection rebind step has to be in the same transaction as the
  claim; otherwise a crash leaves orphan pending rows. Test the crash path
  (or at least the SQL ordering).

## Plain-English schedule note

Schedule production is now a step inside the crawl queue runner
(`produce_scheduled_rows`), not a separate daemon. It treats the durable
queue as the source of truth for "this schedule already fired." In
practice:

- Before this change, schedule timing looked at `crawls.started_at`, which is
  the moment a crawl actually began.
- Now it looks at `crawl_queue` rows with `source='schedule'`, which records
  when the schedule intended to fire, even if the queue was paused or blocked.
- On the first tick after upgrading, if no schedule-origin queue row exists
  yet for that URL, the producer falls back once to the old `crawls.started_at`
  value.

User impact: post-upgrade schedules should keep their normal cadence instead of
immediately firing again just because the queue is new. From the analyst's
perspective, this mainly avoids surprise duplicate scheduled crawls right after
upgrade or after a period where dispatch was held. Side effect of folding the
producer into the queue runner: schedules now fire within ~10 s of their
interval elapsing (the queue runner's safety tick) instead of within 60 s
(the old daemon's tick), and a process restart catches up overdue schedules
before the first dispatch attempt.
