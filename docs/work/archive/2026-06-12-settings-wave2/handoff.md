# Handoff

## State

**Slice 1 complete (uncommitted at time of writing).** Three new Settings tabs
ship over already-consumed settings keys:

- `frontend/src/components/modals/settings/TorPrivacyTab.svelte`
- `frontend/src/components/modals/settings/CrawlQueueTab.svelte`
- `frontend/src/components/modals/settings/LlmOllamaTab.svelte`
- wired into `SettingsModal.svelte` (`TabId` union, `TABS`, render switch)

No backend changes were needed — every control writes an existing validated key
(`tor.proxy`, `tor.kill_switch`, `crawl.pacing`, `crawl.queue_paused`,
`llm.ollama_url`, `llm.model`, `llm.batch_size`, `llm.auto_start`) through the
existing `PUT /api/settings/{key}` autosave seam, identical to the Wave 1 tabs.

Gates: `npm run check` 0 errors, `npm run build` emits the single
bundle.js/bundle.css. Not yet exercised live in-browser (the controls reuse the
proven Wave 1 autosave path; the underlying keys are already covered by
`backend/tests/test_b4_settings.py`).

## Slice 2 complete — Retention (job-history only)

Owner confirmed job-records-only retention; page snapshots stay untouched
(pruning them would erase the page version-history / diff record). Shipped:

- `retention.jobs_days` validator (int 0–3650; 0 = keep forever, default) in
  `db/settings.py`.
- `prune_terminal_jobs` + `count_prunable_terminal_jobs` in `db/jobs.py`
  (terminal rows only; no FK dependents — batch form of the existing `delete_job`).
- Enforcement: startup sweep in `main.py` lifespan + `routes/retention.py`
  (`GET /api/retention/status`, `POST /api/retention/run`).
- `RetentionTab.svelte` wired into `SettingsModal.svelte`; `api/retention.ts`.
- `tests/test_retention.py` (validator range, prune/count, route) — 123 passed
  across retention + settings + jobs-batch suites.

## Still open (not this package's core scope)

The advanced knobs need net-new enforcement before they can be honest controls —
see `decisions.md` "Open (later / owner)": Tor control-port / NEWNYM circuit
refresh, crawl worker-capacity / retry policy, LLM timeouts. Do not ship those as
UI until a consumer exists. With those deferred, Wave 2's shippable scope is
complete — this package is ready to close to `archive/` once reviewed.
