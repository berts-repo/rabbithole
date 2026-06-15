# Stack & Architecture Reference

Both halves are a clean rebuild: a Python/FastAPI backend in `backend/` and a Svelte 5
SPA in `frontend/src/`. The old top-level `src/` tree is reference-only — do not port
its code.

---

## Frontend

| Concern | Choice |
|---------|--------|
| Framework | **Svelte 5** — use runes (`$state`, `$derived`, `$effect`, `$props`) throughout |
| Bundler | **Vite** |
| Language | **TypeScript** — strict mode, all API response shapes typed |
| Icons | **lucide-svelte** |
| Graph canvas | **Sigma.js** (WebGL renderer) + **graphology** (graph data structure and algorithms) |
| CSS | Scoped Svelte component `<style>` blocks — no Tailwind, no external framework |

### Build output

`npm run build` must produce a single `bundle.js` and `bundle.css` in `public/`. The
Python server loads them into memory at startup — do not split into chunks.

`npm run dev` runs Vite on `:5173` with `/api` proxied to the Python backend on `:7654`.

### Visual design

Dark terminal aesthetic. Use these as CSS custom properties:

```css
--bg:      #0a0f0d;   /* near-black background */
--text:    #a8ffdb;   /* light cyan-green primary text */
--border:  #1a3a2a;   /* dark teal borders */
--accent:  #00d4aa;   /* bright cyan hover / active */
--muted:   #667;      /* secondary / muted text */
```

---

## Backend

The server is **FastAPI + Uvicorn** running on `http://127.0.0.1:7654`. All API routes are
under `/api/`. The frontend communicates via `fetch()` with same-origin cookie auth
(`crawl_token`) — no explicit auth header is needed. Real-time updates come via
**SSE** (`EventSource`). The crawler uses **aiohttp** with `aiohttp-socks` (SOCKS5h) for
all `.onion` egress; aiohttp is not the web server.

### Project registry

Projects are stored in a `projects.json` file managed by the backend server. The frontend
owns the Project Picker UI entirely. On initial load it fetches the project list; if the
list is empty or no project is active the Project Picker modal is shown. Project selection
state (last active project) is held by the server — the frontend does not use localStorage
for this.

Operations needed: list projects, create project (name + path), switch active project,
delete project from registry (does not delete the DB file). Endpoint paths are specified
in app-shell.md and match the existing backend routes.

---

## Database schema

SQLite 3 (WAL mode, foreign keys on). The tables a rebuilder needs to know about:

| Table | Key columns | Purpose |
|-------|-------------|---------|
| `nodes` | `id` (INTEGER PRIMARY KEY AUTOINCREMENT), `url` (TEXT UNIQUE NOT NULL), `title`, `domain`, `depth`, `status_code`, `category`, `summary`, `body_text`, `body_text_clean` (TEXT — HTML-stripped, used for FTS, LLM input, and content snippets; populated at crawl time), `response_headers` (JSON), `first_seen`, `last_seen`, `reviewed` (bool, default false), `analysis_excluded` (bool, default false — when true the page is skipped by the auto-queue and not shown in the Intel queue), `opened_at` (nullable — set when analyst clicks Open), `stub` (bool, default false — true when the URL was added by the analyst before being crawled; flips to false and all fields populate when the crawler visits it) | One row per known URL — crawled or analyst-added stub |
| `response_headers` | `node_id` (FK → `nodes.id`), `key`, `value` | Normalized header rows — one per header per crawled page. Populated at crawl time alongside the JSON blob on `nodes`. Exists solely to make fingerprint cluster queries fast via SQL rather than in-memory JSON parsing. On re-crawl, all existing rows for the node are deleted before inserting the new set. If added after sites are already crawled, a one-time migration unpacks the JSON blob on every existing node row to backfill this table. |
| `edges` | `from_id`, `to_id`, `anchor_text`, `source` ('crawl'\|'analyst'), `label` | Directed links between nodes |
| `entities` | `node_id` (FK → `nodes.id`), `type` (email/btc/xmr/pgp/onion/handle/blob), `value`, `source` (TEXT DEFAULT `'crawl'` — `'crawl'` for regex-extracted, `'llm'` for LLM analysis–extracted) | Extracted entities |
| `page_versions` | `node_id` (FK → `nodes.id`), `crawled_at`, `status_code` | Historical crawl snapshots per URL |
| `watchlist` | `id`, `term` | Terms auto-flagged during crawl — any node whose content contains a term gets flagged |
| `graph_filters` | `term` | Persistent graph exclusion terms (hidden nodes/domains) |
| `domains` | `host`, `alias`, `last_seen` | Per-host metadata. Counts (pages, fails, alerts, entities, flags) are computed at query time via JOIN — not stored. |
| `seeds` | `url`, `label`, `added_at` | Saved seed bookmarks — URLs the analyst wants to remember for future crawls. Not a queue. Selected individually when starting a crawl. |
| `crawls` | `id`, `seed_url`, `status` (pending/running/paused/completed/failed/stopped), `mode`, `collection_id` (nullable FK — auto-adds crawled nodes to this collection), `pages_crawled`, `pages_failed`, `pages_queued`, `pages_skipped`, `max_depth` (nullable), `started_at`, `completed_at` (nullable), `paused_at` (nullable), `error` (nullable — message if status is failed) | One row per crawl run |
| `crawl_nodes` | `crawl_id`, `node_id`, `depth` | Per-crawl depth of each node |
| `crawl_queue` | `id`, `url`, `status` (queued/running/completed/failed/cancelled/skipped), `mode`, `stay_on_domain`, `max_depth` (nullable — NULL = unlimited; default 3 applied at enqueue), `collection_id` (nullable FK), `collection_name_pending` (nullable — resolved to `collection_id` lazily on first run), `source` (manual/bulk/bookmark/collection/bottom_pane/search/graph_menu/right_pane/schedule), `priority` (int, default 0; higher runs sooner), `lookup_state` (nullable — unknown/crawled/stub), `attempts`, `error` (nullable), `created_at`, `updated_at`, `started_at` (nullable), `finished_at` (nullable), `crawl_id` (nullable FK → `crawls.id` ON DELETE SET NULL) | Durable crawl queue — canonical intake/intent log. Drained FIFO (by `priority` DESC, `created_at` ASC) by `CrawlQueueRunner`; the runner also produces schedule-fired rows from `crawl_schedules`. Partial unique index on `(url) WHERE status IN ('queued','running')` enforces dedupe. Replaces the standalone `ScheduleDaemon`. |
| `notes` | `node_id`, `body`, `created_at` | Analyst notes per URL |
| `monitors` | `url`, `label`, `interval_hours`, `last_status`, `enabled` (bool, default true — false when paused), `alert_on_change` (bool, default true), `alert_on_restore` (bool, default true), `downtime_threshold_hours` (real, default 48) | Watch monitors |
| `probes` | `monitor_id`, `checked_at`, `status_code` | Monitor check results |
| `flags` | `node_id`, `status`, `priority`, `note` | Investigation flags (post-crawl only) |
| `collections` | `name`, `description` | Named URL groups |
| `collection_items` | `collection_id`, `node_id` | Collection membership (post-crawl only) |
| `analyses` | `node_id` (FK → `nodes.id` ON DELETE CASCADE), `analysis_type`, `model`, `status` (`waiting` — stub not yet crawled, job fires on crawl; `pending` — queued and eligible to run; `running`; `done`), `result`, `question` (nullable — Q&A prompt text), `priority` (int, default 0 — higher = processed sooner; used for queue reordering), `created_at`, `updated_at` | LLM analysis records. `waiting` jobs are skipped by the worker until the node's `stub` flag clears. |
| `collection_analyses` | `id`, `collection_id`, `analysis_type`, `model`, `status`, `result`, `created_at`, `updated_at` | LLM analysis records (collection-scoped) |
| `crawl_schedules` | `url`, `label`, `interval_hours`, `mode`, `active`, `collection_id` (nullable FK → `collections.id` ON DELETE SET NULL — crawled nodes are auto-added to this collection if set) | Recurring crawl definitions |
| `search_engines` | `id`, `label`, `url` | Dark-web search engine registry (no state — enabled/disabled lives in settings) |
| `settings` | `key`, `value` | Project-scoped user preferences. Covers graph view (color, edges, filters, overlays), nodes sort, intel section collapse states, engine enabled defaults (`search.engine.{id}.enabled`), browser config (`browser.path`, `browser.launch_mode`), Tor proxy address (`tor.proxy`, default `socks5h://127.0.0.1:9050`), kill switch state (`tor.kill_switch`, default `true`). |
| `embeddings` | `node_id`, `vector` (blob), `model`, `created_at` | Page content vectors for semantic search — stored via SQLite-vec extension in the same project DB |

## Security

### Threat model

- Investigation data is sensitive.
- Crawled content is hostile and untrusted.
- Remote network egress must not bypass Tor.
- The local app is single-user and loopback-only.

### Network egress

- All non-local outbound traffic must use Tor via `socks5h://`.
- If Tor is unavailable, remote requests fail closed.
- Direct non-Tor connections are allowed only to local loopback services (`127.0.0.1`) and optional Unix sockets.
- Remote network access is limited to `.onion` targets only.

### Crawl scope and redirects

- Seed URLs must be valid `.onion` URLs over `http` or `https`.
- Discovered links are eligible only if they are valid `.onion` URLs over `http` or `https`.
- Redirects are allowed only to another valid `.onion` URL over `http` or `https`.
- Enforce a small redirect cap.
- Block and log redirects to non-`.onion` hosts or unsupported schemes.

### Response handling

- Enforce connect, read, and total request timeouts.
- Enforce a maximum decompressed response size of `10 MB`, checked while streaming.
- Parse only explicitly supported content types.
- Never execute page JavaScript or other active content.

### Hostile content storage and rendering

- Preserve raw fetched body text as evidence.
- Store cleaned or normalized text separately for search, snippets, and LLM input.
- Never treat stored HTML as trusted HTML.
- Escape or sanitize only at render time.

### Local API security

- Bind the backend to `127.0.0.1` only.
- Do not bind to `0.0.0.0`.
- Do not enable permissive CORS.
- Reject unexpected `Host` headers.
- Browser access is limited to the expected local origin.

### Session and request protection

- Use a random in-memory session cookie.
- Set `HttpOnly`.
- Set `SameSite=Strict`.
- Rotate the session on server restart.
- Require strict `Origin` validation on all state-changing requests. Accept only `http://127.0.0.1:{port}` — reject `http://localhost:{port}` (DNS-rebindable) and all other origins.
- Reject cross-origin requests by default.

### Project paths and process execution

- Each project is a user-selected directory root.
- The project database lives at a fixed path under that root.
- Arbitrary external DB paths are not supported.
- Project paths are resolved relative to `~/.local/share/rabbithole/projects/` when entered as relative paths. Absolute paths are accepted only if they resolve within `~`. All paths are canonicalized and validated to start with the resolved base before use.
- Browser paths are canonicalized and treated as data.
- External programs are launched only via direct exec with explicit argument lists.
- Never interpolate URLs or paths into shell commands.

### File permissions

- Create project root directories with restrictive permissions such as `0700`.
- Create the DB and other sensitive project files with owner-only permissions such as `0600`.
- Treat exports as sensitive by default and save them with owner-only permissions.
- Default export location is under the project root.
- Warn when exporting outside the project root.
- Temp files should be owner-only and deleted promptly.

### LLM safety

- Treat crawled page content as untrusted data, never as instructions.
- Send the model only bounded derived text needed for the task.
- Keep system instructions separate from page content.
- Model outputs are advisory only.
- Model outputs may suggest actions, but cannot directly trigger tools, network requests, or persistent state changes.
- Any state change requires explicit application logic or user approval.

### `.onion` HTTPS policy

- Valid `.onion` targets may use `http` or `https`.
- HTTPS certificate verification remains enabled.
- Verification failures are logged and treated as fetch failures.
- The crawler does not silently bypass or downgrade broken HTTPS.

### Frontend containment

- The SPA never treats crawled content as trusted HTML.
- The SPA does not load external scripts, styles, fonts, images, or frames from crawled pages.
- Serve the app with a restrictive CSP. Required directives:
  ```
  default-src 'self';
  script-src 'self';
  style-src 'self' 'unsafe-inline';
  img-src 'self' data: blob:;
  connect-src 'self';
  worker-src blob:;
  frame-ancestors 'none';
  base-uri 'self';
  ```
  `unsafe-inline` for styles is required for Svelte's scoped CSS. `data:` and `blob:` for `img-src` and `worker-src` are required for Sigma.js canvas operations and export. `frame-ancestors 'none'` prevents clickjacking.
- Full-page viewing belongs in Tor Browser, not the SPA.
