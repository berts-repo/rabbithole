# Pane Responsibility Reset

First post-F6 cleanup package. Frontend only — no schema, no backend routes.
Establishes the four-pane mental model and action taxonomy that every later
cleanup depends on.

Closed package. Prefer [`outcome.md`](outcome.md) for what shipped.

## Goal

Give each shell pane one stable job:

- **Left** — compose and start work (Crawl / Intel / Search sub-tabs).
- **Center graph** — investigate relationships.
- **Right** — inspect and act on the current selection.
- **Bottom** — monitor and manage queues, activity, lists, and datasets.

## Scope of this package

- Move the **Scheduled Crawls** recipe list out of the left sidebar into the
  bottom pane, and add a new global **Monitors** recipe tab beside it.
- Group the bottom-pane tabs under three top-level labels — **Work**,
  **Catalog**, **Sets** — each opening a sub-strip, so later items (Activity,
  Labels, Search Results) have a home and the flat strip stops overflowing.
- Add one consistent **right-pane action bar** (Send to Crawl / Add to
  collection / Flag / Queue Analysis / More) wired to the existing
  `$lib/contextMenu/actions.ts` helpers and the existing action modals.
- Persist the last-used left sub-tab and bottom sub-tab.

## Two carve-outs (decisions for this package)

1. **`CrawlQueuePanel` and `BatchConfirmStrip` stay in the left Crawl
   sub-tab.** The spec keeps the durable crawl queue in the left sidebar as a
   named carve-out until the schema reset (NEXT item: Schema Reset Milestone),
   when the Activity tab absorbs it in one user-visible step. The batch-confirm
   strip stages directly into that queue, so it stays with it rather than
   splitting a coupled flow across panes only to be torn out again. This
   package therefore removes **only** Scheduled Crawls from the left pane.

2. **The `Analyses` bottom tab lives under Work as an interim home.** The
   unified Activity tab (Schema Reset Milestone) will absorb it later; until
   then it sits in the Work group rather than getting its own scheme.

## Read order

1. [`outcome.md`](outcome.md)
2. [`plan.md`](plan.md), [`checklist.md`](checklist.md)
3. `docs/reference/frontend-structure.md`

## Relationship to the queue

Required precondition for the Shared UI Primitives and GraphCanvas
Decomposition packages and everything after them in
[`../../NEXT.md`](../../NEXT.md).
