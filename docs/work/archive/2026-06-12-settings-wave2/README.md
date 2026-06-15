# Settings Modal Completion — Wave 2

Finishes Settings as the single discoverable home for durable project
configuration. Wave 1 (archived `2026-06-09-settings-modal/`) shipped the
left-rail autosave modal with Graph, Engines, Watchlist, Browser, Embedding,
and later Labels tabs. Wave 2 appends the remaining configuration domains.

## Scope source

`docs/work/additions/settings-modal.md` (the live Wave-2 scope) and
`docs/work/NEXT.md` item 1.

## Slices

Each slice is a complete vertical: every control it ships is wired to a live
backend consumer. No slice ships a knob nothing reads.

- **Slice 1 — surfacing tabs (shipped).** Tor / Privacy, Crawl & Queue, and
  LLM / Ollama tabs over settings keys that already have backend consumers and
  validators but no Settings-modal home yet. Pure UI over the existing
  `PUT /api/settings/{key}` autosave seam.
- **Slice 2 — Retention (shipped, job-history only).** `retention.jobs_days`
  prunes terminal job-tracking rows; net-new validator + `db/jobs` prune/count +
  startup sweep + `routes/retention.py` + tab. Page snapshots are **not** pruned
  (owner decision — would erase the version-history record); "log retention" was
  dropped (no log store). See `decisions.md`.

Remaining Wave-2 knobs (Tor circuit refresh, crawl retry/capacity, LLM timeouts)
are deferred to enforcement work — see `decisions.md` "Open (later / owner)".

## Read order

1. `docs/work/additions/settings-modal.md`
2. `frontend/src/components/modals/SettingsModal.svelte` and its
   `settings/*.svelte` tab components (autosave pattern)
3. `backend/backend/db/settings.py` (validators) and
   `backend/backend/routes/settings.py`
4. `plan.md`, `checklist.md`, `decisions.md` here
