# Plan

## Slice 1 — surfacing tabs

Three new tab components under `frontend/src/components/modals/settings/`,
appended to `SettingsModal.svelte`'s `TABS` and `TabId` union. Every control
autosaves via `putSetting(key, value)` on change, matching `BrowserTab` /
`EmbeddingTab`. Each tab loads its keys with `getSetting(...).catch(() => null)`
and a `loaded` guard.

### TorPrivacyTab.svelte

| Control | Key | Type | Consumer |
| --- | --- | --- | --- |
| SOCKS5h proxy URL | `tor.proxy` | text, `socks5h://(127.0.0.1\|::1):<port>` | crawler runtime, kill-switch, monitor, harvest |
| Kill switch | `tor.kill_switch` | checkbox | `services/kill_switch.py` |

Plus a read-only status line stating per-onion-host Tor circuit isolation is
always on (enforced in `security/net.py` via SOCKS auth keyed on the onion
host) — informational, not a toggle. Control-port / NEWNYM circuit refresh is
**not** built: no control-port capability exists in the backend; that is
enforcement-slice work, noted in `decisions.md`.

### CrawlQueueTab.svelte

| Control | Key | Type | Consumer |
| --- | --- | --- | --- |
| Pacing profile | `crawl.pacing` | select fast/polite/stealth | `crawler/runtime.py` |
| Pause queue dispatch | `crawl.queue_paused` | checkbox | `services/crawl_queue_runner.py` |

Worker capacity / retry policy / scheduled-crawl defaults are deferred: no
settings consumer exists for them today (retry is manual via
`POST /api/jobs/{id}/retry`). Noted in `decisions.md`.

### LlmOllamaTab.svelte

| Control | Key | Type | Consumer |
| --- | --- | --- | --- |
| Ollama endpoint | `llm.ollama_url` | text, `http://(127.0.0.1\|::1):<port>` | `services/llm_worker.py` |
| Default model | `llm.model` | text (free string per validator) | `routes/llm.py`, `services/llm_worker.py` |
| Worker batch size | `llm.batch_size` | number 1–50 | `services/llm_worker.py` |
| Auto-start worker | `llm.auto_start` | checkbox | `main.py` |

`llm.model` is a free-text input — there is no installed-models endpoint and the
backend validator is a plain non-empty string check (Ollama tags vary widely).
Timeouts / extra concurrency knobs beyond batch size have no consumer and are
deferred.

## Slice 2 — Retention (separate delivery)

New keys + a pruning pass. Out of scope for the first commit; see
`decisions.md` open items.
