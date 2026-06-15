# Documentation Organization Plan

Status: implemented
Date: 2026-05-21

Goal: make project notes easy for humans to follow and predictable for agents
like Claude and Codex to navigate.

## Implemented Model

```text
docs/
  reference/      Current human-facing truth about the app.
  specs/          Text-only source specs/prompts for regenerating the app.
  work/
    ACTIVE.md     Current active package and agent read order.
    active/       Current change packages.
    archive/      Completed or deferred change packages.
```

Root-level docs are now limited to repo-wide operational or agent files:

```text
AGENTS.md
CLAUDE.md
LIBRARIAN.md
PREFLIGHT.md
```

Future feature plans, cleanup briefs, and checklists should live under
`docs/work/`.

## Project Reading

This project is a local-first dark-web OSINT workbench for journalism and
research. The current product center of gravity is the graph/crawl workflow:
onion crawling, graph exploration, collections, flags, notes, monitors, search,
embeddings, and LLM analysis. The frontend shell exists to support an analyst's
repeated investigation loop, not a public SaaS workflow.

The docs structure preserves that working context:

- `docs/reference/` is the concise current-truth layer for agents and humans
  changing code.
- `docs/specs/` keeps the original text/spec seed material because it is
  still useful for intended surfaces and rebuild prompts.
- `docs/work/` holds active implementation context, handoffs, completed phase
  history, and follow-up plans.

## Agent Entry Rules

Agents should use this reading order:

1. For implementation or debugging, start with `docs/reference/`.
2. For continuing current work, start with `docs/work/ACTIVE.md`.
3. For rebuilding the app from text specs, start with `docs/specs/`.
4. If work notes conflict with code or `docs/reference/`, trust the current code
   and `docs/reference/`.

## Work Package Rules

Use this naming format:

```text
YYYY-MM-DD-slug/
```

Minimum work package:

```text
README.md
checklist.md
```

Recommended non-trivial work package:

```text
README.md
checklist.md
handoff.md
plan.md
decisions.md
outcome.md
```

When archiving, keep the durable memory and compress the noise:

- Keep `README.md`, `outcome.md`, and `decisions.md`.
- Keep plans/checklists only if they still explain important context.
- Delete or trim scratch notes after useful information is folded into
  `outcome.md`.

## Migration Result

The migration created:

```text
docs/specs/
docs/specs/additions/
docs/work/README.md
docs/work/ACTIVE.md
docs/work/archive/2026-05-21-docs-organization/
docs/work/active/2026-05-21-crawler-privacy-cleanup/
docs/work/archive/2026-05-15-codex-bug-report/
docs/work/archive/2026-05-20-f4a/
docs/work/archive/2026-05-20-f4b-toolbar-modals/
docs/work/archive/2026-05-20-fixes/
docs/work/archive/2026-05-20-graph-frontend-refactor/
docs/work/archive/2026-05-20-todo/
```

`docs/work/ACTIVE.md` now points to crawler privacy cleanup as the next
owner-confirmed project step.

## Current Work Queue

After this documentation organization pass, the active work queue is:

1. `docs/work/active/2026-05-21-crawler-privacy-cleanup/` — implement P1
   request fingerprint, P2 per-onion-host circuit isolation, then P3 crawl
   pacing profile.
2. `docs/work/active/YYYY-MM-DD-graph-layout-selector/` — finish the open graph
   layout slice from the archived TODO: add `Domain` / `Force` layout selection,
   restore ForceAtlas2 as a selectable mode, and preserve radial/domain as the
   default.
3. `docs/work/active/YYYY-MM-DD-graph-canvas-invalidation/` — only if still
   reproducible or encountered during layout work: unify canvas refresh
   invalidation for crawl updates and cross-window freshness.
4. `docs/work/active/YYYY-MM-DD-db-access-seam/` — backend DB-access seam, after
   crawler privacy work, to keep optional at-rest encryption easy later.
5. Deferred graph refactor phases — revisit only when F5/F6/F8 scope makes graph
   UI orchestration, workspace/snapshot boundaries, or backend follow-on cleanup
   an active blocker.

## Final Policy

Use this mental model:

```text
docs/reference/      What the app currently is.
docs/specs/          The text-only source spec/prompt for regenerating the app.
docs/work/active/    What we are changing right now.
docs/work/archive/   What we changed before.
```
