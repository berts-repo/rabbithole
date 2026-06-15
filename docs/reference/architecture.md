# Architecture

Onion Rabbithole is a local single-user web application. A FastAPI backend
runs on loopback, serves the frontend in production, owns a single active
SQLite project database, and performs crawler, graph, search, embedding, and
analysis work.

## Process Shape

```text
Browser UI
  |
  | same-origin /api/* fetch + SSE
  v
FastAPI backend on 127.0.0.1:7654
  |
  | active project DB handle
  v
SQLite project database
```

In development, Vite serves the frontend on `127.0.0.1:5173` and proxies API
requests to the backend. In production, the backend serves `backend/public`.

## Backend Startup

`backend/backend/main.py` creates the FastAPI app and process-level services.
During lifespan startup it:

1. Reattaches to the last active project from the project registry if possible.
2. Starts the kill switch.
3. Starts the schedule and monitor daemons.
4. Starts the embedding worker if `embedding.auto_start` is enabled.
5. Starts the LLM worker if `llm.auto_start` is enabled.

Shutdown stops workers and daemons, stops any in-flight crawl, and closes the
active project DB.

## Project Model

Only one project is active in a backend process at a time. The active project
state lives in `services/project_state.py` and contains:

- active project id
- active `CrawlDB` handle
- graph cache
- writer-priority async read/write lock

DB-touching routes acquire a read lock through `routes/deps.py`. Project
creation, deletion, and switching take the write lock so the active DB cannot
be swapped while requests are using it.

## Request Flow

Typical API request flow:

```text
Frontend component/store
  -> frontend/src/lib/api/
  -> FastAPI route in backend/backend/routes/
  -> get_active_db dependency when project data is needed
  -> backend/backend/db/* helper and/or backend/backend/services/* service
  -> JSON response
```

Route modules should handle HTTP concerns. DB modules should own SQL. Services
should own long-running process behavior and cross-route state.

## Crawler Flow

Crawler work is coordinated by `crawler/runtime.py`.

```text
POST /api/crawl/queue
  -> pending kind='crawl' jobs row inserted
  -> CrawlQueueRunner.try_advance() claims it (jobs.claim_next_crawl)
  -> create crawl detail row (status lives on the job)
  -> CrawlRunnerRegistry starts CrawlRunner
  -> CrawlRunner queue pops URL
  -> security.net.make_tor_session builds Tor-routed session
  -> fetch page
  -> crawler.parser parses HTML/text/entities/links
  -> db helpers persist resources/pages/page_versions, edges, findings, crawls
  -> EventBus publishes crawl events
  -> graph cache is invalidated after graph-affecting writes
```

The crawl runtime is async. It accepts injected session factories, parsers, and
clocks so tests can run without Tor or network access.

## Event And SSE Flow

`services/event_bus.py` is the in-process publish/subscribe bus. Producers
publish events to string channels such as:

- `crawl.log`
- `crawl.status`
- `crawl.page`
- `crawl.alert`
- `kill_switch.engaged`
- `kill_switch.clear`
- `kill_switch.banner`
- `watchlist.changed`

`services/sse.py` formats envelopes as Server-Sent Events. `crawl.log` has a
small ring buffer so late subscribers can replay recent crawl log entries.
Other channels are live-only.

## Graph Flow

The graph path is split between backend data/metrics and frontend rendering.

```text
GET /api/graph
  -> backend/backend/db/graph.py
  -> SQLite node/edge/domain/filter data
  -> NetworkX metrics
  -> GraphPayload JSON
  -> frontend graph store
  -> Graphology graph instance
  -> Sigma canvas renderer
```

Backend responsibilities:

- build the graph payload
- compute graph metrics
- apply persisted graph data
- export graph data as GEXF or CSV

Frontend responsibilities:

- maintain Graphology instance
- run visual layouts
- render with Sigma
- manage viewport, selection, hover, filtering, and workspace snapshots

## Search And Embedding Flow

Keyword search uses SQLite FTS5 over the current page version's
`body_text_clean` (contentless `pages_fts`, keyed per page).

Semantic search uses:

```text
EmbedWorker
  -> fastembed model
  -> sqlite-vec embeddings table
  -> /api/search/semantic
```

The embedding model defaults are stored in settings. The vector table dimension
is defined in `db/core.py` as `EMBED_DIM`.

## LLM Analysis Flow

The LLM worker is local-Ollama oriented. Analysis rows live in SQLite and are
processed by `services/llm_worker.py`.

```text
User/API queues analysis
  -> analyses / collection_analyses / cluster_analyses row + linked job
  -> LlmWorker claims work (per-node batch first, then one synthesis job
     — collection, then cluster — per idle tick)
  -> local Ollama endpoint
  -> prompt contract validation
  -> result persisted
```

Node analyses funnel through one compose path (Intel · Analyse) regardless of
the surface that initiated them; collection and cluster analyses compose in
their own sections and write to their own tables. Cluster analyses are
synthesis over a fingerprint-keyed membership snapshot (one result per
analysis), not one row per member.

LLM endpoints are validated as loopback-only by the security layer.

## Frontend Runtime Flow

`main.ts` mounts the app and, in dev mode, calls `/__session` so the backend can
set the session cookie even though Vite served the page.

`app.svelte` then:

- loads projects
- loads selected settings
- loads graph filter/layout/workspace state
- checks Tor status
- starts kill-switch, Tor, and stats pollers

The shell is a fixed grid with resizable/collapsible regions. Graph and search
are center tabs; node/domain/detail workflows are handled in the right panel.
