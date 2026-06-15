# Bottom Pane Completion (F7)

Status: active — Phase 1 starting.
Date: 2026-05-26

The graph view's bottom pane is currently a stub: `BottomPane.svelte` has
the eight tab buttons wired but the body just renders
`{tab} — content lands in F7`. This package builds the eight sub-tabs
described in `docs/specs/explore-bottom-pane.md` plus the reusable
`BottomPaneRow` component and a consolidated right-click context menu.

Backend support is already complete — every sub-tab has its routes, DB
module, and (where needed) SSE channel. This is a frontend-only build
with no schema work.

Completing F7 also closes two surfaces deferred from the just-shipped
durable-crawl-queue work: Bookmarks row `▶ Send to Crawl` and the
Collection sub-tab `Send to Crawl (all uncrawled)` action.

Source spec: `../../../specs/explore-bottom-pane.md`.

## Phases

The package ships in four internal phases on `main`. See `plan.md`.

1. Row component + context-menu consolidation + Bookmarks + Collection
   (closes the two deferred Send-to-Crawl surfaces).
2. Live Crawl + Analyses (streaming / polling).
3. Domains + Flags (list-with-filters).
4. Fingerprints + Hidden (most self-contained).

## Read order

1. `plan.md`
2. `checklist.md`
3. `../../../specs/explore-bottom-pane.md` (source spec)
4. `../../../reference/frontend-structure.md`
