# Onion Rabbithole

A local-first dark-web OSINT workbench for journalism and research. Crawls
onion sites through Tor, turns pages, domains, links, and entities into a
graph, and runs local keyword/semantic search and Ollama-backed analysis —
without sending page content to any third-party service.

This README is for engineers landing on the repo. End-user product intent
lives in `CONTEXT.md` and `docs/specs/`.

## Architecture at a Glance

```text
Browser UI (Svelte 5 + Sigma/Graphology)
  |  same-origin /api/* fetch + SSE
  v
FastAPI on 127.0.0.1:7654
  |  one active project at a time, writer-priority lock
  v
SQLite project DB (FTS5 + sqlite-vec)
        |
        +-- Tor SOCKS5h  ->  onion crawler
        +-- Local Ollama  ->  LLM worker
        +-- fastembed     ->  embedding worker
```

- Backend binds loopback only. All onion traffic routes through Tor; non-Tor
  egress is blocked by build-time grep guards in `make lint-security`.
- Frontend is a single-bundle build (`bundle.js` + `bundle.css`) loaded into
  memory by the backend in production. Vite proxies `/api` to `:7654` in dev.
- One project DB is active per backend process. Crawler, graph, search,
  embedding, and LLM work all read/write that DB through the same lock.

See `docs/reference/architecture.md` for the full request, crawler, graph,
search, and LLM flows.

## Stack

- **Backend:** Python, FastAPI, SQLite (FTS5, sqlite-vec), NetworkX, aiohttp
  over Tor SOCKS5h, fastembed, local Ollama.
- **Frontend:** Svelte 5 (runes only — `$state`, `$derived`, `$effect`,
  `$props`), TypeScript strict, Sigma.js + Graphology, Vite. Scoped Svelte
  `<style>` only — no Tailwind, no CSS framework.
- **Build:** single bundle emitted to `backend/public/`.

## Repo Layout

```text
backend/        FastAPI app, DB modules, services, crawler, workers, tests
frontend/      Svelte 5 + Vite app; builds to backend/public/
docs/
  reference/   Authoritative docs for current behavior (read these)
  specs/       Product/UI intent
  work/        ACTIVE.md (in flight), NEXT.md (queue), archive, proposals
CONTEXT.md     Project context, source-of-truth rules, task read orders
CLAUDE.md      Always-on stack + UI rules for AI assistants
Makefile       setup / dev / build / test / lint-security
```

Route modules handle HTTP. DB modules own SQL. Services own long-running
process behavior and cross-route state. Do not cross those seams.

## Local Development

Requires Python 3, Node, and a running Tor SOCKS proxy for live crawling.
Ollama is optional but required for LLM analysis.

```bash
make setup         # venv + pip + npm install
make dev           # backend on :7654, Vite on :5173
make build         # production bundle into backend/public/
make test          # lint-security + pytest
make lint-security # build-blocking grep guards (see below)
```

Individual targets: `make dev-backend`, `make dev-frontend`.

## Security Guardrails

`make lint-security` is build-blocking and fails the tree on:

- `aiohttp.ClientSession(` outside `backend/backend/security/net.py` —
  all HTTP must go through the Tor-routed factory.
- `ssl=False` / `verify=False` anywhere in backend.
- `shell=True` in any backend subprocess call.
- `socket.getaddrinfo` in backend (DNS leak vector).
- Raw `._conn` access outside `db/core.py` — use `db.read()` /
  `db.transaction()`.
- `{@html ...}` anywhere in the frontend.

The current threat model prioritizes privacy toward malicious onion sites
and relays. Physical/device security and at-rest encryption are deferred.
See `docs/reference/security-model.md`.

## Recommended Deployment: VPN on Host, Rabbithole in a Guest VM

The recommended way to run Rabbithole is **VPN on the host, app + Tor in a
guest VM**. The host's VPN protects your real IP from your ISP and from the
Tor guard relay; the guest provides a clean network and filesystem boundary
around the crawler.

```text
Host OS
  VPN client (always on)
  +-- Guest VM
        tor (SOCKS5h on 127.0.0.1:9050, inside the guest)
        rabbithole backend (127.0.0.1:7654, inside the guest)
        browser UI (loopback inside the guest)
```

Layout:

- **Tor runs inside the guest.** Rabbithole's SOCKS target stays
  `127.0.0.1:9050` — same as a bare-metal run. The guest's outbound traffic
  exits via the host's VPN.
- **Backend stays loopback-only inside the guest.** Do not forward `:7654`
  to the host. Open the UI in a browser inside the guest, or use the VM's
  built-in display.
- **Kill switch.** Configure the host firewall so the guest can only egress
  through the VPN interface. If the VPN drops, the guest loses network — Tor
  fails closed, the crawler stops, no clearnet leak.
- **Snapshots.** Take a clean VM snapshot before each investigation so you
  can roll back project DBs, browser state, and any incidentally cached
  artifacts.
- **DNS.** Ensure the guest does not use the host's DNS directly. Tor
  resolves via SOCKS5h; the build-time `socket.getaddrinfo` guard catches
  accidental local resolution inside the app.

The in-app guardrails (loopback bind, Tor-only egress, build-blocking grep
guards) still apply — the VM and host VPN are defense in depth, not a
replacement.

## Where To Read Next

| You're working on... | Start with |
| --- | --- |
| Backend routes / APIs | `docs/reference/architecture.md`, `backend-structure.md`, `data-model.md` |
| Crawler / Tor / privacy | `docs/reference/security-model.md`, `backend-structure.md` |
| Frontend / UI | `docs/reference/frontend-structure.md`, relevant `docs/specs/*` |
| Graph | `docs/reference/architecture.md`, `docs/specs/explore-graph.md` |
| Search / embeddings / LLM | `docs/reference/data-model.md`, relevant `docs/specs/*` |

`docs/work/ACTIVE.md` is the single pointer to what's in flight.
`docs/work/NEXT.md` is the prioritized queue. Anything under
`docs/work/archive/` is history, not current truth — if it conflicts with
the current code or `docs/reference/`, trust the code.
