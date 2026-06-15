# Phase 3 progress / handoff (item 11)

Slices defined (build order). Each ships green + committed to main on its own.

- **Slice A — DONE, committed `d730c65`.** Bottom-pane Labels tab + members
  endpoint + label NodeSet (3a + 3f). Backend `GET /api/labels/:id/members`
  (`db/labels.label_members`), `'labels'` BottomTab (not default-visible),
  `LabelsTab.svelte` (drag-reorder writes rank, lazy member expand =
  highlight-only, open-as-graph-tab), `NodeSetSource{kind:'label'}`. Pure
  helpers + vitest. Green: backend 797, front check 0/0 + 459, bundle.

- **Slice B — DONE.** Color-by-label + labelFilter (3c). Backend label
  color/filter settings keys; `labelFilter.ts` pure predicate +
  `labelFilter.svelte.ts` store; `dominantLabelColor` + `'label'` color mode
  wired through reducer/visibility controllers; `GraphCanvas` deps + reactivity;
  `GraphFilterControls` Label mode + tri-state Labels filter group; boot load in
  `app.svelte`. Green: front check 0/0 + vitest 467, backend 812, bundle.

- **Slice C — DONE.** Graph collapse machinery (3d, D4–D8). Alias-aware domain
  folds; `clusterLabel.ts` (`cluster:label:<id>`) + `foldPlan.ts` unified D5/D6
  resolution (highest-ranked collapsed label wins, domain at the floor, overlap
  counts) routed through both `rebuildInto` + `applyDiff`; per-workspace-tab
  `graphCollapseStore` persisted to the `graph.collapse` JSON setting; per-domain
  "Collapse/Expand" menu action + label-cluster double-click expand + a
  "Fold by label" group in the filter panel. Green: front check 0/0 + vitest
  496, backend 819, bundle.

  Build order (each kept green):
  1. `model/clusterLabel.ts` (+test) — `cluster:label:<id>` key scheme
     (`labelClusterKey`/`isLabelClusterKey`/`labelClusterId`),
     `synthesizeLabelClusterRaw(label, members, overlaps)`. Label-cluster keys
     also satisfy `isClusterKey` (shared `cluster:` prefix) — decode paths must
     test `isLabelClusterKey` first.
  2. `model/clusterDomain.ts` — alias-aware `synthesizeClusterRaw`: label the
     folded node with `members[0].alias` (the backend already serves the *domain*
     alias on every node's `alias`, graph.py:285/299) when set, host otherwise.
  3. `model/foldPlan.ts` (+test) — pure unified fold resolution. Given payload
     nodes + `{collapsedDomains, collapsedLabels(rank-ordered), groupByDomain,
     expandedDomains}`, assign each fetched page to the highest-ranked collapsed
     label it carries, else its collapsed domain (D5/D6: domain at the floor),
     producing `memberToCluster` + per-cluster members + overlap counts.
  4. `model/applyPayload.ts` — both `rebuildInto` + `applyDiff` route through
     the FoldPlan; `ClusterFilterOptions` gains `collapsedDomains` +
     `collapsedLabels`; diff topology-bail accounts for the label-cluster set;
     position seeding (centroid + re-emergence fan) generalised to any cluster
     key. Update `applyPayload.test.ts`.
  5. `stores/graphCollapse.svelte.ts` (+test) — per-workspace-tab collapse sets
     (`domains:Set<string>`, `labels:Set<number>`), persisted to a new
     `graph.collapse` JSON setting keyed by workspace id (covers Global, which
     `workspace.tabs` omits). Toggle/clear/active getters scoped to
     `workspaceStore.activeWorkspaceId`.
  6. Backend `db/settings.py` — register `graph.collapse` validator + test in
     `tests/test_b4_settings.py`.
  7. `stores/graph.svelte.ts` — `currentClusterOptions` reads the active tab's
     collapse sets; collapse toggles rebuild from current payload. Double-click
     on a label-cluster un-collapses that label.
  8. `contextMenu` + `GraphCanvas` + `GraphFilterControls` — per-domain
     "Collapse"/"Expand" action; collapse-by-label toggles in the Labels group;
     reducer colours a label-cluster by its label swatch.
  9. `app.svelte` boot-load `graphCollapseStore`. Gauntlet green, commit
     `feat(labels): Phase 3d — graph collapse (domain + label folds)`.

- **Slice D — DONE.** Left-pane label browser (3b) + Settings Labels tab (3e).
  - `views/left/labelBrowser.ts` (+test) — pure `labelMemberNodeIds` (one pass
    over the payload mapping each label id → the node-id set carrying it, direct
    ∪ via-domain) + `sameIdSet`. `views/left/LabelBrowser.svelte` mounts under
    the Find composer in `FindTab.svelte`: lists `labelsStore.visible` with a
    per-label in-graph member count, click highlights that set
    (`selectionStore.replaceMulti`, highlight-only), second click on the active
    label clears. Counts re-derive from `graphStore.payload`, so they track the
    active workspace tab.
  - `components/modals/settings/LabelsTab.svelte` — registered as the `labels`
    tab in `SettingsModal`. Drag-reorder (writes `rank`), per-label color
    palette + description edit, custom-label rename/delete, preset `hidden`
    toggle (eye), inline add. Every mutation routes through `labelsStore`
    (the catalog), so chips/picker/color/collapse stay in sync; PATCH always
    sends the full current state so `hidden` isn't reset by omission.
  - Scope hygiene: lifted the generic drag-reorder `reorderedIds` out of
    `views/bottom/labels.ts` into shared `$lib/labels/order.ts` (+test) now that
    both the bottom tab and the settings tab reorder the same rank list.
  - Green: front check 0/0 + vitest 502, backend 819 (untouched), single bundle.

- **Slice E — TODO.** Close-out: docs (data-model v6, features labels+collapse),
  outcome.md, archive per LIBRARIAN.md, drop item 11 from NEXT.md. This is the
  only remaining slice — all four Phase-3 surfaces (browse, filter, color,
  collapse) plus management now ship.

## Notes / conventions in play

- Per-node payload already carries `label_ids` (direct, rank-ordered) +
  `domain_label_ids` (via-domain). The catalog store `labelsStore` resolves
  id→{rank,color}; `byId(id)` exists.
- Selection model: bottom-pane label-member click is highlight-only (plan), not
  full select — matches Domains tab precedent.
- Memory rules in force: clean code no shortcuts; commit/push goes straight to
  main; no Co-Authored-By lines; dev DB is disposable.
- Git: Slice A is `d730c65` on main. Untracked root `.md` files + screenshots +
  `.playwright-mcp/` must stay OUT of commits (stage explicit paths).
