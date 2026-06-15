# Documentation

Use this directory as the main map for both humans and agents.

For project context, source-of-truth rules, hard constraints, and task-specific
read orders, start with `../CONTEXT.md`.

## Current Model

| Path | Purpose |
| --- | --- |
| `reference/` | Canonical current truth about the app. Start here for implementation and debugging. |
| `security/` | Security awareness notes and accepted/deferred risk writeups that support, but do not replace, the current security model. |
| `specs/` | Original text/spec source material used to shape the app. Useful for intended product surfaces and rebuild prompts. |
| `work/additions/` | Live future feature notes and deferred capability sketches. |
| `work/proposals/` | Owner-discussed directions that are not implementation-ready yet. |
| `work/active/` | Current implementation packages and handoffs. |
| `work/archive/` | Completed or deferred work packages kept for historical context. |

For continuing active work, read `work/ACTIVE.md`; it names the relevant
reference docs and active package files for the current task.

## Reference Docs

| Doc | Purpose |
| --- | --- |
| `reference/features.md` | User-facing product workflow, current capabilities, planned work, future/deferred features, and product boundaries. |
| `reference/structure.md` | Repository map and generated-file guidance. |
| `reference/backend-structure.md` | Backend modules, service boundaries, route groups, and crawler/security layout. |
| `reference/frontend-structure.md` | Frontend entrypoints, views, components, stores, pollers, graph code, and build output. |
| `reference/architecture.md` | High-level system flow across browser, FastAPI, SQLite, crawler, graph, search, embeddings, LLM, and SSE. |
| `reference/data-model.md` | SQLite schema overview, relationships, constraints, and DB module ownership. |
| `reference/security-model.md` | Local auth, Host/Origin checks, egress rules, path validation, kill switch, and security lint guardrails. |
| `reference/dependencies.md` | Backend and frontend dependency inventory. |
| `reference/runbook.md` | Setup, run, build, test, ports, and troubleshooting. |
| `reference/testing.md` | Backend pytest, security lint, frontend checks, and when to add tests. |

## Security Notes

| Doc | Purpose |
| --- | --- |
| `security/at-rest-data-exposure.md` | Cleartext at-rest storage risk, current deferral status, future SQLCipher path, and operational mitigations. |

## Authority

When archived work notes disagree with code or `reference/`, trust the current
code and `reference/`.
