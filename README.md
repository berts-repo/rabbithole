# Onion Rabbithole

A local-first dark-web OSINT workbench for journalism and research.

Rabbithole crawls onion sites through Tor, turns pages, domains, links, and
entities into a graph you can explore, and lets you search, annotate, and
analyze findings — all on your own machine. Page content and LLM analysis
never leave the host.

## What You Can Do

- **Crawl onion sites through Tor.** Cross-site, BFS, DFS, diverse, or
  focused (watchlist-driven) modes. Re-crawls produce versioned page
  snapshots.
- **Explore as a graph.** Pages, domains, links, entities, and infrastructure
  relationships rendered with Sigma + Graphology. PageRank, betweenness,
  Louvain clusters, bridges, infrastructure clusters. Multi-tab workspaces,
  ego focus, filters, domain grouping, collapse, exports.
- **Organize findings.** Collections, flags, notes, labels (presets + custom),
  reviewed state, analyst-created edges, domain aliases.
- **Search.** Local keyword search (FTS5) and semantic search (fastembed +
  sqlite-vec) over crawled text.
- **Analyze locally.** Ollama-backed summaries, risk scores, categories,
  entity extraction, Q&A, domain labels, and collection/cluster synthesis.
- **Monitor.** Scheduled crawls, uptime monitors, watchlist-driven flagging,
  content-change detection against the latest snapshot.

Everything runs against a local SQLite project database on `127.0.0.1`. No
hosted service, no telemetry, no third-party page content.

## Quick Start

Requires Python 3, Node, Tor (for crawling), and optionally Ollama (for LLM
analysis).

```bash
make setup   # one-time: venv, pip install, npm install
make dev     # backend on :7654, frontend dev server on :5173
```

Open `http://127.0.0.1:5173` in your browser.

For a production-style run:

```bash
make build   # bundles frontend into backend/public/
make test    # lint-security guards + pytest
```

## Recommended Deployment: VPN on Host, Rabbithole in a Guest VM

The recommended way to run Rabbithole is **VPN always-on on the host**, with
**Rabbithole and Tor both inside a guest VM**:

```text
Host: VPN client (always on)
  └── Guest VM
        ├── tor      (127.0.0.1:9050)
        └── rabbithole backend + browser UI (127.0.0.1:7654)
```

- Host firewall pins guest egress to the VPN interface — if VPN drops, the
  guest loses network and Tor fails closed.
- Tor runs in the guest, so the app's SOCKS target is unchanged from a
  bare-metal run.
- Take a VM snapshot before each investigation for clean rollback.
- Don't forward `:7654` to the host — open the UI in a browser inside the
  guest.

## Where To Read Next

- `CONTEXT.md` — project context, source-of-truth rules, task read orders.
- `docs/reference/` — authoritative docs for current behavior (architecture,
  data model, security model, frontend/backend structure).
- `docs/specs/` — product and UI intent.
- `docs/work/ACTIVE.md` — what's in flight. `NEXT.md` — the queue.

## Stack

Svelte 5 (runes) + TypeScript strict, Sigma.js + Graphology, FastAPI,
SQLite (FTS5 + sqlite-vec), aiohttp over Tor SOCKS5h, fastembed, local
Ollama. Single-bundle production build into `backend/public/`.
