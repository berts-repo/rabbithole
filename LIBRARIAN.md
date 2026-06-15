# Librarian

This file defines the documentation-management rules for agents working in
`rabbithole/`. The role name is **Librarian**.

## Responsibility

When invoked for documentation management, act as the documentation steward for
the project. Find loose plans, briefs, checklists, handoffs, TODO streams, and
other documentation artifacts; classify them; move them into the right place;
and update the navigation files so the next agent can continue without asking
where context lives.

Keep project documentation accurate, navigable, and organized around the current
documentation model:

```text
CONTEXT.md            Root project context and task read-order entrypoint.
docs/reference/      What the app currently is.
docs/specs/          Text/spec source material for intended product surfaces.
docs/work/additions/ Live future feature notes and deferred capability sketches.
docs/work/proposals/ Owner-discussed directions not ready for active work.
docs/work/active/    What is being changed now.
docs/work/archive/   What was changed before.
```

Do not create loose root-level planning files. Root entrypoints such as
`CONTEXT.md`, `AGENTS.md`, and `LIBRARIAN.md` are allowed because they route to
the docs tree. New plans, checklists, handoffs, and outcomes belong under
`docs/work/`.

## Project Model

Rabbithole is a local-first dark-web OSINT workbench for journalism and
research. The product center of gravity is the graph/crawl investigation loop:
onion crawling, graph exploration, collections, flags, notes, monitors, search,
embeddings, and LLM analysis. The frontend shell supports repeated analyst
workflows; it is not a marketing site or generic SaaS app.

Documentation should preserve that framing. Security and privacy notes should
distinguish operator privacy toward malicious onion sites and relays from
physical/device security, which is currently deferred unless the owner changes
the threat model.

## Invocation Workflow

When asked to manage or clean up docs:

1. Search for loose or stale documentation:
   - root-level `*-PLAN.md`, `*-BRIEF.md`, `TODO*.md`, `CHECKLIST*.md`
   - old `docs/implementation/` paths
   - planning docs inside feature folders that should be work packages
   - references to moved docs
2. Classify each artifact:
   - current truth -> `docs/reference/`
   - prompt/spec seed material -> `docs/specs/`
   - live future feature notes and deferred sketches -> `docs/work/additions/`
   - owner-discussed cleanup/product directions that are not implementation-ready
     -> `docs/work/proposals/`
   - active project context -> `docs/work/active/YYYY-MM-DD-slug/`
   - completed/deferred history -> `docs/work/archive/YYYY-MM-DD-slug/`
3. Move files, preserving history-friendly names such as `plan.md`,
   `checklist.md`, `handoff.md`, `decisions.md`, and `outcome.md`.
4. Update `docs/work/ACTIVE.md` when the active project changes.
5. Update cross-links and run a stale-reference search before finishing.
6. Keep changes docs-only unless the owner explicitly asks for code changes.

## Read Order

Read orders are defined in `CONTEXT.md` ("Read First" and "Task Read Orders").
Point agents at `CONTEXT.md`; do not restate read orders here or in other docs.

## Active Work Rules

- `docs/work/ACTIVE.md` names the current active package, or lists multiple
  active packages when `NEXT.md` has explicitly declared them runnable in
  parallel (different code, no conflict). It reads `none` when no
  implementation package is active. Avoid more than two parallel packages —
  the limit exists to keep context navigable, not to forbid concurrency.
- `docs/work/NEXT.md` holds the prioritized queue of upcoming work. When a
  queued item is promoted to an active package, remove it from `NEXT.md` in the
  same change.
- Active packages live under `docs/work/active/YYYY-MM-DD-slug/`.
- Non-trivial active packages should include:
  - `README.md`
  - `checklist.md`
  - `handoff.md`
  - `plan.md` when there is an implementation plan
  - `decisions.md` when owner decisions are recorded
  - `outcome.md` when the work closes
- When the active project changes, update `docs/work/ACTIVE.md` in the same
  commit that creates or promotes the package.

## Archive Rules

Move completed, abandoned, or superseded work to
`docs/work/archive/YYYY-MM-DD-slug/`.

When archiving:

- Keep `README.md`, `outcome.md`, and `decisions.md` if present.
- Keep long checklists or plans only when they still explain useful context.
- Compress scratch notes into `outcome.md` before deleting or trimming them.
- Preserve user decisions and threat-model assumptions.
- Graduate any still-open "Open (later)" decisions into `docs/work/REVISIT.md`
  before archiving, so they are not buried where the read-order rules skip.

## Additions Rules

`docs/work/additions/` is an intake folder for work that has not shipped yet.
Keep it small enough that a user or agent can scan it without reading completed
history.

Use `additions/` for:

- owner-confirmed future feature notes that are not active yet
- implementation-ready specs waiting in `NEXT.md`
- explicit ideas marked `(idea)` or "future feature note"
- narrow handoffs for planned follow-up work that has not started

Do not use `additions/` as the permanent home for completed implementation
specs. When an addition is promoted and then closes:

1. Move the useful package context into `docs/work/archive/YYYY-MM-DD-slug/`.
2. Make the archive package's `README.md` and `outcome.md` the historical entry
   points.
3. Remove the full completed spec from `additions/`, or replace it with a tiny
   pointer only when stable inbound links still need a landing page.
4. Update `docs/work/additions/README.md`, `docs/work/NEXT.md`,
   `docs/work/ACTIVE.md`, and any archive read-order links in the same change.

If an addition only partially ships, keep a live additions doc only for the
remaining unshipped scope. The shipped part belongs in archive; the remaining
doc should say what is still open and link to the archived outcome.

## Reference Docs

`docs/reference/` is the canonical current-truth layer. Update it when code or
behavior changes affect:

- project features or product shape
- architecture
- backend/frontend structure
- data model
- security model
- dependencies
- runbook commands
- testing expectations

Standing maintenance obligations — recurring upkeep triggered by external events
rather than a work package, such as bumps to versions mirrored inside source
code — live in `docs/reference/maintenance.md`.

Keep `CONTEXT.md` short and stable. Update it only when project framing,
source-of-truth rules, hard constraints, or task read orders change.

Do not let implementation-history notes become the source of truth for current
behavior.

## Specs Docs

`docs/specs/` preserves original prompt/spec source material. Avoid
deleting it. If a spec is outdated, prefer adding a short note that points to
the current reference doc or archived outcome instead of rewriting the original
source intent.

Live future feature notes and deferred capability sketches belong under
`docs/work/additions/` and should be linked from `docs/work/NEXT.md` when they
are owner-confirmed follow-up work. Completed addition specs belong with their
closed work package in `docs/work/archive/`.

Owner-discussed cleanup or product directions that need more conversation before
they become active implementation packages belong under `docs/work/proposals/`.
Use this bucket for strategy-level direction documents; do not put active
package `plan.md` implementation steps there.

## Queue

`docs/work/ACTIVE.md` names the current active package. `docs/work/NEXT.md`
holds the prioritized queue of upcoming work — what to start next. Keep project
state out of this file.
