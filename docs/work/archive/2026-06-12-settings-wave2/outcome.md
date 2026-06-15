# Outcome

**Closed 2026-06-12.** Settings Wave 2 shipped its full honest scope: every
control that landed is wired to a live backend consumer. Knobs without an
enforcement consumer were deliberately deferred (graduated to
[`../../REVISIT.md`](../../REVISIT.md)) rather than shipped as dead UI.

## Shipped

**Slice 1 — surfacing tabs** (`b7b5352`). Three Settings tabs over settings keys
that already had validators + consumers but no modal home:

- `TorPrivacyTab.svelte` — `tor.proxy`, `tor.kill_switch`; per-onion circuit
  isolation shown read-only (always on by design, no off switch).
- `CrawlQueueTab.svelte` — `crawl.pacing`, `crawl.queue_paused`.
- `LlmOllamaTab.svelte` — `llm.ollama_url`, `llm.model` (free text),
  `llm.batch_size`, `llm.auto_start`.
- Wired into `SettingsModal.svelte` (`TabId`, `TABS`, render switch).

No backend change — pure UI over the existing `PUT /api/settings/{key}` autosave
seam. Gates: `npm run check` 0 errors, `npm run build` single bundle.

**Slice 2 — Retention, job-history only** (`19171dc`). Net-new vertical:

- `retention.jobs_days` validator (int 0–3650; 0 = keep forever, default) in
  `db/settings.py`.
- `prune_terminal_jobs` + `count_prunable_terminal_jobs` in `db/jobs.py`
  (terminal rows only, no FK dependents).
- Enforcement: startup sweep in `main.py` lifespan + `routes/retention.py`
  (`GET /api/retention/status`, `POST /api/retention/run`).
- `RetentionTab.svelte` + `api/retention.ts`.
- `tests/test_retention.py` — 123 passed across retention + settings + jobs-batch.

## Deferred (see REVISIT.md)

Tor control-port / NEWNYM circuit refresh, crawl worker-capacity / retry policy,
and LLM request timeouts each need a backend enforcement consumer built before
they can be honest controls. Continuous retention sweep also parked (startup +
manual button cover the current single-user, restart-frequent reality). All
carried in `REVISIT.md` so they survive this archival.

## Decisions

Preserved in [`decisions.md`](decisions.md) — most load-bearing: **no dead
controls**, **job-history-only retention** (pruning page snapshots would erase
the version-history / diff evidence record), **retention default off**.
