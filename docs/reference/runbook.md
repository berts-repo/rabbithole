# Runbook

This is the local development and operations guide for the repo.

## Prerequisites

See `PREFLIGHT.md` for environment detail. At a minimum:

- Python 3.12 or newer
- Node/npm
- SQLite with FTS5 and loadable extension support
- Tor SOCKS proxy available at the configured `tor.proxy` for real crawls
- Optional: Ollama on loopback for LLM analysis workflows

## Bootstrap

From the repo root:

```sh
make setup
```

This runs `scripts/bootstrap.sh`, which:

- creates backend/frontend directory shells if missing
- creates `backend/.venv`
- installs backend runtime and dev requirements
- runs `npm install` in `frontend`
- checks SQLite FTS5/loadable-extension support

## Run Both Dev Servers

```sh
make dev
```

This runs `dev-backend` and `dev-frontend` together from one terminal. The two
sections below cover running each server on its own.

## Run Backend

```sh
make dev-backend
```

Backend URL:

```text
http://127.0.0.1:7654
```

The backend serves:

- `/api/*` JSON/SSE routes
- `/bundle.js` and `/bundle.css` when built
- SPA fallback for non-API paths

If the frontend has not been built, backend `/` serves a small fallback page.

## Run Frontend In Development

In another terminal:

```sh
make dev-frontend
```

Frontend dev URL:

```text
http://127.0.0.1:5173
```

Vite proxies:

- `/api/*` to `http://127.0.0.1:7654`
- `/__session` to backend `/`

The proxy injects the Origin expected by backend auth middleware.

## Build Frontend For Backend Serving

```sh
make build
```

This runs `npm run build` in `frontend` and writes:

- `backend/public/bundle.js`
- `backend/public/bundle.css`

The Makefile verifies that exactly those top-level JS/CSS files exist.

## Run Tests

Full backend test path:

```sh
make test
```

This runs security lint checks, then `pytest` under `backend/`.

Focused backend tests:

```sh
cd backend
.venv/bin/pytest tests/test_b3_security.py
.venv/bin/pytest tests/test_b6_graph.py
.venv/bin/pytest tests/test_b8_search.py
```

Frontend checks:

```sh
cd frontend
npm run check
npm run build
```

## Common Failure Modes

### `venv not set up`

Run:

```sh
make setup
```

### Backend API returns `401 unauthorized`

The browser does not have the current process session cookie. In dev, refresh
the Vite page so `frontend/src/main.ts` can call `/__session`.

### Backend API mutation returns `403 bad_origin`

The request is missing the expected Origin. Use the Vite proxy or backend-served
frontend. Raw curl/scripts need to send the cookie and the correct Origin for
unsafe methods.

### API returns `409 no_active_project`

No project is active. The frontend should open the project picker. Backend
callers need to create or switch to a project first.

### Tor crawl/probe failures

Check that Tor is running and that `tor.proxy` points at a loopback `socks5h`
proxy, usually:

```text
socks5h://127.0.0.1:9050
```

### Keyword search fails

SQLite may lack FTS5 support. Re-run `make setup` and check the SQLite sanity
output.

### Semantic search or embeddings fail

Check that `sqlite-vec` loaded successfully and that `fastembed` can load the
configured model. First model load can be slow and may download model assets.

### LLM analysis fails

Check that Ollama is running on the configured loopback URL, default:

```text
http://127.0.0.1:11434
```

Non-loopback LLM endpoints are rejected by the security layer.

## Ports

| Service | Port |
| --- | --- |
| Backend | `127.0.0.1:7654` |
| Vite frontend | `127.0.0.1:5173` |
| Default Tor SOCKS proxy | `127.0.0.1:9050` |
| Default Ollama URL | `127.0.0.1:11434` |
