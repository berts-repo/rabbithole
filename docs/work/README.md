# Work Packages

This folder holds implementation context.

Use `../../CONTEXT.md` for project-wide context, then use `ACTIVE.md` when
continuing current work. Completed, deferred, or historical packages live under
`archive/`.

`additions/` holds live future feature notes and deferred capability sketches.
`proposals/` holds owner-discussed cleanup or product directions that are not
implementation-ready. `REVISIT.md` is a durable watch-list of things to come
back to or possibly remove — distinct from `NEXT.md` (intended work). Active
package implementation steps still live in each package as `plan.md`.

## Rules

- `ACTIVE.md` names one active package, or `none`, and its task-specific read
  order when work is active.
- `NEXT.md` names upcoming live work only; do not keep completed-work summaries
  there.
- `additions/` is future-only. When work ships, move useful context into the
  archive package and remove or shrink the addition.
- Each non-trivial package should include `README.md`, `plan.md`,
  `checklist.md`, `handoff.md`, and `outcome.md` when closing.
- Archive completed, abandoned, or superseded work after `outcome.md` captures
  durable decisions and results. When archiving, graduate any still-open
  "Open (later)" decisions into `REVISIT.md` so they are not buried in
  `archive/`.
- Do not create loose root-level planning files.
