# Schema Reset Milestone (item 6)

**Closed 2026-06-05 — see [`outcome.md`](outcome.md) for what shipped, the owner
decisions, and final results.** Promoted from `NEXT.md` item 6 on 2026-06-04
once its dependencies (items 1–5) closed — the frontend is stable, decomposed,
on its final workspace model, and legible.

The largest single package in the post-F6 cleanup sequence. One coordinated,
breaking **DB-delete** cutover that bundles three schema-touching cleanups:

1. **State vocabulary consolidation** — `resources.state`
   (`unknown`/`known`/`crawled`/`dead`) replaces `nodes.stub`,
   `crawl_queue.lookup_state`, and the analysis `waiting` derivation.
2. **Resource / page data model split** — `nodes` splits into `resources`,
   `pages`, `page_versions`, `graph_nodes`, `findings`. Unlocks page versioning.
3. **Unified `jobs` table + Activity tab** — one work-tracking table and one
   status vocabulary, plus the new bottom-pane `ActivityTab.svelte`.

Key feature unlock: **page versioning** — re-crawl a URL, keep both snapshots,
diff them.

## Specs

- `source-spec.md` — the milestone spec.
- `source-ddl.md` — consolidated CREATE script,
  column mapping, fill-in decisions D1–D6. **Authoritative DDL.**
- `source-unified-activity-view.md` — `jobs`/Activity spec.
- `source-checklist.md` — six-phase task source.

## Read order

1. This README.
2. `outcome.md` — what shipped, owner decisions, bugs found, final results.
3. `plan.md` — the executable phase plan grounded against the tree.
4. `decisions.md` — owner sign-off gates resolved at promotion.
5. `checklist.md` — task tracker (seeded from `schema-reset-checklist.md`).

## Migration strategy

DB delete — no in-place migration, no adapter layer, no pre-wipe export
(owner-declined). One sharp transition; empty state after cutover.
`SCHEMA_VERSION` 2 → 3.

## Honest framing

Shape win + feature unlock, **not** a code-size win. Net LOC flat-to-slightly-up
(five tables = more joins/insert paths). Affected surface: ~112 files /
~1,128 matches, most shallow renames.
