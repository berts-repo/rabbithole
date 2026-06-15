# Right Pane Completion (F6)

Status: active — Phase 1 starting.
Date: 2026-05-27

The shell's right-side detail panel is currently a stub:
`frontend/src/views/RightPanel.svelte` renders the three tab buttons
(Page / Domain / Analysis) over a body that just says
`{tab} — content lands in F6`. This package builds the three single-node
tabs described in `docs/specs/right-pane.md` plus the multi-select
cluster workspace (Nodes / Q&A / Common).

Backend support is already complete — node detail, node collections,
notes, flags, reviewed/exclude toggles, domain profile + pages + entities,
domain alias rename, monitors, analyses CRUD + rerun, batch analyses,
and shared-across-nodes entities (`/api/entities/common`) all exist
from prior packages. This is a frontend-only build with no schema work.

Completing F6 also closes two surfaces deferred from earlier work:

- The Phase B right-pane single-node stub `Send to Crawl` button
  (deferred from the durable-crawl-queue package).
- The cluster workspace batch `Send to Crawl` action.

It also resolves the F7 Phase 3 follow-up note that the bottom-pane
Domains row click currently uses `selectionStore.replaceMulti(...)`
which would trip the cluster workspace once it exists — F6 must gate
the cluster trigger on something other than raw multi-count
(e.g. a `selectMode: 'cluster'`).

Source spec: `../../../specs/right-pane.md`.

## Phases

The package ships in four internal phases on `main`. See `plan.md`.

1. Shell + Page tab (header chips, reviewed/exclude toggles, summary,
   collections, flag editor, content/entities/headers/history/notes,
   stub-node simplified state with `Send to Crawl`).
2. Domain tab (profile card + sparkline + entity-type chips, pages
   list, entities list, monitors with add form).
3. Analysis tab (analyses list with status badges, result pane,
   re-run / delete, stub-node queued-jobs notice).
4. Cluster workspace (Nodes / Q&A / Common tabs, cluster-mode gating
   so Domains row-click doesn't trigger it, batch `Send to Crawl`).

## Read order

1. `plan.md`
2. `checklist.md`
3. `../../../specs/right-pane.md` (source spec)
4. `../../../reference/frontend-structure.md`
