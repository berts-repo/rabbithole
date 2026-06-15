# Checklist — Label System (item 11)

## Phase 1 — Schema + CRUD + page-alias column

- [x] `db/core.py`: add `labels`, `resource_labels`, `domain_labels`;
      `ALTER TABLE pages ADD COLUMN alias`; v5 → v6 forward migration block.
- [x] Seed seven presets (`builtin = 1`) with default ranks (warnings high);
      seeding idempotent on re-run.
- [x] `db/labels.py`: CRUD, attach/detach (both join tables), member counts,
      rank read/write.
- [x] `db/pages.py`: `alias` get/set accessor (mirror `db/domains.py`).
- [x] `routes/labels.py`: CRUD + attach/detach + reorder endpoints.
- [x] `PATCH /api/pages/:id/alias`. *(Label-filter param on `routes/domains.py`
      is a Phase-3 filter concern — deferred to that phase.)*
- [x] pytest: CRUD, 409 dup name, preset-undeletable, cascade-on-delete,
      page-alias set/clear, rank reorder, idempotent seed.

## Phase 2 — Apply + page rename

- [x] `lib/api/labels.ts` + page-alias client.
- [x] Replace `renameTarget()` `page`-branch stub with `patchPageAlias`; remove
      the misleading domain-rename-from-PageTab path.
- [x] **Membership read surface (added):** `db/labels.py`
      `resource_label_ids` / `domain_label_ids` + bulk maps; `label_ids` +
      `domain_label_ids` (via-domain, server-deduped) on the graph payload,
      node detail, and domain profile; graph-cache invalidation on
      attach/detach/delete/reorder. pytest covers all. *Chips/picker need
      current membership; the catalog store resolves ids → name/color so
      appearance has one source of truth.*
- [x] Label apply/remove action helper on `contextMenu/actions.ts` (`setLabel`,
      target-agnostic over the two join tables).
- [x] Label-picker popover (`LabelPickerPopover.svelte`, search existing +
      create-new inline, optimistic toggles, deferred graph refresh on close).
- [x] Label chips in right panel (`LabelChips.svelte` in Page + Domain tabs)
      with the "via domain" badge. *(Bottom-pane list-row chips ride with the
      Phase-3 Labels-tab surfacing work.)*
- [x] `lib/stores/labels.svelte.ts` (list + ranks + counts) + `resolve(ids)`
      + boot-time `ensureLoaded()` in `app.svelte`.
- [x] Menu wiring: `label` capability + `applyLabels` handler in the shared
      single-target menu; graph adapter + GraphCanvas + RowContextMenu mounts.
- [x] vitest: pure picker seam (`labels.test.ts` — modal shape, identity,
      create-name gating). Attach/detach covered backend-side.

## Phase 3 — Surfacing

- [x] Bottom-pane `labels` tab (`bottomTabs.ts` + `_BOTTOM_TAB_VALUES`,
      not default-visible); `LabelsTab.svelte` with expandable members +
      drag-to-reorder writing `rank`. *(Members ride a new
      `GET /api/labels/:id/members` + `db/labels.label_members`; expand is
      highlight-only per the app model — resource highlights its node, domain
      highlights its host's nodes.)*
- [x] Left-pane label browser in the Find sub-tab. *(`LabelBrowser.svelte`
      under the Find composer; counts + highlights each label's members in the
      current graph workspace off the rendered payload, union of direct +
      via-domain ids; highlight-only, second click clears. Pure set math in
      `views/left/labelBrowser.ts` + vitest.)*
- [x] Color mode `label` (highest-ranked label wins). *(Slice B.)*
- [x] `labelFilter` predicate in `visibilityController`, composing with
      `graph_filters`; "Avoid" = exclude. *(Slice B.)*
- [x] Domain cluster alias-aware (`synthesizeClusterRaw` reads `domains.alias`).
      *(Slice C.)*
- [x] Selective per-domain "Collapse" action over the existing cluster seam.
      *(Slice C.)*
- [x] `clusterLabel.ts`: `cluster:label:<id>` fold across domains. *(Slice C.)*
- [x] Unified fold resolution: highest-ranked collapsed group wins, domain at
      the floor; overlap counts on folded nodes. *(Slice C — `foldPlan.ts`.)*
- [x] Persist collapsed domains + labels per workspace tab. *(Slice C —
      `graphCollapse.svelte.ts` + `graph.collapse` setting.)*
- [x] Settings modal Labels tab (preset `hidden` toggles, CRUD, colors, rank).
      *(`settings/LabelsTab.svelte`; drag-reorder shares `$lib/labels/order`
      with the bottom tab; per-label color palette + description, custom-label
      rename/delete, preset hide toggle, inline add. All mutations via
      `labelsStore`.)*
- [x] Wire `NodeSetSource { kind:'label'; labelId }` → workspace tab. *(Opened
      from the Labels tab's per-label graph-icon; captures the resource node
      ids; signature `label:<id>` so reopening focuses the existing tab.)*

## Close-out

- [x] Backend pytest (819) + frontend check (0/0) / vitest (502) +
      single-bundle build green.
- [x] Update `docs/reference/data-model.md` (v6 label tables + `pages.alias`)
      and `docs/reference/features.md` (labels, collapse).
- [x] `outcome.md`; archive per `LIBRARIAN.md`; remove item 11 from `NEXT.md`;
      mark the source-spec addition consumed.
