# Repository Structure

This repository contains one local web application with a Python/FastAPI
backend and a Svelte/Vite frontend. The backend serves the production frontend
bundle from `backend/public`.

## Top-Level Layout

| Path | Purpose |
| --- | --- |
| `backend/` | Python backend package, tests, requirements, and production static bundle output. |
| `frontend/` | Svelte/Vite frontend source, npm manifest, and lockfile. |
| `docs/` | Current reference docs, specs, and work packages. |
| `scripts/` | Project setup and utility scripts. |
| `CONTEXT.md` | Root project context, source-of-truth rules, hard constraints, and task read orders. |
| `AGENTS.md` | Minimal agent entrypoint that routes to `CONTEXT.md`, active work, and librarian docs. |
| `LIBRARIAN.md` | Documentation-management role and rules. |
| `Makefile` | Common setup, test, dev, build, and security-check commands. |
| `PREFLIGHT.md` | Environment prerequisites and operational notes. |
| `CLAUDE.md` | Agent-facing context from earlier workflow. Treat as context, not source code. |

## Backend Layout

| Path | Purpose |
| --- | --- |
| `backend/backend/main.py` | FastAPI app factory, middleware setup, router registration, lifespan startup/shutdown, SPA/static serving, Uvicorn entrypoint. |
| `backend/backend/routes/` | HTTP route handlers. Route modules should stay thin and call DB/service helpers. |
| `backend/backend/db/` | SQLite schema owner and table-specific data access helpers. `db/core.py` owns the connection, schema, transaction primitive, FTS, and sqlite-vec setup. |
| `backend/backend/services/` | Long-lived app services and process-level state: event bus, workers, daemons, project state, graph cache. |
| `backend/backend/crawler/` | Crawl queue, parser, Tor probe, and async crawl runtime. |
| `backend/backend/security/` | Session auth, Host/Origin checks, egress validation/session factories, and path validation. |
| `backend/backend/export/` | Export helpers for CSV and GEXF graph output. |
| `backend/backend/prompts.py` | LLM prompt contracts and validation models. |
| `backend/tests/` | Backend pytest suite. |
| `backend/public/` | Production frontend assets served by the backend. `bundle.js` and `bundle.css` are build outputs. |

## Frontend Layout

| Path | Purpose |
| --- | --- |
| `frontend/src/main.ts` | Browser entrypoint. Bootstraps the session cookie in dev and mounts the Svelte app. |
| `frontend/src/app.svelte` | App-level bootstrap effects: project load, settings load, pollers, graph filters/layout/workspace state. |
| `frontend/src/views/` | Main shell regions: app shell, sidebars, bottom pane, graph tab, search tab, right panel. |
| `frontend/src/components/` | Reusable UI components and feature components. |
| `frontend/src/components/graph/` | Graph canvas, toolbar, overlays, context menu, and graph-specific controls. |
| `frontend/src/components/crawl/` | Crawl controls, bulk import, and scheduled crawl UI. |
| `frontend/src/components/modals/` | Modal components. |
| `frontend/src/lib/api/` | Typed same-origin API client, split into core, types, and per-domain route modules. |
| `frontend/src/lib/stores/` | Svelte rune stores for UI state, graph state, services, projects, selections, and workspace state. |
| `frontend/src/lib/pollers/` | Small polling loops for crawl, graph, stats, Tor, and kill switch state. |
| `frontend/src/lib/graph/` | Graph-specific helpers and layout implementations. |
| `frontend/src/styles/global.css` | Global frontend styling. |

## Generated Or Build Output

Do not hand-edit these unless the task is explicitly about generated output:

- `backend/public/bundle.js`
- `backend/public/bundle.css`
- `backend/public/assets/`
- `backend/.venv/`
- `backend/.pytest_cache/`
- `backend/backend/**/__pycache__/`
- `frontend/node_modules/`

The production frontend build is configured in `frontend/vite.config.ts` to
write a single JS bundle and a single CSS bundle into `backend/public`.

## Documentation Layout

| Path | Purpose |
| --- | --- |
| `docs/reference/` | Canonical current truth about the app. |
| `docs/reference/features.md` | User-facing product workflow and feature map. |
| `docs/specs/` | Text/spec source material used to shape the project. |
| `docs/work/active/` | Current implementation packages and handoffs. |
| `docs/work/archive/` | Completed or deferred work packages. |

If work notes conflict with code or reference docs, treat the current code and
`docs/reference/` as authoritative.
