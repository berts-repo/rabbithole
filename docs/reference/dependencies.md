# Dependencies

This project has a Python backend and a Svelte/Vite frontend.

Dependency sources:

- Backend runtime dependencies: `backend/requirements.txt`
- Backend development/test dependencies: `backend/requirements-dev.txt`
- Frontend direct dependencies: `frontend/package.json`
- Frontend exact resolved dependency graph: `frontend/package-lock.json`

## Backend

The backend is a FastAPI application that handles crawling, Tor-routed HTTP
egress, graph analysis, SQLite-backed storage, search, and local embeddings.

Backend requirements are range-pinned rather than lock-pinned. Installs may
resolve to newer compatible patch or minor versions unless a frozen environment
is generated for a release or deployment target.

### Runtime Dependencies

| Dependency | Version Range | Purpose |
| --- | --- | --- |
| `fastapi` | `>=0.115,<0.120` | HTTP API framework used by the main app and route modules. |
| `uvicorn[standard]` | `>=0.32,<0.36` | ASGI server used to run the FastAPI app. The `standard` extra pulls in server/runtime helpers such as `uvloop`, `httptools`, `watchfiles`, and `websockets`. |
| `aiohttp` | `>=3.10,<4.0` | Async HTTP client used by crawler/runtime code, Tor checks, monitor probes, harvest search, and LLM worker requests. |
| `aiohttp-socks` | `>=0.9,<0.11` | SOCKS proxy support for `aiohttp`, used for Tor-routed requests. |
| `pydantic` | `>=2.9,<3.0` | Request models, response/data validation, and prompt output validation. |
| `brotli` | `>=1.1,<2.0` | Brotli decompression so onion egress can advertise `Accept-Encoding: gzip, deflate, br`, matching the Tor Browser request profile in `security/net.py`. |
| `sqlite-vec` | `>=0.1.6,<0.2` | SQLite vector extension used for embedding storage and semantic search. |
| `pyahocorasick` | `>=2.1,<3.0` | Efficient multi-term matching for watchlist/crawler queue logic. |
| `beautifulsoup4` | `>=4.12,<5.0` | HTML parsing for crawled pages and search result harvesting. |
| `lxml` | `>=5.3,<6.0` | Parser backend used by BeautifulSoup. |
| `networkx` | `>=3.4,<4.0` | Graph construction and graph metric computation. |
| `scipy` | `>=1.13,<2.0` | Required by NetworkX 3.x PageRank. |
| `fastembed` | `>=0.4,<0.6` | Local embedding model support. This is a heavy dependency because it pulls ONNX Runtime and model tooling. |

### Development And Test Dependencies

`backend/requirements-dev.txt` includes all runtime dependencies via
`-r requirements.txt`, then adds:

| Dependency | Version Range | Purpose |
| --- | --- | --- |
| `pytest` | `>=8.0,<9.0` | Test runner. |
| `pytest-asyncio` | `>=0.24,<0.26` | Async test support for crawler, route, and service tests. |
| `httpx` | `>=0.27,<0.29` | HTTP transport used by FastAPI's `TestClient`. |

### Current Local Backend Environment

The checked local virtualenv currently resolves the main backend dependencies to:

| Dependency | Installed Version |
| --- | --- |
| `fastapi` | `0.119.1` |
| `uvicorn` | `0.35.0` |
| `aiohttp` | `3.13.5` |
| `aiohttp-socks` | `0.10.2` |
| `pydantic` | `2.13.4` |
| `brotli` | `1.2.0` |
| `sqlite-vec` | `0.1.9` |
| `pyahocorasick` | `2.3.1` |
| `beautifulsoup4` | `4.14.3` |
| `lxml` | `5.4.0` |
| `networkx` | `3.6.1` |
| `scipy` | `1.17.1` |
| `fastembed` | `0.5.1` |
| `pytest` | `8.4.2` |
| `pytest-asyncio` | `0.25.3` |
| `httpx` | `0.28.1` |

These installed versions are informational. The requirements files are the
source of truth unless a lockfile or frozen requirements file is added.

## Frontend

The frontend is a Svelte 5 application built with Vite. It renders and manages
an interactive graph UI using Sigma and Graphology.

Frontend dependencies are range-declared in `frontend/package.json` and exactly
resolved in `frontend/package-lock.json`.

### Runtime Dependencies

| Dependency | Declared Range | Locked Version | Purpose |
| --- | --- | --- | --- |
| `@sigma/node-border` | `^3.0.0` | `3.0.0` | Sigma node border rendering program used for graph node styling overlays. |
| `graphology` | `^0.26.0` | `0.26.0` | In-memory graph data structure used by the graph store, layouts, and renderer integration. |
| `graphology-layout-forceatlas2` | `^0.10.1` | `0.10.1` | ForceAtlas2 graph layout, including worker-based layout support. |
| `graphology-types` | `^0.24.8` | `0.24.8` | TypeScript types for Graphology attributes. |
| `lucide-svelte` | `^1.0.1` | `1.0.1` | Icon components used across buttons, panels, modals, and graph controls. |
| `sigma` | `^3.0.3` | `3.0.3` | Graph canvas renderer. |

### Development And Build Dependencies

| Dependency | Declared Range | Locked Version | Purpose |
| --- | --- | --- | --- |
| `@sveltejs/vite-plugin-svelte` | `^4.0.0` | `4.0.4` | Svelte integration for Vite and Svelte preprocessing. |
| `@tsconfig/svelte` | `^5.0.4` | `5.0.8` | Base TypeScript configuration for Svelte projects. |
| `svelte` | `^5.0.0` | `5.55.5` | UI framework and compiler. |
| `svelte-check` | `^4.0.0` | `4.4.8` | Svelte-aware type and diagnostics checker. |
| `tslib` | `^2.6.3` | `2.8.1` | TypeScript runtime helper library. |
| `typescript` | `^5.5.0` | `5.9.3` | Type checking and TypeScript compilation support. |
| `vite` | `^5.4.0` | `5.4.21` | Development server and production bundler. |

The frontend lockfile currently contains 102 package entries including
transitive dependencies.
