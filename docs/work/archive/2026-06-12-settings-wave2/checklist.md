# Checklist

## Slice 1 — surfacing tabs

- [x] `TorPrivacyTab.svelte` — proxy URL + kill switch + isolation status line
- [x] `CrawlQueueTab.svelte` — pacing + queue pause
- [x] `LlmOllamaTab.svelte` — endpoint + model + batch size + auto-start
- [x] Wire all three into `SettingsModal.svelte` (`TabId`, `TABS`, render)
- [x] Typecheck (`npm run check`) + production build clean
- [x] Reference doc note in `frontend-structure.md` (tab list)

## Slice 2 — Retention (job-history only)

- [x] Owner decision: job-records only; page snapshots never pruned (would
      erase the version-history / diff record). Standalone tab. Default off.
- [x] `retention.jobs_days` validator (int 0–3650; 0 = keep forever)
- [x] `prune_terminal_jobs` + `count_prunable_terminal_jobs` in `db/jobs.py`
- [x] Enforcement: startup sweep (`main.py` lifespan) + manual
      `POST /api/retention/run`; status via `GET /api/retention/status`
- [x] `RetentionTab.svelte` wired into `SettingsModal.svelte`
- [x] `tests/test_retention.py` (validator, prune/count, route) — green
- [x] Typecheck + build clean
