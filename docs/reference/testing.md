# Testing

The backend has the primary automated test suite. The frontend currently uses
Svelte/TypeScript checking and production builds as its main automated checks.

## Backend Test Setup

Backend tests live in `backend/tests/`.

Pytest configuration is in `backend/pytest.ini`:

- test path: `tests`
- file pattern: `test_*.py`
- async mode: `auto`

Run all backend tests through the Makefile:

```sh
make test
```

This runs `make lint-security` first, then `pytest`.

## Security Lint

`make lint-security` is build-blocking and checks:

- no raw `aiohttp.ClientSession(` outside `backend/backend/security/net.py`
- no Svelte `{@html}` in `frontend/src`
- no `ssl=False` or `verify=False` in backend code
- no `shell=True` in backend code
- no direct `socket.getaddrinfo` in backend code

Run it directly when touching security-sensitive code:

```sh
make lint-security
```

## Focused Backend Test Commands

From repo root:

```sh
cd backend
.venv/bin/pytest tests/test_b1_scaffold.py
.venv/bin/pytest tests/test_b2_schema.py
.venv/bin/pytest tests/test_b3_security.py
.venv/bin/pytest tests/test_b5c_runtime.py
.venv/bin/pytest tests/test_b6_graph.py
.venv/bin/pytest tests/test_b8_search.py
```

Run a single test:

```sh
cd backend
.venv/bin/pytest tests/test_b3_security.py -k origin
```

## Test Fixtures

Shared pytest fixtures live in `backend/tests/conftest.py`.

Common fixture patterns:

- temporary project DBs under pytest temp paths
- FastAPI `TestClient`
- active project state setup
- fake event bus/service state
- monkeypatched workers or expensive dependency boundaries

Many tests avoid importing or loading heavy dependencies for real. For example,
embedding-related tests may stub `fastembed` registry/model behavior.

## Async Tests

`pytest-asyncio` is configured with `asyncio_mode = auto`, so async tests can be
written directly with `async def` and awaited helpers.

Crawler, daemon, worker, SSE, and event-bus tests commonly use async fixtures or
fake async session objects.

## Frontend Checks

From `frontend/`:

```sh
npm run check
npm run build
```

`npm run check` runs `svelte-check` against `tsconfig.json`.

`npm run build` runs the production Vite build and writes output to
`backend/public`.

From repo root, prefer:

```sh
make build
```

The Makefile adds a guard that confirms the expected backend public bundle
shape.

## When To Add Tests

Add or update tests when changing:

- DB schema or constraints
- route request/response behavior
- project switching or active DB locking
- crawler queue/runtime behavior
- path, auth, or network security rules
- graph payload construction or graph-affecting writes
- embedding/search/LLM queue semantics
- frontend API contract types that reflect backend changes

For narrow UI-only changes, `npm run check` and a production build may be
enough. For shared data contracts, add backend route tests and keep
`frontend/src/lib/api/` in sync.
