# Project Context

Rabbithole is a local-first dark-web OSINT workbench for journalism and
research. The core workflow is onion crawling through Tor, graph-based
investigation, collections, flags, notes, monitors, local search, embeddings,
and local LLM analysis.

This is an investigation tool, not a marketing site or generic SaaS app. Design
and implementation should preserve repeated analyst workflows: crawl, map,
filter, collect, flag, annotate, monitor, search, and analyze.

## Read First

For current implementation work:

1. `docs/reference/features.md`
2. `docs/work/ACTIVE.md`
3. The task-specific reference docs named in `ACTIVE.md`
4. The active package named in `ACTIVE.md`

For what to work on next:

1. `docs/work/ACTIVE.md` — what is in flight now
2. `docs/work/NEXT.md` — the prioritized queue of upcoming work

For documentation cleanup:

1. `LIBRARIAN.md`
2. `docs/work/ACTIVE.md`

For product or UI intent:

1. `docs/specs/index.md`
2. The relevant spec file under `docs/specs/`

## Source Of Truth

- Current code and `docs/reference/` are authoritative for current behavior.
- `docs/work/ACTIVE.md` is the single pointer to current active work.
- `docs/work/NEXT.md` is the prioritized queue of upcoming work.
- `docs/work/REVISIT.md` is the watch-list of things to revisit or possibly
  remove — not a build queue.
- `docs/work/active/` contains current implementation packages.
- `docs/work/archive/` is history, not current truth.
- `docs/work/proposals/` contains owner-discussed cleanup/product directions
  that are not implementation-ready yet.
- `docs/specs/` preserves source specs and intended UI behavior.
- `docs/work/additions/` contains live future feature notes and deferred
  capability sketches, not completed implementation history.
- If archived work or specs conflict with current code or `docs/reference/`,
  trust the current code and `docs/reference/`.

## Hard Constraints

- Local-first, single-user application.
- Backend binds to `127.0.0.1:7654`.
- Onion crawling must route through Tor via SOCKS5h.
- Avoid DNS leaks and non-Tor egress.
- Page content and analysis stay local; LLM work uses local Ollama.
- Preserve the current threat model: privacy toward malicious onion sites and
  relays is in scope; physical/device security is deferred unless the owner
  changes the threat model.
- Frontend is Svelte 5 with runes and TypeScript strict mode.
- Backend route modules should handle HTTP concerns; DB modules own SQL;
  services own long-running process behavior and cross-route state.
- Product UI should support dense, repeated analyst workflows rather than
  marketing presentation.

## Task Read Orders

| Task | Read |
| --- | --- |
| Backend route/API work | `docs/reference/features.md`, `docs/reference/architecture.md`, `docs/reference/backend-structure.md`, `docs/reference/data-model.md`, `docs/reference/security-model.md` |
| Crawler/Tor/privacy work | `docs/reference/features.md`, `docs/reference/security-model.md`, `docs/reference/backend-structure.md`, `docs/work/ACTIVE.md` |
| Frontend/UI work | `docs/reference/frontend-structure.md`, relevant `docs/specs/*` |
| Graph work | `docs/reference/features.md`, `docs/reference/architecture.md`, `docs/reference/frontend-structure.md`, `docs/specs/explore-graph.md` |
| Search/embedding/LLM work | `docs/reference/features.md`, `docs/reference/architecture.md`, `docs/reference/data-model.md`, relevant specs under `docs/specs/` |
| Documentation cleanup | `LIBRARIAN.md`, `docs/work/ACTIVE.md` |

## Token Rules

- Do not start by reading the archived historical build plan unless a current
  doc points to a specific section of it.
- Do not read `docs/work/archive/` unless a current doc points to a specific
  archived package.
- Keep read order short and task-specific.
- Prefer root `CONTEXT.md`, `docs/work/ACTIVE.md`, and targeted reference docs
  over broad scans of the docs tree.
- Update reference docs when current behavior changes.
- Update active package docs when implementation status changes.
