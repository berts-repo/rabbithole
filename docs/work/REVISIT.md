# Revisit

A durable watch-list of things to **come back to** or **possibly remove** —
distinct from `NEXT.md`, which is work intended to be built. Nothing here is a
commitment to build; items may instead be deleted once a trigger resolves.

This file survives package archival on purpose. When an active package closes,
graduate its `decisions.md` "Open (later)" items into this list so they are not
buried in `archive/` (which the read-order rules skip).

Each row: **what · why parked · trigger to act-or-delete · pointer.**

## Revisit (deferred decisions awaiting a trigger)

- **Continuous retention sweep.** Job-history retention currently runs only at
  backend startup + the manual "Run cleanup now" button. *Trigger:* if long-
  running sessions let terminal job rows pile up enough to matter, add a
  throttled periodic sweep. *Pointer:* `db/jobs.prune_terminal_jobs`,
  `services/crawl_queue_runner.py` (a natural existing tick to hang it on),
  `archive/2026-06-12-settings-wave2/decisions.md`.
- **Graph domain spacing — alternative layouts.** Shipped fix weights edges by
  domain boundary (`CROSS_DOMAIN_WEIGHT=5` / `INTRA_DOMAIN_WEIGHT=0.3`), so the
  spacing is emergent from the physics and tuned via those constants. *Trigger:*
  if that emergent spacing proves too unpredictable to tune on real graphs,
  reach for one of two parked alternatives — cluster-by-domain-then-expand
  (`groupByDomain` / `clusterDomain.ts`) or a custom two-phase layout under
  `frontend/src/lib/graph/layouts/` (reuse `graph/model/geometry.ts`). Tune the
  constants first before either. *Pointer:* `frontend/src/lib/graph/layouts/`
  `force.ts`; full sketch in git history of `additions/graph-domain-spacing.md`.

## Deferred knobs (no backend consumer yet — do NOT ship as UI until one exists)

These were intentionally left out of Settings Wave 2 because a control with no
effect is a misleading surface. Each needs enforcement built first.

- **Tor control-port / NEWNYM circuit refresh.** Needs a control-port client
  (port 9051 + auth) that does not exist. Overlaps `NEXT.md` item "Crawler
  privacy cleanup". *Trigger:* decide whether circuit refresh lives in Settings
  or stays a crawl-privacy feature, then build the client.
- **Crawl worker-capacity / retry policy.** Needs a settings consumer in
  `services/crawl_queue_runner.py` (retry is manual today via
  `POST /api/jobs/{id}/retry`). *Trigger:* build the consumer, then surface.
- **LLM request timeouts / extra concurrency** (beyond `llm.batch_size`). No
  consumer in `services/llm_worker.py`. *Trigger:* add the consumer, then
  surface in Settings → LLM / Ollama.

## Maybe remove (verify before deleting — confirm it really is dead)

- **`docs/work/active/2026-06-09-search-tab/`.** `ACTIVE.md` reports no active
  package other than settings-wave2, so this looks like a leftover that was
  never archived. *Action:* confirm it shipped, then move to
  `archive/2026-06-09-search-tab/` (or delete if fully superseded).

## Loose ends (inline markers to not lose)

- `frontend/src/lib/stores/crawl.svelte.ts:12` — `TODO(B8)`: drop the local
  counter shim if `crawl.status` ever emits the counters directly.
- `frontend/src/components/AppHeader.svelte:20` — `TODO(F5)`: settings-changed
  badge once `graph.*` non-default detection exists.

## Rules

- Keep rows short; link to code or a package rather than re-explaining it.
- When you act on an item (build it, or delete the thing), remove the row.
- On package archival, move any still-open "Open (later)" decisions here.
- This is not a priority queue — ready, intended work belongs in `NEXT.md`.
