# Label System (item 11)

Closed package (archived 2026-06-11; see [`outcome.md`](outcome.md)). Gives the
analyst a managed way to **categorize** resources
(URLs / pages) and domains as they work — "this is a market," "avoid this" —
then **query, filter, color, and collapse** the graph by those categories.
Ships page **rename** alongside the existing domain alias on the same UI seam.

Source spec: [`source-spec.md`](source-spec.md) (the former live label-system
addition).
Rename-consolidation source: [`source-rename-consolidation.md`](source-rename-consolidation.md)
(the former live rename-consolidation addition).
This package keeps that spec as the data-model and taxonomy source of truth and
**adds** three things it could not have: the post-reset / post-rename-refactor
code reality, the **collapse-by-label** graph model, and the persistence model.
Read [`decisions.md`](decisions.md) for what this package settled with the owner.

## What changed since the source spec was written

The spec predates three shipped packages. The corrections matter:

1. **Rename is already consolidated.** The latest refactor folded rename onto
   one target-agnostic seam — `lib/contextMenu/rename.ts` (`RenameTarget` with
   `domain | page` kinds) + `renameTarget()` in `contextMenu/actions.ts`. The
   `page` branch is already stubbed and throws `"Page rename not yet
   available"`. So "page rename" is **not** a rebuild — it is: add `pages.alias`
   + endpoint, then fill in that one branch. The source spec's "extend the
   `RenameAliasPopover` pattern" language is obsolete; the seam exists.

2. **Schema is at v5 with a real non-destructive forward migration.** The spec
   said "no `schema_version` bump dance." That is now wrong: labels land as an
   **additive v5 → v6 migration** (new tables + one column, no DB delete),
   consistent with how items 5 and 7 shipped. `findings.kind` is `entity | note`
   (flags are their own table) — labels are **not** a findings kind, per spec.

3. **The Find sub-tab and Settings modal exist.** The two surfaces the spec said
   to "build later" now have real homes: the left-pane label browser slots into
   the existing Find sub-tab; the Settings Labels tab slots into the real
   Settings modal.

## Shape

Two separate data concepts, one shared UI panel (do not fold them together):

| Concept | Cardinality | Stored | Example |
|---|---|---|---|
| **Rename** (alias) | 1:1 per target | `domains.alias` (exists), `pages.alias` (new) | host → "NightMarket" |
| **Label** (tag) | N:M | `labels` + `resource_labels` + `domain_labels` (new) | "Market", "Avoid" |

Surfaces (all from the source spec, unchanged in intent):

- Right-click menus + right-panel action bar — apply/remove labels and rename.
- Bottom-pane **Labels** tab — labels with member counts, expand to members.
- Left-pane **label browser** inside the Find sub-tab.
- Graph **color-by-label** mode and a **label filter** (include/exclude) plugged
  into `visibilityController` as a separate dimension from `graph_filters`.
- Graph **collapse-by-label** — the new capability this package designs; see
  [`decisions.md`](decisions.md) D4–D6 and [`plan.md`](plan.md) Phase 3.
- Settings modal **Labels** tab — preset visibility, custom-label CRUD, colors.

## Read order

1. This README + [`outcome.md`](outcome.md) + [`decisions.md`](decisions.md) +
   [`plan.md`](plan.md)
2. [`source-spec.md`](source-spec.md) — data model, taxonomy, querying, the
   "Avoid" workflow (the original additions spec, kept as historical intent)
3. `backend/backend/db/core.py` (schema + the v5→v6 migration seam),
   `backend/backend/db/domains.py` (alias accessor to mirror for `pages.alias`)
4. `frontend/src/lib/contextMenu/rename.ts` + `contextMenu/actions.ts`
   (`renameTarget`, the stubbed `page` branch) — the rename seam page rename
   lands on
5. `frontend/src/lib/graph/model/clusterDomain.ts` (`synthesizeClusterRaw`,
   `cluster:<domain>` key scheme) + `lib/stores/graphFilters.svelte.ts`
   (`groupByDomain`, `expandedDomains`) — the collapse machinery Phase 3 extends
6. `frontend/src/lib/stores/workspace.svelte.ts` (`persistWorkspace`) — where
   per-tab collapse state persists
