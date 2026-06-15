# Backend Structure

The backend is a FastAPI app backed by a single active SQLite project database.
The app is local-first: it binds to `127.0.0.1:7654`, serves the built frontend,
and exposes JSON/SSE routes under `/api/*`.

## Entrypoints

| File | Role |
| --- | --- |
| `backend/backend/__main__.py` | Runs the backend package as a module. |
| `backend/backend/main.py` | Creates the FastAPI app, registers middleware and routers, owns lifespan startup/shutdown, and serves the SPA. |

`create_app()` initializes process state on `app.state`:

- `session`
- `project_state`
- `event_bus`
- `kill_switch`
- `crawl_runners`
- `crawl_queue_runner`
- `monitor_daemon`
- `embed_worker`
- `llm_worker`

The lifespan hook reloads the last active project, starts daemons/workers as
settings allow, and stops workers/crawls before closing the DB on shutdown.

## Route Layer

Route modules live in `backend/backend/routes/`. They define concrete API
surfaces and should stay close to HTTP concerns: request models, dependency
injection, status codes, and response shaping.

Important route groups:

| Module | API Area |
| --- | --- |
| `projects.py` | Project registry, project creation, active project switching/deletion. |
| `settings.py` | Per-project settings. |
| `stats.py` | Header/sidebar summary counts. |
| `sse.py` | Tor status/probe and kill-switch SSE control stream. |
| `crawl.py` | Crawl start/stop/status/history/log/events. |
| `crawl_queue.py` | Crawl enqueue only (`POST /api/crawl/queue`). List/edit/cancel/retry/SSE for crawl work moved onto `jobs.py`. |
| `jobs.py` | Unified Activity API over the `jobs` table — list/get/cancel/retry/pause/resume/batch + SSE stream, across every job kind. |
| `seeds.py`, `schedules.py`, `watchlist.py` | Crawl inputs and recurring crawl configuration. |
| `nodes.py`, `edges.py` | Resource lookup/detail/open/review state and analyst edges. |
| `collections.py` | Collections, collection membership, and collection export. |
| `graph.py`, `graph_filters.py` | Graph payload, graph exports, and graph filter terms. |
| `flags.py`, `notes.py`, `domains.py`, `entities.py`, `fingerprints.py` | Analyst enrichment and graph sidebar data. |
| `embed.py`, `search.py` | Embedding worker controls and keyword/semantic search. |
| `llm.py` | LLM analysis queue and worker controls — per-resource, collection-synthesis, and cluster-synthesis analyses (`/api/clusters/analyses` keyed by membership fingerprint), plus a load/capacity block on `/api/llm/status`. |
| `prompt_templates.py` | Analyzer prompt-template CRUD (`/api/prompts`; DELETE refuses built-ins, hide instead). |
| `auto_rules.py` | Auto-analysis rule CRUD (`/api/auto-analysis-rules`). |
| `monitors.py` | Uptime monitors. |
| `search_engines.py`, `harvest_search.py` | Search-engine configuration and onion discovery. |

Routes that need the active project DB use `Depends(get_active_db)` from
`routes/deps.py`. That dependency acquires a read lock for the request and
returns `409 {"error":"no_active_project"}` when no project is active.

## Database Layer

Database modules live in `backend/backend/db/`.

`db/core.py` is the owner of:

- the `sqlite3.Connection`
- SQLite PRAGMAs
- `sqlite-vec` loading
- schema creation
- FTS5 setup
- vec0 virtual table setup
- default settings
- crash recovery for stale crawls
- the reentrant transaction context manager

Sibling modules own table-specific operations. The old `db/nodes.py` is split
into `db/resources.py` (URL identity + `state` machine), `db/pages.py` (1:1 page
state) and `db/page_versions.py` (versioning + crawl-write). `db/graph.py`
builds graph payloads, `db/embed.py` serializes vectors, and `db/settings.py`
validates settings.

All background work is tracked in one `jobs` table owned by `db/jobs.py`
(create, claim, status transitions, list, cancel). It replaced the old
`crawl_queue` table; the schedule-daemon "when did this schedule last intend to
fire?" lookup now reads schedule-sourced crawl jobs by `created_at`.

The analysis-intel tables add `db/prompt_templates.py` (template CRUD + built-in
seeding) and `db/auto_rules.py` (auto-analysis rules + crawl-rule seeding).
`db/llm.py` owns the cluster fingerprint helper (`compute_fingerprint`) and the
`cluster_analyses` enqueue/claim/mark helpers alongside the per-resource and
collection ones.

## Services

Service modules live in `backend/backend/services/`.

| Module | Role |
| --- | --- |
| `project_state.py` | Active DB handle, active project id, graph cache, and writer-priority async RW lock. |
| `registry.py` | Project registry file load/save helpers. |
| `event_bus.py` | In-process pub/sub for SSE fan-out and crawl log replay. |
| `sse.py` | Shared SSE framing and channel fan-in helpers. |
| `graph_cache.py` | Cached graph payload state invalidated by graph-affecting writes. |
| `kill_switch.py` | Tor-health kill switch state and crawl cancellation signaling. |
| `crawl_queue_runner.py` | Schedule producer + one-at-a-time dispatcher over the `jobs` table. Each safety tick first produces a pending `kind='crawl'` job for any schedule whose `interval_hours` has elapsed, then `try_advance` claims the next pending crawl job (`jobs.claim_next_crawl`) and starts a crawl when capacity frees up. The producer step is never gated by the kill switch or the queue-pause flag — those are dispatch gates only (audit-trail item 4). |
| `monitor_daemon.py` | Periodic monitor probing. |
| `embed_worker.py` | Embedding model loading and vector generation. |
| `llm_worker.py` | Local Ollama-backed analysis queue processing. Each tick claims per-node jobs first (interactive queue), then at most one synthesis job — collection, then cluster — per tick. Cluster jobs read the membership snapshot off the claimed row, concatenate member page bodies, and render a single multi-page synthesis (Cluster Q&A threads the analyst question into the prompt). Honors the `llm.batch_size` concurrency setting. |

## Crawler

Crawler modules live in `backend/backend/crawler/`.

| Module | Role |
| --- | --- |
| `runtime.py` | Async crawl runner and active crawl registry. |
| `frontier.py` | Per-crawl frontier — link expansion modes (Cross-site / BFS / DFS / Diverse / Focused) and watchlist matching. In-memory per run; distinct from the cross-crawl `jobs` queue. |
| `parser.py` | HTML parsing, text cleanup, link/entity extraction. |
| `tor.py` | Tor reachability probing. |

The runtime fetches through `security.net.make_tor_session`, parses pages,
persists resource/page/version, finding, and edge data through DB helpers,
publishes events through `EventBus`, and invalidates graph cache when graph
data changes.

## Security Modules

Security modules live in `backend/backend/security/`.

| Module | Role |
| --- | --- |
| `auth.py` | In-memory session token, cookie name, `/api/*` auth middleware, and unsafe-method Origin checks. |
| `net.py` | Tor proxy validation, v3 onion URL validation, loopback Ollama validation, and the only allowed `aiohttp.ClientSession` constructors. |
| `paths.py` | Project path validation, safe path containment, permissions, and browser path validation. |

The Makefile security lint checks enforce several security boundaries,
including no raw `aiohttp.ClientSession` construction outside `security/net.py`.
