# Onion Rabbithole — Implementation Plan

> Archived 2026-05-21. This is the former `docs/specs/PLAN.md`, preserved as
> implementation history. Do not use it as current source of truth; use
> `docs/reference/` and `docs/work/ACTIVE.md` instead.

---

## Decisions locked in

| Concern | Decision |
|---------|----------|
| Repo layout | Monorepo inside `rabbithole/` — `frontend/` + `backend/` |
| Python package manager | pip + venv |
| Python version | 3.12+ (3.12 or newer) |
| Backend server | **FastAPI** + Uvicorn |
| Crawler HTTP client | **aiohttp** + aiohttp-socks (SOCKS5h → Tor) |
| Database | SQLite 3 (WAL, FK on) + sqlite-vec extension |
| Graph algorithms | networkx (server-side: PageRank, betweenness, Louvain) |
| LLM integration | Ollama at `http://127.0.0.1:11434` |
| Embeddings | fastembed + sqlite-vec |
| Frontend framework | Svelte 5 (runes only — no legacy syntax) |
| Frontend language | TypeScript strict mode |
| Bundler | Vite |
| Icons | lucide-svelte |
| Graph canvas | Sigma.js (WebGL) + graphology |
| CSS | Scoped Svelte `<style>` blocks, CSS custom properties |
| Build output | Single `bundle.js` + `bundle.css` in `backend/public/` |
| Build order | **Backend-first**, then frontend |
| Testing | pytest for backend critical paths (DB, security, crawler) |
| Type hints | Typed on DB layer, route handlers, security utils |
| Dev workflow | Two terminals: backend on `:7654`, Vite on `:5173` (proxies `/api`) |

## Still to decide

- [x] Python version: 3.12+ (minimum floor; 3.13 tested on current dev host)
- [x] sqlite-vec: pip package (`sqlite-vec`) — included in requirements.txt
- [x] Dev commands: Makefile (`make dev-backend`, `make dev-frontend`)
- [x] Redirect cap: 5
- [x] Watchlist matching: **literal terms only** (glob support dropped), case-insensitive, using `pyahocorasick` for O(n) multi-term matching against `body_text_clean`; max 200 terms, max 256 chars per term; `pyahocorasick` added to `requirements.txt`
- [ ] **Cross-country + cross-language exploration**: let the operator browse as if from a chosen country (Tor exit-node selection or `ExitNodes {XX}` torrc) and read foreign-language page content in English. Translation must run on-device — no third-party translation APIs (would leak page content + operator intent). Open questions: exit-node UX (per-session vs per-circuit), translation engine (Argos / NLLB / Marian), where translated text is stored (cache vs render-only), and how language is detected.

---

## Directory structure

```
rabbithole/
├── backend/
│   ├── backend/              # Python package
│   │   ├── __init__.py
│   │   ├── main.py           # FastAPI app factory + Uvicorn entry point
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── core.py       # CrawlDB class + schema init + migrations
│   │   │   ├── nodes.py
│   │   │   ├── domains.py    # Domain profile queries (derived from nodes + entities)
│   │   │   ├── crawl.py
│   │   │   ├── graph.py
│   │   │   ├── graph_filters.py
│   │   │   ├── llm.py
│   │   │   ├── collections.py
│   │   │   ├── monitors.py
│   │   │   ├── fingerprints.py
│   │   │   ├── watchlist.py
│   │   │   ├── embed.py
│   │   │   └── settings.py
│   │   ├── crawler/
│   │   │   ├── __init__.py
│   │   │   ├── runtime.py    # Main crawl loop (aiohttp + SOCKS5h)
│   │   │   ├── queue.py      # Per-mode priority queues
│   │   │   ├── parser.py     # HTML → body_text + body_text_clean + entities
│   │   │   └── tor.py        # SOCKS5h proxy + Tor status check
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── projects.py
│   │   │   ├── graph.py
│   │   │   ├── graph_filters.py  # Hidden sub-tab — graph_filters table CRUD
│   │   │   ├── nodes.py
│   │   │   ├── domains.py        # Domain profile, pages, entities, alias rename
│   │   │   ├── crawl.py
│   │   │   ├── collections.py
│   │   │   ├── flags.py
│   │   │   ├── notes.py
│   │   │   ├── entities.py
│   │   │   ├── monitors.py
│   │   │   ├── fingerprints.py
│   │   │   ├── watchlist.py      # Watchlist CRUD (used by Focused mode + Settings)
│   │   │   ├── llm.py
│   │   │   ├── embed.py
│   │   │   ├── search.py
│   │   │   ├── seeds.py
│   │   │   ├── schedules.py
│   │   │   ├── search_engines.py
│   │   │   ├── settings.py
│   │   │   ├── edges.py
│   │   │   ├── harvest_search.py  # Search-tab SSE stream — query engines via Tor, probe uncrawled URLs
│   │   │   └── sse.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── kill_switch.py       # Shared kill-switch state (Tor down → pause all)
│   │   │   ├── llm_worker.py        # Analysis queue drain loop
│   │   │   ├── embed_worker.py      # Embedding generation loop
│   │   │   ├── monitor_daemon.py    # Uptime probe loop
│   │   │   ├── schedule_daemon.py
│   │   │   └── event_bus.py         # In-process SSE broadcast
│   │   ├── security/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py       # Session cookie, Origin validation
│   │   │   ├── net.py        # Egress allowlist, SOCKS5h enforcement
│   │   │   └── paths.py      # Project path resolution + traversal check
│   │   ├── prompts.py            # LLM prompt templates per analysis type (auditable single source)
│   │   └── export/
│   │       ├── __init__.py
│   │       ├── gexf.py
│   │       └── csv.py
│   ├── public/               # Built frontend lands here (bundle.js + bundle.css)
│   │   └── .gitkeep
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── tests/
│       ├── conftest.py
│       ├── test_db.py
│       ├── test_security.py
│       ├── test_crawler.py
│       └── test_routes.py
├── frontend/
│   ├── src/
│   │   ├── app.svelte        # Root component
│   │   ├── main.ts
│   │   ├── lib/
│   │   │   ├── api/          # Typed API client: core, types, per-domain modules, barrel
│   │   │   ├── sse.svelte.ts # Centralized SSE manager, ref-counted
│   │   │   └── stores/
│   │   │       ├── selection.svelte.ts
│   │   │       ├── services.svelte.ts
│   │   │       ├── workspace.svelte.ts
│   │   │       ├── navigation.svelte.ts
│   │   │       └── crawl.svelte.ts
│   │   ├── components/       # Shared/small components
│   │   └── views/            # Top-level layout sections
│   │       ├── AppShell.svelte
│   │       ├── GraphTab.svelte
│   │       ├── SearchTab.svelte
│   │       ├── LeftSidebar.svelte
│   │       ├── RightPanel.svelte
│   │       └── BottomPane.svelte
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── svelte.config.ts
└── docs/
    ├── reference/            # Canonical current behavior and structure
    ├── specs/                # Product/spec source material
    └── work/                 # Active and archived implementation packages
```

---

## How to run

### Makefile targets
```
make setup           # create venv, pip install, npm install
make dev-backend     # start Python server on :7654
make dev-frontend    # start Vite dev server on :5173
make build           # production frontend build → backend/public/
make test            # run pytest
```

### Manually
```bash
# Backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m backend

# Frontend (dev)
cd frontend && npm install && npm run dev

# Frontend (production build)
cd frontend && npm run build
```

---

## Build phases

Build order is **backend-first**. Each backend phase ends with a working, testable layer. Frontend phases begin once the API is solid.

---

### BACKEND

#### Phase B0 — CI security guards
*Build-blocking grep rules enforced from the first commit. `make lint-security` must pass before `make test` runs.*

- [x] `Makefile` target `lint-security` — fails on any match. All Python rules pass `--exclude-dir=.venv --exclude-dir=__pycache__ --exclude-dir=.pytest_cache --exclude-dir=.mypy_cache --exclude-dir=.ruff_cache` so vendored deps under `backend/.venv/` are not scanned; frontend rule passes `--exclude-dir=node_modules --exclude-dir=dist`. Rules that have legitimate test-only references (`aiohttp.ClientSession`, `socket.getaddrinfo`) scope to `backend/backend/` only — tests are allowed to verify the ban by referencing the banned symbol:
  - `grep -r --exclude-dir=.venv ... "aiohttp\.ClientSession(" backend/backend/ --include="*.py" | grep -v "security/net.py"` → must be zero results
  - `grep -r --exclude-dir=node_modules ... "{@html" frontend/src/` → must be zero results
  - `grep -rE --exclude-dir=.venv ... "ssl=False|verify=False" backend/ --include="*.py"` → must be zero results
  - `grep -r --exclude-dir=.venv ... "shell=True" backend/ --include="*.py"` → must be zero results
  - `grep -r --exclude-dir=.venv ... "socket\.getaddrinfo" backend/backend/ --include="*.py"` → must be zero results
- [x] `make test` depends on `lint-security` (runs guards first, aborts if any fire)

#### Phase B1 — Project scaffold
*Nothing works yet, but the skeleton compiles and the server starts.*

- [x] `backend/` directory, `requirements.txt` with all deps
- [x] FastAPI app factory in `backend/backend/main.py`, Uvicorn entry point (`python -m backend`)
- [x] Health check route `GET /api/health` → `{"ok": true}`
- [x] Auth middleware (`security/auth.py::ApiAuthMiddleware`) — enforced on **all** `/api/*` routes (GETs, POSTs, SSE streams — no exceptions): requires a valid session cookie on every API request. Unsafe methods (`POST`, `PUT`, `PATCH`, `DELETE`) also require `Origin: http://127.0.0.1:7654`; safe methods (`GET`, `HEAD`, `OPTIONS`) skip Origin validation because browsers commonly omit it on same-origin GETs and EventSource handshakes. SSE handshake validates before the stream opens, broken auth closes the stream immediately; token comparison uses `hmac.compare_digest` (constant-time). Session token generated at startup via `secrets.token_urlsafe(32)`; issued on first `GET /` as `HttpOnly` + `SameSite=Strict` cookie.
- [x] 127.0.0.1-only binding (uvicorn `host=127.0.0.1`), `Host` header rejection — `HostHeaderMiddleware` rejects anything not in `{127.0.0.1:7654, 127.0.0.1}`
- [x] CSP header middleware (`SecurityHeadersMiddleware`) — exact directive set (no drift); also emits `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`:
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
- [x] `backend/public/` static file serving (allowlist: only `bundle.js` + `bundle.css` are read off disk; SPA fallback serves `index.html` if present, otherwise an inline stub. First HTML response sets the session cookie.)
- [x] `requirements-dev.txt`: pytest, httpx (test client), pytest-asyncio
- [x] **Tests** (`tests/test_b1_scaffold.py`, 11 cases): `/api/health` auth + Origin + cookie matrix, Host header rejection, CSP/security-headers presence on root and `/api/*`, cookie attributes (`HttpOnly`, `SameSite=Strict`), session token rotates per process.

#### Phase B2 — Database layer
*The schema that everything else depends on. Correct once, never revisit.*

- [x] `db/core.py`: `CrawlDB` class, `connect()`, WAL mode, FK enforcement
- [x] Full schema DDL: all tables from spec (nodes with integer PK, body_text_clean, monitors.enabled, entities.source, crawl_schedules.collection_id, etc.)
  - **Explicit PKs required** — these tables are missing `id` in stack.md but all API response shapes return one: `analyses`, `flags`, `monitors`, `notes`, `collections` → all need `id INTEGER PRIMARY KEY AUTOINCREMENT`
  - **`nodes.embed_excluded`** (bool, default false) — set by embed worker after 3 consecutive embed failures on the same node; skipped permanently by the worker; visible in graph as no-embed indicator
- [x] FTS5 virtual table on `body_text_clean` for keyword search
- [x] sqlite-vec extension loading + `embeddings` table
- [x] All necessary indices (nodes.domain, nodes.stub, analyses.status, etc.)
- [x] DB module split: nodes, crawl, graph, llm, collections, monitors, fingerprints, embed, settings (stubs in B2; helpers filled in B5–B8)
- [x] **Migration**: `response_headers` backfill — on schema init, if `nodes` rows already have `response_headers` JSON, unpack them into the normalized `response_headers` table (one row per header per node). Required for fingerprint cluster queries to work on existing data.
- [x] **Tests**: schema init, FK cascades, FTS5 insert/query, re-crawl header delete rule (`tests/test_b2_schema.py`, 26 cases — also covers PRAGMAs, indices, CHECK constraints, FTS5 update guard, sqlite-vec roundtrip, default settings, crash sweep, transaction nesting, JSON backfill)

#### Phase B3 — Security utilities
*Non-negotiable. Built and tested before any network code.*

- [x] `security/net.py`: `make_tor_session(target_host: str, *, proxy, timeout=None) -> aiohttp.ClientSession` — single factory for ALL outbound sessions; validates `tor.proxy` value matches loopback `socks5h://(127.0.0.1|::1):<port>` with TCP port constrained to `1-65535` before constructing (raises `ConfigError` if not); loopback allowlist for local services (Ollama, Tor probe — literal `127.0.0.1` / `::1` only, `localhost` rejected); `.onion`-only target enforcement (v3, 56-char base32 regex, optional port constrained to `1-65535`); SOCKS5h → `ProxyConnector` with `rdns=True`; NO other code may construct `aiohttp.ClientSession` directly (enforced by B0 guard, scoped to `backend/backend/`)
- [x] `security/paths.py`: project path resolution (`~/.local/share/rabbithole/projects/`), traversal validation, browser path validation:
  - Project names validated against `^[A-Za-z0-9 ._-]{1,64}$` — rejected otherwise; stored NFC-normalized; pure-dot sentinels (`.`, `..`) explicitly refused after regex
  - `HOME` validated as set, existing dir, owned by current user before any `~` expansion
  - Symlink TOCTOU: `safe_realpath_under(base, target)` confirms the canonical target starts with the canonical base; `open_under` re-validates on every open, not just at create time
  - `browser.path` must canonicalize inside one of: `~/tor-browser/`, `/opt/tor-browser/`, `/Applications/Tor Browser.app/` (canonicalized once at lookup time; Windows desktop path documented but not active on the Linux host)
  - validated as a regular file (lstat refuses a symlink at the final component, even if its realpath sits inside the allowlist) with executable bit at save time AND at launch time (TOCTOU guard)
  - launched as `Popen([browser_path, "--", url])` — `--` separator forces end-of-options; URL pre-validated as `http(s)://[a-z2-7]{56}\.onion(?::\d+)?…`; stdio attached to `/dev/null`, `close_fds=True`
  - explicit minimal env passed to `Popen` (PATH/LANG/LC_ALL fixed); `DISPLAY` forwarded only if it matches `^:\d+(\.\d+)?$`; `XAUTHORITY` only if non-symlink regular file; `WAYLAND_DISPLAY`/`XDG_RUNTIME_DIR` forwarded under matching rules
- [x] `security/auth.py`: random in-memory session token, `HttpOnly` + `SameSite=Strict`, unsafe-method Origin validator (127.0.0.1 only, rejects localhost) — landed in B1, unchanged in B3
- [x] **File permissions** (enforced in `security/paths.py`):
  - Project root directories created with `0o700` via `create_project_root` (idempotent; re-asserts on existing dirs)
  - `write_sensitive_file` opens with `O_NOFOLLOW` + mode `0o600`, re-asserts via `fchmod` after the umask-affected create; refuses to write through a symlink
  - `secure_temp_file` creates `0o600` temp files (default location under `projects_base()`) and unlinks on exit
- [x] **Tests** (`tests/test_b3_security.py`): tor.proxy validator (accept / reject matrix incl. `socks5://`, `localhost`, non-loopback, missing port, port `0`, and out-of-range ports); onion host + URL regex coverage including port range; `is_loopback_host("localhost") is False` (DNS-rebind defense); `make_tor_session` returns `TCPConnector` for loopback and `ProxyConnector` for `.onion`, rejects clearnet, rejects non-loopback proxy at construction; project name regex incl. `..`/slash/control/length; NFC normalization sanity; `HOME` validation; `safe_realpath_under` rejects symlink-out; `validate_db_relpath` rejects final-component symlinks before realpath resolution; `create_project_root` mode is `0o700` and idempotent; `open_under` reads through canonical path; browser validator accepts allowlisted exec, rejects missing/non-exec/dir/outside-allowlist/symlink; `launch_browser` calls `Popen([path, "--", url])` with the documented minimal env and `shell` not set; **TOCTOU**: swap exec for symlink between save and launch → `PathError`; `write_sensitive_file` mode is `0o600` and refuses symlink target; `secure_temp_file` is `0o600` and auto-deletes; `put_setting` round-trips valid `tor.proxy`, rejects bad proxy (round-trip default unchanged), rejects unknown key; autouse fixture in `conftest.py` patches `socket.getaddrinfo` to raise — proves any direct DNS call from backend code blows up the suite

#### Phase B4 — Project management + settings
*Enables multi-project support. Needed before any route can touch a DB.*

- [x] `projects.json` registry: list, create, switch, delete
- [x] `GET /api/projects`, `POST /api/projects`, `POST /api/project/switch`, `DELETE /api/projects/:id`
- [x] Per-request DB injection (active project's DB attached to request state)
- [x] `GET/PUT /api/settings/:key` — project-scoped settings read/write; validation via `db/settings.py::SETTING_VALIDATORS: dict[str, Callable[[Any], Any]]` dispatch table plus templated-key resolution. Unknown keys → 400 via `UnknownSettingError` (a `ValueError` subclass so the B3 contract holds). Per-key validators return the normalized value to store or raise `ValueError` (→ 400). Current validator families include:
  - `tor.proxy` — must match loopback `socks5h://(127.0.0.1|::1):<port>` with port constrained to `1-65535`
  - `tor.kill_switch` — coerced to bool
  - `browser.path` — canonicalize, basepath check (same allowlist as `security/paths.py`), regular-file + executable check
  - `browser.launch_mode` — enum: `fresh` | `reuse`
  - `embedding.model` — must appear in the fastembed model registry (lazy import + module-level cache)
  - `embedding.auto_start` — coerced to bool
  - `llm.*` — model string, loopback Ollama URL, worker auto-start, and auto-enqueue toggles
  - `graph.color`, `graph.edges`, `graph.*` overlays — enum / bool per their UI controls
  - `workspace.*` — persisted workspace tabs and active workspace
  - `search.engine.{id}.enabled` — coerced to bool; `{id}` must reference an existing `search_engines.id` (resolved at PUT time via `validators_for_key(key, db)`)
  - Workers (kill_switch, embed_worker, monitor_daemon) import `SETTING_VALIDATORS` and read settings through it so all reads pass through the same normalization
- [x] Asyncio RW lock on active DB handle — `POST /api/project/switch` acquires write lock, drains in-flight readers before swapping; all request handlers hold read lock while executing (writer-priority — new readers queue behind a pending writer so the swap doesn't starve)
- [x] **Active-crawl handling on switch**: `POST /api/project/switch` checks for a `crawls` row in `running` or `paused`; if found, returns `409` with `{error: "crawl_running", crawl_id, seed_url, pages_crawled}` and does NOT swap. Frontend confirms with the analyst ("Stop the crawl and switch?") then re-calls `POST /api/project/switch?force=true`, which marks the crawl `stopped` at the DB layer and swaps. The kill-signal broadcast that drains in-flight crawl tasks lives in B5 alongside `event_bus`.
- [x] `GET /api/stats` — header stats bar counts (domains, pages, flags, monitors)
- [x] **Tests** (`tests/test_b4_projects.py` 19 cases, `tests/test_b4_settings.py` 27 cases, `tests/test_b4_concurrency.py` 7 cases): registry CRUD + atomicity, file modes (0o600 / 0o700), traversal + absolute-path rejection, duplicate-name guard, 409 vs `?force=true` on active crawl, registry corruption → fresh empty load, RW lock writer-priority semantics, switch swaps active DB and a follow-up read sees the new file, `load_from_registry` re-attaches across process restart, every validator + the templated `search.engine.{id}.enabled` path.

#### Phase B5 — Crawler
*Populates the DB so every other route has real data.*

- [x] `crawler/tor.py`: `GET /api/tor/status` — probe Tor via SOCKS5h test connect
- [x] `crawler/parser.py`: HTML → `body_text` (raw) + `body_text_clean` (stripped) + entity extraction (email, BTC, XMR, PGP, onion, handle, blob) — regex-based, `source='crawl'`
  - `body_text_clean` normalization at write time: strip NULL bytes, strip C0 control chars (except `\t\n\r`), Unicode NFC, cap at 512 KB
  - Entity values normalization at write time: additionally strip BiDi override chars (U+202A–202E, U+2066–2069, U+200F); cap each value at 2 KB
- [x] `crawler/queue.py`: per-mode queues (Cross-site / BFS / DFS / Diverse / Focused); Focused mode loads **literal terms** from watchlist table (case-insensitive Aho-Corasick automaton built from `pyahocorasick`, rebuilt on watchlist mutation)
- [x] `crawler/runtime.py`: full async crawl loop — SOCKS5h, redirect cap + validation, 10 MB streaming size limit, timeout enforcement, watchlist Aho-Corasick literal match → auto-flag, `body_text_clean` population, stub promotion (`stub=false`, `waiting→pending` analyses)
  - **Content-Type allowlist**: parse only `text/html` and `application/xhtml+xml`; other types record status + headers but discard body, no entity extraction, no FTS row
  - **HTTPS policy**: certificate verification stays on for `.onion` https targets; verification failure logged and treated as a fetch failure — no silent downgrade or `ssl=False`
  - **Crawl edge persistence**: every discovered `<a href>` resolving to a valid `.onion` link inserts an `edges` row with `source='crawl'`, anchor text captured
  - **Crash recovery on startup**: any `crawls` row left in `running` or `paused` from a prior process is swept to `failed` with `error='process restarted'`; in-flight `crawl_nodes` rows are left intact (URLs already known to the system)
- [x] `services/kill_switch.py`: shared asyncio Event; reads `settings.tor.kill_switch` (default `true`); Tor health probed every 5 s internally (independent of the 30 s UI poll); when flag is **on** and Tor goes down, fires kill switch immediately and cancels all in-flight asyncio tasks (crawl requests, monitor probes, harvest probes) via task cancellation — not just "pauses between jobs"; when flag is **off**, only emits the banner event and lets activity continue (and fail naturally); clears on Tor reconnect; crawl loop + LLM/embed workers all await this
- [x] `routes/crawl.py`: start, stop, status (SSE), crawl history
- [x] `routes/seeds.py`: seed bookmark CRUD (`GET/POST /api/seeds`, `DELETE /api/seeds/:id`)
- [x] `routes/schedules.py`: scheduled-crawl CRUD (`GET/POST /api/schedules`, `PATCH/DELETE /api/schedules/:id`, pause/resume)
- [x] `routes/nodes.py`: node detail, stub create, reviewed toggle, analysis_excluded toggle, `PATCH /api/nodes/:id/opened` (records `opened_at`)
- [x] `routes/watchlist.py`: `GET/POST /api/watchlist`, `PUT/DELETE /api/watchlist/:id` (term ≤ 256 chars, ≤ 200 total terms)
- [x] `routes/edges.py`: create/delete analyst edges
- [x] `services/schedule_daemon.py`: fires scheduled crawls at interval
- [x] `services/event_bus.py`: in-process pub/sub for SSE broadcast
- [x] `routes/sse.py`: SSE endpoint for crawl log stream
- [x] **Tests**: redirect to non-.onion blocked, response size limit enforced, stub→crawled promotion flips waiting analyses, Aho-Corasick literal watchlist matching (case-insensitive, multi-term overlapping), non-allowlisted Content-Type → body discarded, crawl crash-recovery sweep on startup, kill-switch cancels in-flight `aiohttp` request mid-stream (not just between jobs)

#### Phase B6 — Graph API
*The frontend's most data-heavy endpoint.*

- [x] Server-side graph computation: PageRank, betweenness centrality, Louvain clusters, infrastructure clusters (shared header fingerprints), bridge detection
- [x] `GET /api/graph`: full graph response with all node fields (id, label, title_text, color, domain, depth, flag_status, is_bridge, betweenness, pagerank, cluster_id, infra_cluster_id, first_seen, is_cluster, stub, analysis_excluded, in_degree_count, out_degree_count)
- [x] **Server-side filter — `graph_filters` table only**. Nodes whose URL or title matches any term are excluded from `/api/graph`, the Domains list, fingerprint cluster expansion, and all exports (GEXF, CSV, collection JSON). This is the only filter that runs in the backend — every other graph control (max hops, show stubs, hide orphans, mutual clusters, edge mode, group-by-domain, color mode, overlays) is client-side and applied at render time by the SPA. *(Filter is honored at compute time; `routes/graph_filters.py` CRUD lands in B7.)*
- [x] `GET /api/export/gexf` — implemented via `xml.etree.ElementTree` only (no string templating); all node/edge attribute values escaped by the library
- [x] `GET /api/export/nodes-csv` — all cell values written with `csv.writer`; any value starting with `= + - @ \t \r` prefixed with `'` to neutralize spreadsheet formula injection
- [x] 15 s cache on graph computation, invalidated on any of: crawl events (new/updated node, new edge), analyst edge create/delete, `graph_filters` add/delete, `nodes.analysis_excluded` toggle, flag create/update/delete, domain alias rename

#### Phase B7 — Investigation routes
*Flags, collections, notes, monitors, fingerprints, domains.*

- [x] `routes/flags.py`: create, update (status/priority/note), delete. Also: `flag_status` joined into `db/graph.py::build_payload` (highest-priority active flag wins); `db/nodes.py::get_node` returns the active `flag` object for the right-panel Page tab.
- [x] `routes/collections.py`: CRUD, add/remove items, `GET /api/collections/:id/export?format=json|csv|gexf`. Collection-scoped LLM analysis records land with B8.
- [x] `routes/notes.py`: create, list per node, delete
- [x] `routes/monitors.py`: CRUD, enable/disable (pause/resume via PATCH `{enabled}`), last status; host-scoped list via `?host=…`
- [x] `services/monitor_daemon.py`: periodic uptime probe loop — respects kill switch; publishes `monitor.probed` SSE events for the Domain tab
- [x] `routes/fingerprints.py`: cluster query (IDF scoring), member expansion (capped at 500 rows), CSV export; header names validated against RFC 7230 token chars (`[!-9;-~]+`) at storage time via `db/fingerprints.py::insert_response_headers` (the crawler now writes headers through this helper); header values truncated at 4 KB on the way in
- [x] **Dropped:** `services/fingerprint_daemon.py` — `response_headers` only mutates during crawl, and the crawl runtime already invalidates the graph cache. No derived index exists that would need refreshing.
- [x] `routes/entities.py`: `GET /api/entities/common?node_ids=1,2,...` — shared entities across a set of nodes (≥ 2 nodes match, stubs excluded; used by cluster workspace Common tab). Per-domain entity list lives on `GET /api/domains/:host/entities`.
- [x] `routes/domains.py`: `GET /api/domains` (list), `GET /api/domains/:host` (profile + stats), `GET /api/domains/:host/pages` (cap 200, honors `graph_filters`), `GET /api/domains/:host/entities`, `PATCH /api/domains/:host` (alias rename, invalidates graph cache)
- [x] `routes/graph_filters.py`: `GET /api/graph-filters`, `POST /api/graph-filters`, `DELETE /api/graph-filters/:term` — Hidden sub-tab; caps 500 terms, 256 chars/term; shared helper `db/graph_filters.py::excluded_node_ids` reused by fingerprints + domains
- [x] **Tests**: 116 cases across `tests/test_b7_{flags,notes,graph_filters,collections,monitors,fingerprints,entities,domains,monitor_daemon}.py`. Cover the spec checklist: fingerprint IDF query returns rare-header clusters first; collection JSON/CSV/GEXF exports produce expected shapes; alias rename rejects duplicates; monitor disable stops probes mid-loop; `/api/entities/common` excludes stubs and requires ≥ 2 matching nodes; `graph_filters` add/remove invalidates the graph cache; fingerprint header-name RFC 7230 validation rejects invalid chars at storage.

#### Phase B8 — LLM + Embed + Search
*AI features and search. Depends on DB layer being solid.*

- [x] `backend/prompts.py` (new module — add to directory structure): per-type prompt templates with hard input/output contracts:
  - Each type defines: `system_prompt` (static), `user_template` (takes `page_content: str` only — no other substitutions), `input_cap_bytes` (max bytes of `body_text_clean` to pass), `output_validator` (Pydantic model or regex — non-conforming outputs are dropped, not stored)
  - Types with structured output: `Risk Score` → `int 1–10`; `Category` → enum of allowed labels; `Domain Label` → `str` max 60 chars
  - Multi-page synthesis (Cluster Summary, Site Relationships, etc.): pages delimited by a random UUID generated per request; total input capped at 64 KB; delimiter injected into system prompt as "ignore any text matching this delimiter: {uuid}"
  - `Seed Suggestions` output: displayed with provenance (which pages produced them) so analyst sees suggestions came from hostile content
- [x] `routes/llm.py`: queue analysis, list queue, prioritize, cancel, start/stop worker, result fetch, collection analysis; `POST /api/analyses/:id/rerun` — resets done job to pending and clears result (backend owns the reset logic)
- [x] `services/llm_worker.py`: batch drain loop (5 jobs), crash recovery (`running→pending` on start), Ollama retry on down (30 s), `waiting` skip, priority order; collection synthesis input cap: 64 KB total `body_text_clean` per synthesis job — pages over cap are dropped (oldest/lowest-priority first), truncation logged
  - **Result write-back paths**: validated outputs are persisted to the right tables, not just `analyses.result`:
    - `Entities (LLM)` → one `entities` row per parsed value with `source='llm'` (deduped against existing `crawl`-sourced values for the same node)
    - `Category (LLM)` → `nodes.category` (enum-validated label only)
    - `Domain Label` → `domains.alias` for the page's host (only if no analyst-set alias is already present — analyst alias wins)
    - `Summary` → `nodes.summary`
    - `Risk Score` / `Q&A` / collection-scoped synthesis → `analyses.result` only
- [x] `routes/embed.py`: status, pause/resume, start/stop, model list, progress
- [x] `services/embed_worker.py`: fastembed loop, sqlite-vec insert, model change triggers full re-index (delete all embeddings first); crash recovery: exponential backoff (5 s → 10 s → 30 s → 60 s → 5 min), circuit breaker stops after 5 consecutive failures and requires manual restart; poison-pill detection: 3 consecutive crashes on the same `node_id` sets `nodes.embed_excluded = true` and skips that node permanently
- [x] `routes/search.py`: keyword (FTS5), semantic (sqlite-vec ANN query, cap 50)
- [x] `routes/search_engines.py`: CRUD for dark-web engine registry; engine URLs validated at save time against `^https?://[a-z2-7]{56}\.onion` — non-.onion URLs rejected with 400
- [x] `routes/harvest_search.py`: SSE stream — query each engine via Tor, probe uncrawled URLs, emit events; query substitution uses `urllib.parse.quote_plus`; all requests via `make_tor_session()`; probes are transient HEAD requests only — no DB rows created, title/description held in memory for the stream session and discarded on close; analyst must explicitly "Queue Crawl" or "+ Collection" to persist anything
- [x] **Tests** (77 cases across `tests/test_b8_{prompts,llm_routes,llm_worker,embed_routes,embed_worker,search,search_engines,harvest_search}.py`): malformed model output (e.g. `Risk Score` returning "high" instead of an int) is dropped, not stored; LLM worker crash recovery flips `running` → `pending` on startup; poison-pill detection sets `embed_excluded=true` after 3 consecutive same-node failures; harvest_search probe creates zero DB rows; semantic search cap of 50 enforced; engine URL `^https?://[a-z2-7]{56}\.onion` validation rejects clearnet URLs; multi-page synthesis delimiter UUID is unique per request and present in system prompt; LLM `Entities (LLM)` write-back dedupes against existing `source='crawl'` values

#### Phase B9 — Crawl queue backend
*Durable shared crawl intake; detailed plan promoted to [`../../active/2026-05-25-durable-crawl-queue/source-spec.md`](../../active/2026-05-25-durable-crawl-queue/source-spec.md).*

- [ ] `crawl_queue` storage, migration, partial unique index for queued/running URL dedupe, and boot-time recovery for stale `running` queue rows
- [ ] Queue APIs: add/list/edit/cancel/retry rows, priority bump for "start next", and persisted `crawl.queue_paused` setting
- [ ] Sequential queue runner that preserves the current one-active-crawl rule, snapshots crawl mode/domain/collection options at enqueue time, and lazily resolves pending collection names at run time
- [ ] Repoint `services/schedule_daemon.py` so scheduled crawls insert `crawl_queue` rows with `source='schedule'` instead of invoking the crawler runtime directly
- [ ] Tests for queue creation, queued/running dedupe, sequential execution, cancellation, pause/resume, option snapshots, lazy collection find-or-create, restart recovery, and scheduled crawl queue insertion

---

### FRONTEND

Frontend starts after Phase B5 is working (real data in the DB to develop against).

#### Phase F1 — Scaffold + foundation
- [x] Vite + Svelte 5 + TypeScript project in `frontend/`
- [x] Single-bundle build: exactly one `bundle.js` + one `bundle.css` in `../backend/public/`. Vite config:
  ```ts
  // vite.config.ts
  build: {
    outDir: '../backend/public',
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
        entryFileNames: 'bundle.js',
        assetFileNames: (info) =>
          info.name?.endsWith('.css') ? 'bundle.css' : 'assets/[name][extname]',
      },
    },
  }
  ```
  CI guard: `make build` must produce exactly `bundle.js` and `bundle.css` at the top of `backend/public/` — any additional `.js`/`.css` chunk fails the build.
- [x] Vite dev proxy: `/api` → `http://127.0.0.1:7654`
- [x] CSS custom properties + global base styles (dark terminal aesthetic)
- [x] `src/lib/api/`: all UI-called endpoints typed, same-origin base path, error handling, per-domain route modules, and barrel export from `index.ts`
- [x] `src/lib/sse.svelte.ts`: ref-counted SSE manager, kill-switch hook
- [x] All stores: selection, services, workspace, navigation, crawl

#### Phase F2 — App shell
- [x] Four-pane layout (left / graph canvas / right / bottom), full viewport
- [x] Drag handles (left, right, bottom), min/max constraints, localStorage persistence
- [x] Right panel collapse toggle (◀/▶), snaps to 24 px
- [x] Header: Search + Explore tabs, stats bar, ⚙ gear icon with badge
- [x] LLM pill (start/stop, queue count badge, 15 s poll, synced with Intel) *(UI stub — worker wire-up lands with B8)*
- [x] Tor pill (30 s poll, teal/red dot)
- [x] Kill switch toggle (persisted in settings)
- [x] Tor warning banner
- [x] Project picker modal (list, create, switch, delete); on switch, handles `409 crawl_running` by showing a confirm dialog ("Stop the crawl on `<seed>` and switch?") then re-calling `POST /api/project/switch?force=true`
- [x] Toast system

#### Phase F3 — Crawl sub-tab
- [x] Seed URL input, bookmarks dropdown, save bookmark popover
- [x] Mode select (5 modes), Focused mode note/warning, Stay on domain checkbox
- [x] Add results to collection dropdown (+ New collection… inline)
- [x] Start/Stop + live status row via `crawl.status` SSE for lifecycle plus `/api/crawl/status` polling for counters
- [x] Bulk Import (paste area, parsed list with per-row states + actions)
- [x] Scheduled Crawls (add form, schedule list)

#### Phase F4 — Graph canvas

##### F4a — Canvas comes alive (landed)
- [x] Sigma.js + graphology, 15 s poll — `frontend/src/lib/pollers/graph.svelte.ts`, `frontend/src/lib/stores/graph.svelte.ts`
- [x] `getGraph` + `GraphPayload`/`GraphNode`/`GraphEdge` types + `EXPORT_GEXF/CSV` paths in `src/lib/api/graph.ts`
- [x] Hover-dim, single click → highlight + auto-expand right panel
- [x] Multi-select (Ctrl+click, `Cmd+click` on macOS, `Shift+click` alternate, Ctrl+A with > 50-node confirmation) — `frontend/src/components/graph/GraphCanvas.svelte`. Shift+drag box-select was removed: Sigma 3 owns plain drag for camera pan, and the Shift+drag fallback was confusing alongside Shift+click toggle. F4b can revisit with a dedicated camera-plugin override if needed.
- [x] Ego-focus mode (depth slider 1–3, click-to-refocus via left-click in F4a, Escape exits) — `frontend/src/components/graph/EgoFocusOverlay.svelte`
- [x] Graph toolbar: status line, pause/resume physics, Fit, Reset — `frontend/src/components/graph/GraphToolbar.svelte`
- [x] Stub render hint (filled-bg ring) + selection ring + tooltip (CSP-safe `textContent`)

**Post-walkthrough fixes folded back into F4a** (from `docs/work/archive/2026-05-20-fixes/checklist.md`):
- [x] Toolbar status dot — three states (idle teal / fetching pulse / crawl-active yellow pulse), crawl precedence (commit `79b0ec7`). Spec: checklist-fixes §1.
- [x] Ego-focus left-click re-focus — clicking another visible node while focused switches focus, preserving depth (commit `7e0e3cb`). Spec: checklist-fixes §2.
- [x] `F` keyboard shortcut for ego-focus removed — left-click is the sole entry point. Spec: checklist-fixes §3.
- [x] Kill switch FSM — three-state machine (`armed` / `tripped` / `cleared_idle`), SSE-driven, reason-aware modal on auto-trip, no auto-resume on clear (commit `79b0ec7`, `KillSwitchAlert.svelte`). Spec: checklist-fixes §6. Spec changes also propagated to `app-shell.md` (kill switch contract) and `explore-graph.md` (Resume control in graph toolbar).

##### F4b — Advanced controls (in progress)
- [x] Workspace tab bar (Global + collection tabs, + button, ✕ close) — slices 1, 2+3, 3.5, 3.6 (commits `510c9a8`, `1921f00`, `da3dac2`, `7f7ac82`); see `docs/work/archive/2026-05-20-f4b-toolbar-modals/changes.md`.
- [ ] Node rendering: full color modes shipped (Domain / Cluster / Depth / Category / Infra), flagged borders shipped as a real coloured ring via `@sigma/node-border` (preserves the active colour mode fill). **Dashed stub stroke** *(deferred — see checklist-fixes §4; stubs now render as size-2.5 dots in a halo around their parent, which already delivers the "stubs recede / collapse-to-parent" intent — a dashed outline is no longer load-bearing)*, `analysis_excluded` ⊘ overlay *(blocked on AI Analysis — see checklist-fixes §5; node-rendering colour-tone branch already in place so the AI Analysis ship-day check is purely visual)*.
- [x] Right-click context menus (single node, multi-select, analyst edge) — handed off to shared modals under `frontend/src/components/modals/`. **Slice 1** (single-node) and **Slice 2** (multi-select) shipped 2026-05-18; **Slice 3** (analyst-edge → Delete analyst edge) shipped 2026-05-18 (commit `7ac7533`) via a parallel `edgeMenu` state + `rightClickEdge` Sigma handler. **Slice 4** (Open in Tor Browser → `POST /api/nodes/:id/open`) shipped 2026-05-18: kill-switch-gated (cached FSM, not a fresh probe — see `docs/work/archive/2026-05-20-todo/outcome.md` item 11), browser path resolved from `browser.path` setting or auto-discovered from `_BROWSER_EXEC_HINTS`. Change-browser UI deferred to the F5 Settings → Browser pane (placeholder breadcrumb in `SettingsStubModal.svelte`). See `docs/work/archive/2026-05-20-f4b-toolbar-modals/checklist.md` *Right-click context menus*. Modal-backed items (Add to Collection, Draw Edge…, Queue Analysis…, Add Monitor…) now open the shared modals — see the Toolbar/modals bullets below (shipped 2026-05-19).
- [x] Domain cluster nodes (group by domain, double-click to expand) — Slice 7 shipped 2026-05-19. `graphStore` synthesizes one `cluster:<domain>` node per multi-page domain when `graph.group_by_domain` is on; edges rewrite through the cluster (self-loops dropped, `multi:false` dedupes parallels); cluster positions seed from member centroid on collapse. Filter shelf row visible; double-click expands a cluster, double-click on a member while clustered collapses its domain back. Single/right-click on a cluster are opaque for now — cluster-specific right-click menu is a follow-up.
- [x] Graph stale-while-revalidate + diff-update — design brief archived at [`../2026-05-26-additions-triage/graph-stale-while-revalidate.md`](../2026-05-26-additions-triage/graph-stale-while-revalidate.md). **Slice 1 shipped 2026-05-19**: drag-to-move, `userPositioned` flag, `applyDiff` in-place path, focus UX shifts. **Slice 2 shipped 2026-05-19**: per-tab payload + camera cache in `workspaceSnapshots.svelte.ts` (`payload` + `camera` fields added to `Snapshot`; `cameraGetter` callback registered by `GraphCanvas` on mount); `onSwitch` calls `graphStore.applyPayload(cachedPayload)` immediately so the canvas renders the previous view while the background refresh is in flight; `consumePending()` returns `{ restored, camera }` — non-null camera snaps the renderer directly (no `animatedReset`) so the analyst's zoom survives tab switches; first-visit skeleton overlay in `GraphCanvas` shown while `showFirstVisitSkeleton && graphStore.loading`, cleared when any payload lands. **Slice 3 shipped 2026-05-19**: `workspaceSnapshots.invalidatePayloads()` clears the `payload` field (not positions) from all snapshots; called after each successful `addGraphFilter` (single-node hide and multi-select bulk hide) so a hidden node cannot reappear via the optimistic-apply path on the next tab switch. Crawl events intentionally NOT invalidated — the diff-update path handles new nodes correctly (additions don't produce wrong data on tab switch, only layout growth via diff).
- [x] Toolbar additions — shipped 2026-05-19. **Layout picker** + run-to-settle layouts (`frontend/src/lib/graph/layouts/`: `force` = ForceAtlas2 in a Web Worker, plus `radial` / `hierarchical` / `concentric` / `timeline` synchronous geometry); a layout is a transform that runs once and freezes — no perpetual physics. The spec's "Pause / Resume physics" is dropped; a contextual **Stop** button (visible only while FA2 settles) freezes the arrangement early. Layout choice persists under `settings.graph.layout`. **Draw edge** (`Spline`): ≥2 selected → batch modal, 0-1 selected → sequential canvas-pick mode (`drawEdge.svelte.ts`). **Expand to collection** (`FolderPlus`): popover with the shared `CollectionPicker` + 1/2/3 hop selector; client-side BFS (`lib/graph/expand.ts`) → batch add-items. **Export dropdown** (`Download`): GEXF / Nodes CSV. **Resume** button shipped earlier (kill-switch `cleared_idle`; checklist-fixes §6c).
- [x] Add Monitor / Queue Analysis / Collection picker / Draw analyst edge modals — shipped 2026-05-19 under `frontend/src/components/modals/` on a shared `Modal.svelte` shell; shared `CollectionPicker.svelte` extracted (this plan's backlog item "B7 collection picker reuse"). Backed by batch endpoints `POST /api/collections/{id}/items` (node_ids array) and `POST /api/analyses/batch`. Wired into the single-node menu (Add Monitor…, Queue Analysis…) and multi-select menu (Add to Collection, Draw Edge…, Queue Analysis…). *Single-node menu still missing two spec items — `Rename alias…` (inline popover, needs a domain-PATCH client) and `Clear Analyses` (needs a per-node analyses-clear endpoint); tracked as a follow-up.*

  **Parallel-agent fit (2026-05-18 decision).** The four modals are the
  one part of F4b that genuinely fits parallel agents: four independent
  files under `frontend/src/components/modals/`, no shared state between
  them, each consumed by an already-known caller (right-click menu, F6
  right panel, F7 bottom pane). One agent per modal in parallel is the
  intended pattern when this row gets picked up — see the "When parallel
  agents fit on F4b" note below.

  **When parallel agents / worktrees fit on F4b** (and when they don't):

  - *Don't* spawn parallel agents for the right-click slices themselves
    (1 / 2 / 3). Scope is small (slice 2 was ~250 lines in one file),
    all three slices share heavy state inside `GraphCanvas.svelte` (the
    `rightClickNode` handler, the `nodeMenu` discriminator, the
    `MenuSection` / `MenuItem` types, the toast + `graphPoller.refresh`
    patterns), and each slice teaches the next — slice 2's
    `mode: 'single' | 'multi'` + `buildXSections()` scaffold is exactly
    what slice 3 plugs into. Parallel agents here would collide on the
    same file and re-derive the same scaffold twice.
  - *Do* spawn parallel agents for the four shared modals when that row
    is picked up. They're four independent files with no shared state,
    each modal's contract (props in / events out) is already pinned by
    the slice-1/slice-2 disabled placeholders and the F6/F7 callers.
    One agent per modal, all four in flight, then one integration pass
    to wire them into the disabled rows in `GraphCanvas.svelte`.
  - *A worktree* (not a long-lived agent) fits one specific thing on
    F4b: the FA2-vs-radial layout selector (`docs/work/archive/2026-05-20-todo/outcome.md` item 9). It's
    a self-contained UI + store change with a real risk of "throw it
    away if it doesn't feel right" — exactly the case a disposable
    worktree exists for.
  - *Ultrareview / Explore agent* fits **after** all three right-click
    slices land, to audit the menu surface end-to-end against
    `docs/specs/explore-graph.md:117-166`. That's read-heavy
    cross-file review work — the agent's protected context is the win.
  - *Rule of thumb:* an agent earns its cold-start cost when the work
    is genuinely parallel (independent files, no shared scaffold) or
    genuinely long-running (minutes of grinding you can parallel-work
    against). The right-click slices are neither — they're
    seconds-of-tool-call edits on one shared file.
- [x] **Client-side filters over `/api/graph` data** — filter shelf (commit `54f62df`) + flagged-borders ring + isolate-on-selection (this slice). Shipped controls: max hops, show stubs, hide orphans, mutual-only, edge mode (All / cross-site / same-site), show-all-edges vs dedup-per-domain, colour mode (Domain / Cluster / Depth / Category / Infra), overlays (flagged borders as real ring, isolate as hover+selection snap-dim, bridge highlight with betweenness + in-degree thresholds). Each setting persists under `settings.graph.*` and rehydrates on reload; toggling any control re-renders from the already-fetched `/api/graph` payload. The only server-side graph filter remains the `graph_filters` table (Hidden sub-tab). **Group-by-domain** is the one shelf control still hidden; it pairs with the cluster rendering in the Domain cluster nodes bullet above (Slice 7).
- [x] **2026-05-19 browser-test follow-ups** — closed out 2026-05-20. Domain colour mode, Category-mode greying, and workspace-tab persistence had already shipped in earlier commits; the remaining three items landed this pass. **(1) Flag model:** `status` is now a 5-state lifecycle (`pending → flagged → investigating → done`, plus `dismissed`) and a new `flags.source` column records provenance (`watchlist` vs `analyst`), decoupling lifecycle from origin. FK-safe `flags`-table rebuild migration in `db/core.py::_migrate_flags_table` (backfills `source` from the `watchlist:` note prefix). Graph flag ring is 3-tone by status; the single-node right-click menu offers `Flag — High/Medium/Low` and writes `flagged` (an analyst flag is a confirmation, not the watchlist's `pending`). `done`/`dismissed` have no UI yet — tracked in `docs/work/archive/2026-05-20-todo/outcome.md` item 12. **(2) Infra cluster:** `db/graph.py` normalizes Content-Security-Policy (sorts directives, strips per-request nonces) so equivalent policies cluster together; `infra_cluster_id` stays a readable signature (not hashed — it is exported to CSV/GEXF); the frontend `infra_cluster_id` type was corrected `number` → `string`. **(3) Escape:** `GraphCanvas` `onKey` now handles `Escape` ahead of the form-control guard so it always exits ego-focus. See `docs/work/archive/2026-05-20-f4b-toolbar-modals/checklist.md` for the per-item decision trail.

#### Phase F5 — Left pane (Search + Intel + Settings)
- [ ] Search sub-tab: debounced input, Keyword/Semantic toggle, result rows, right-click menu
- [ ] Intel sub-tab: LLM service section, Analyse section, Embedding section, Collection Analysis section, collapse state persisted
- [ ] Settings modal: Graph / Engines / Watchlist / Browser / Embedding tabs

#### Phase F6 — Right panel
- [ ] Collapse/expand, no-selection placeholder, stub simplified state
- [ ] Page tab: header block, collections section, flag section, details toggle, expanded block (content, entities, headers, version history, notes)
- [ ] Domain tab: profile card, sparkline, pages list, entities list, uptime monitors
- [ ] Analysis tab: analyses list, result pane, lightweight polling
- [ ] Cluster workspace (multi-select): Nodes / Q&A / Common tabs

#### Phase F7 — Bottom pane
- [ ] Header row (always visible, sub-tab buttons)
- [ ] Collection sub-tab (rename, export, delete, Crawl all uncrawled)
- [ ] Bookmarks sub-tab — view/manage saved seed bookmarks from the shared `seeds` data source; adding via graph/bottom-pane right-click **Save as Seed Bookmark** must immediately appear in the left-pane Crawl bookmarks list and this sub-tab.
- [ ] Live Crawl sub-tab (SSE log, domain filter, 200-line buffer, clickable URLs)
- [ ] Analyses sub-tab (status/type filters, 5 s poll, click → right panel)
- [ ] Domains sub-tab (domain highlight on click, visibility toggle)
- [ ] Flags sub-tab (status/priority filters)
- [ ] Fingerprints sub-tab (IDF clusters, expandable member rows, CSV export)
- [ ] Hidden sub-tab — list of active filter terms with **✕ remove per row** (calls `DELETE /api/graph-filters/:term`) + add-term input at the bottom. Removing a term immediately un-hides the matching nodes: they reappear in the graph, Domains sub-tab, Fingerprints expansion, and any subsequent export. Adding works in reverse. Cache invalidation on add/delete is handled by B6.

#### Phase F8 — Search tab
- [ ] Search bar, source selector row
- [ ] SSE result stream: crawled rows, uncrawled rows (probe state)
- [ ] Action bars: crawled (→ Graph, + Collection, Queue Analysis) + uncrawled (Queue Crawl, + Collection, Flag)
- [ ] Empty states (no engines, before search, no results, all failed)

#### Phase F9 — Crawl queue frontend
*Shared crawl intake and queue UI; detailed plan promoted to [`../../active/2026-05-25-durable-crawl-queue/source-spec.md`](../../active/2026-05-25-durable-crawl-queue/source-spec.md).*

- [ ] Refactor the Crawl sub-tab intake so manual seed entry and Bulk Import both enqueue through the same queue API; move Bulk Import into a "Paste URLs" drawer
- [ ] Add crawl queue list, status counts, pause/resume, clear completed, start-next, cancel/remove, retry failed, and queued-row mode/collection edits
- [ ] Standardise **Queue Crawl** versus **Send to Crawl** actions across graph menus, search results, right panel entities, collection views, bottom-pane lists, and bookmarks
- [ ] Update collection/bottom-pane/search/graph/right-panel surfaces to enqueue silently with source metadata and confirming queue toasts
- [ ] Keep the single manual URL flow fast: Start enqueues, then the idle runner picks it up immediately unless the queue is paused

---

## Key constants (from spec)

| Constant | Value |
|----------|-------|
| Backend port | 7654 |
| Vite dev port | 5173 |
| Graph refresh | 15 s poll |
| LLM pill poll | 15 s |
| Intel LLM poll | 8 s |
| Intel embed poll | 10 s |
| Tor status poll | 30 s |
| Analyses sub-tab poll | 5 s |
| Right panel analysis poll | 5 s (only while pending/running) |
| Collection synthesis poll | 4 s |
| Search debounce | 300 ms |
| Search min length | 2 chars |
| Crawl log buffer | 200 lines |
| LLM worker batch size | 5 jobs |
| LLM retry interval | 30 s |
| Redirect cap | 5 |
| Max response size | 10 MB |
| Semantic results cap | 50 |
| Domain pages cap | 200 |
| Ctrl+A confirm threshold | 50 nodes |
| Monitor interval minimum | 0.25 hours |
| Tor SOCKS5 default | socks5h://127.0.0.1:9050 |

---

## Open questions

All pre-build questions resolved. New questions added here as they come up during implementation.

### Bug review decisions (2026-05-15)

- **Issue 1: forced project switch during active crawl.** Decision: keep the force-switch path, but make it truthful. UX should show a "stopping old crawl..." progress state and complete the switch only after the in-process crawl runner has fully exited and the old DB handle is safe to close. Chosen by user during bug review interview.
- **Issue 2: deleting the active project while background work may still exist.** Decision: allow delete from the active project, but require a confirmation path that explains the project is active and that background work will be stopped before removal. After active-project delete, keep the Project Picker modal open until the user selects or creates a new project so the app never drops into an ambiguous no-project state without an explicit next step. Chosen by user during bug review interview.
- **Issue 3: project-scoped worker auto-start and recovery after project activation.** Confirmed by delegated code review. Decision: reconcile workers on every project activation event. Scope note: plain project creation is not itself an activation event in the current code; the fix applies to startup load, project switch, active-project delete follow-up, and any future create-and-activate flow. Auto-start settings must be applied immediately for the newly active project, workers that should not be active must be idled or stopped, and project-scoped LLM recovery state must be reset so stale `running` jobs in the newly active project are repaired.
- **Issue 4: placeholder tabs across left/right/bottom panes.** Cleared from bug review. User confirmed the frontend is still actively being implemented, so these placeholders are intentional work-in-progress and should not be treated as current defects. Revisit only if they remain exposed at ship time without clearer availability states.
- **Issue 5: `crawl.status` SSE counters.** Decision: make this the first priority for the next implementation session. Unify crawl lifecycle state and counter updates by including the counter trio in the `crawl.status` SSE payload, then remove the extra polling path so the crawl UI reads from one live contract.

---

## Backlog (post-phase follow-ups)

Small enhancements deferred from the phase that surfaced them. Pull into a phase or land as a standalone PR when convenient.

- **Project picker — purge DB on delete.** `DELETE /api/projects/:id` should accept `?purge=true` to also unlink `<path>.db`, `<path>.db-wal`, `<path>.db-shm` after canonicalising under the projects base (reuse `safe_realpath_under` + lstat-no-symlink at the final component). Confirm dialog gets an "Also delete DB file" checkbox. Surfaced during F2.

- ~~**B7 collections — absorb F3's minimal endpoints.**~~ *Resolved in B7c (2026-05-15)*: PATCH/DELETE + item add/remove + JSON/CSV/GEXF export shipped in `routes/collections.py`; `tests/test_f3_collections.py` migrated into `tests/test_b7_collections.py` and the F3 file deleted. Collection-scoped LLM analysis records still owed by B8.

- **B7 collection picker reuse.** F3's bulk-import + control-row collection dropdowns inline the "+ New collection…" UX. The bottom-pane Collections sub-tab (F7) and graph Collection picker modal (F4) will need the same UI. Extract into a shared `CollectionPicker.svelte` no later than F7. Surfaced during F3.

- **`crawl.status` SSE counters.** F3 polls `/api/crawl/status` every 2 s while running (`frontend/src/lib/pollers/crawlStatus.svelte.ts`) because `crawl.status` SSE envelopes don't carry the counter trio. When B8 or later adds more SSE-driven UI, fold counters into the `crawl.status` payload and delete the poller in one cut. Surfaced during F3.

- **`POST /api/nodes/lookup` GET variant.** F3 needs the batch endpoint, but B7 right-panel "lookup by URL" flows may benefit from a single-URL GET variant. Add when B7 makes the case. Surfaced during F3.

- **Bookmarks bottom-pane sub-tab (F7 follow-up).** Folded into Phase F7. Add a `Bookmarks` tab to the bottom pane as a dedicated place to view and manage saved bookmarks. Intent: keep bookmark access available without leaving the main workspace; treat as a bottom-pane feature, not a sidebar-only control. Open/rename-label/delete/organize actions; stays in sync with the saved-seed/bookmark data source and the left-pane Crawl bookmark list. Surfaced May 11 (was `docs/bookmark-tab-note.md`, folded in here); sync clause tightened May 19.

### Codex review carry-over

Compact carry-over from the original Codex review questionnaire (deleted 2026-05-15). Items are current unless marked resolved.

- ~~**Project DB symlink validation (Codex Sec 1).**~~ *Resolved*: `validate_db_relpath` now lstat-checks the user-supplied final component before realpath can resolve a symlink away, and `tests/test_b3_security.py` covers same-base and absolute symlink pivots.

- ~~**Port range validators (Codex Sec 3).**~~ *Resolved*: `security/net.py` uses a shared `1-65535` port regex for onion URLs, Tor proxy URLs, and Ollama URLs; tests reject port `0`, `65536`, and `99999`.

- **`CrawlDB` read helpers (Codex 2).** ~132 direct `db._lock` / `db._conn` accesses across `db/*`, `routes/*`, and `services/*`. Add a thin `CrawlDB.read_one` / `read_all` (or named query helpers) and migrate simple reads. Keep the multi-statement reads that intentionally hold one lock as-is.

- **Unify per-node and collection LLM queues (Codex 3, deferred).** `analyses` and `collection_analyses` duplicate schema, worker logic, and route shapes. Merging them is a larger schema/API migration — leave until B8 follow-up work is otherwise quiet.

- **Shared worker control route helper (Codex 4).** `routes/llm.py` and `routes/embed.py` repeat the worker start/stop/pause/resume contract. Extract a small shared helper or base router after the lifecycle contract is reviewed (start/stop/pause/resume/status payload shape).

- **Centralise router imports (Codex 5).** `main.py` imports 24 route modules and explicitly includes 24 routers. Move the ordered tuple to `routes/__init__.py` and loop over it in `main.py`. Preserve order; SPA catch-all stays last.

- **Tiny API error helpers (Codex 6).** Add `api_error` / `not_found` / `bad_request` helpers and migrate the repeated `JSONResponse({"error": ...}, status_code=...)` cases. Preserve exact existing JSON shapes — no global exception framework.

- **Shared UTC timestamp helper (Codex 7).** `_now_iso()` is duplicated in 7 modules. Add one `now_utc_iso()` (e.g. `backend/util.py`) with `timespec="seconds"` and migrate; leave daemon clock-injection patterns alone.
