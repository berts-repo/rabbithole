# Plan — Right Pane Completion (F6)

## Scope

The three single-node tabs (Page / Domain / Analysis), the stub-node
simplified state on each, and the multi-select cluster workspace
(Nodes / Q&A / Common). All frontend; no schema work; no new endpoints.

Spec: `../../../specs/right-pane.md`.

## Approach

One package, four phases on `main`. Each phase ships independently and
updates `checklist.md` as it goes.

Existing infrastructure to reuse:

- `selectionStore.selectedNodeId` / `selectedIds` / `multiCount`
  (`frontend/src/lib/stores/selection.svelte.ts`).
- `navigationStore.rightTab` + `setRight(tab)`
  (`frontend/src/lib/stores/navigation.svelte.ts`).
- `layoutStore.rightCollapsed` + `expandRight()` / `collapseRight()`.
- Shared `ContextMenu.svelte` + `MenuTarget` from F7's
  `lib/contextMenu/` (entity context menus reuse the Onion-URL /
  Handle / Copy patterns the bottom-pane rows already use).
- `BatchConfirmStrip.svelte` + `batchConfirmStore.stage()` for the
  cluster-workspace and stub-node `Send to Crawl` paths.
- `domainAlias`, `flagStatus`, `collectionAdd/Remove`, `notesAdd/Delete`
  API helpers already in `lib/api/`.
- `actSendToCrawl`, `actSendToSearch`, etc. from
  `lib/contextMenu/actions.ts`.

### Phase 1 — Shell + Page tab

Replace the placeholder body with a tab-routed slot and build the
single-node Page tab end to end.

- `RightPanel.svelte` — keep the existing collapsed sliver + tab bar,
  swap the placeholder body for a `{#if multiCount >= 2}` cluster
  branch (Phase 4) over a per-tab single-node branch (Phase 1–3).
  Auto-expand behaviour from the spec: any new full-selection
  expands the panel unless the user collapsed it themselves this
  session.
- `views/right/PageTab.svelte` — owns node-detail fetch keyed by
  `selectionStore.selectedNodeId`. Loads node detail, collections,
  and notes in parallel on every URL change. Renders:
  - Header block: URL (small green), domain alias with ✎ pencil
    opening the existing `RenameAliasPopover.svelte`, title, meta
    chips (`HTTP 200`, `depth 2`, category), Reviewed and Exclude
    toggles (`PATCH /api/nodes/{id}/reviewed` / `…/analysis_excluded`),
    summary block.
  - Collections section: pills with ✕, `+ Add` opens a lazily-loaded
    picker (cached in component state) that hides already-joined
    collections.
  - Flag section: only when `flag` is non-null. Status + Priority
    selects (save-on-change), note textarea (save-on-blur),
    Remove-flag button.
  - Details toggle: starts expanded on every node load.
  - Expanded block: content preview, entities (right-click → shared
    `ContextMenu` with Onion-URL / Handle / Copy actions; click also
    opens the same menu), response headers `<details>`, version
    history `<details>`, notes (add textarea + Save, ✕ delete).
- `views/right/StubPageTab.svelte` (or a `stub` branch inside
  `PageTab.svelte`) — URL + amber `not crawled` badge, collection
  pills, flag section if flagged, notes, prominent `Send to Crawl`
  that switches the left pane to Crawl and loads the URL into the
  single-URL manual input.
- New `lib/api/nodes.ts` helpers if missing (`getNodeDetail`,
  `setReviewed`, `setAnalysisExcluded`); add to barrel.

### Phase 2 — Domain tab

- `views/right/DomainTab.svelte` — scoped to the page-detail
  response's `domain` field; makes no API calls when no node is
  selected. Renders:
  - Profile card: four chips (`Pages`, `Flags`, `Entities`, `Uptime`).
  - Activity sparkline — small SVG polyline of pages-per-day from
    `domain_profile.activity[]`; dots with `YYYY-MM-DD: N pages`
    tooltip; single-day data shows a text label; empty shows
    `No dated pages`.
  - Entity-type breakdown — horizontal chips from `entity_types[]`.
  - Pages list — up to 200 rows; row click is a
    `selectionStore.highlight(...)` (highlight-only, not full).
    Right-click opens the shared `ContextMenu`. When the 200 cap is
    hit, render the "Showing 200 of N — view all in the Domains
    tab" link that switches the bottom pane to Domains pre-filtered
    by host.
  - Entities list — shared context menu by type; below it the
    `View fingerprint clusters →` link that switches the bottom
    pane to Fingerprints pre-filtered for this host.
  - Uptime monitors — list with ⏸/▶ enable toggle and ✕ remove;
    add-monitor form (URL + label + interval, collapsible Alert
    settings with content-change / restore / downtime-threshold).
- Stub-node Domain branch: monitors section fully functional;
  profile and pages list show "Not yet crawled."
- New `lib/api/monitors.ts` helpers if any are missing; the
  endpoints exist already.

### Phase 3 — Analysis tab

- `views/right/AnalysisTab.svelte` — reloads on every node change.
  - Analyses list (`GET /api/analyses?node_id=…`): type, status
    badge (`done` teal, `pending` amber, `running` pulsing dot,
    `waiting` muted amber with tooltip), model line, Re-run button
    (only on `done`), ✕ delete.
  - Result pane below: meta line, Q&A question line (italic grey)
    when present, monospace pre-formatted body, status placeholders
    (`In queue…`, `Running…`, `No result yet.`).
  - Fetches result only when status is `done`.
- Stub-node Analysis branch: shows queued waiting jobs, Queue
  Analysis form, and the "Jobs will run when this URL is crawled"
  notice.
- Reuse `lib/api/analyses.ts` from F7 Phase 2 (list / delete / rerun
  / batch / get-result). Add a `getAnalysisResult(id)` helper if
  missing.

### Phase 4 — Cluster workspace

- Cluster-mode gating. Today `selectionStore.replaceMulti(...)` (used
  by the bottom-pane Domains row click in F7 Phase 3) would trip the
  cluster workspace once `multiCount >= 2`. Introduce an explicit
  `selectMode: 'cluster'` and make the cluster branch in
  `RightPanel.svelte` gate on it instead of raw count. Domains
  row-click stays a multi-highlight, not a cluster trigger.
- `views/right/cluster/NodesTab.svelte` — managed selection list.
  Per-row ✕ removes (`selectionStore.deselect(id)`). Buttons:
  - `Add to collection` — collection picker, adds every selected
    node (stubs included).
  - `Save as new collection` — small popover with name input;
    creates collection then adds.
  - `Send to Crawl` — stages every URL in `BatchConfirmStrip`,
    switches left pane to Crawl. Works regardless of stub state.
  - Selection dropping to 1 snaps back to the single-node view.
- `views/right/cluster/QnATab.svelte` — single textarea +
  `Ask all`. Queues a Q&A job per crawled node via
  `POST /api/analyses/batch` (skips stubs and already-queued).
  Polls every 5 s while any selected node has a `pending` /
  `running` Q&A job matching the question; renders results inline
  as they complete. Empty-state, stubs-excluded notice, all-stub
  disabled state per spec.
- `views/right/cluster/CommonTab.svelte` — `GET
  /api/entities/common?node_ids=…` (crawled only); ⟳ refresh
  button. Rows grouped by type, with "seen on N / M nodes"
  count. Shared context menu by entity type.
- Phase B `Send to Crawl` closure: the cluster-batch button above
  closes the deferred cluster path; the single-node stub button
  in Phase 1 closes the right-pane single path.

## Files

- `frontend/src/views/RightPanel.svelte` — replace placeholder body
  with cluster-vs-single branch + per-tab component slot.
- `frontend/src/views/right/*` — new directory for `PageTab.svelte`,
  `DomainTab.svelte`, `AnalysisTab.svelte`, plus the cluster sub-
  directory `cluster/{NodesTab,QnATab,CommonTab}.svelte`. Small
  shared pieces (sparkline, status badge, meta chips) live alongside.
- `frontend/src/lib/api/*` — fill in any missing helpers for node
  detail, monitors CRUD, analysis result fetch, batch analyses,
  common entities. Most endpoints already have a module.
- `frontend/src/lib/stores/selection.svelte.ts` — add
  `selectMode: 'cluster'` plus `replaceCluster(ids)` /
  `deselect(id)` helpers; update the bottom-pane Domains row to
  keep using `replaceMulti(...)` (highlight-only, no cluster trip).
- `frontend/src/lib/stores/layout.svelte.ts` — add a "user
  collapsed this session" flag so auto-expand-on-select can be
  suppressed once the analyst explicitly collapses.

## Verification

Per phase, in `rabbithole/frontend/` with the backend running on
`:7654`:

- `npm run check` — TypeScript strict passes.
- `npm run test` — existing Vitest suites pass; each new component
  gets a pure-helper test where the logic is non-trivial
  (sparkline binning, status-badge mapping, cluster gating).
- `npm run dev` and exercise in a browser via the SwiftShader Edge
  profile. Verify:
  - Selection model: row click (full) shows + auto-expands the
    panel; graph click (highlight) updates the panel without
    moving the bottom-pane active row; left-pane search result
    (highlight) does the same.
  - Stub nodes: Page tab `Send to Crawl` lands the URL in
    `CrawlControls`; Analysis tab queued waiting jobs appear after
    "Queue Analysis"; Domain tab monitors add/remove still works.
  - Cluster workspace: graph multi-select trips the workspace;
    bottom-pane Domains row click does *not*; cluster
    `Send to Crawl` stages every URL in `BatchConfirmStrip`;
    `Ask all` queues Q&A only for crawled nodes; Common tab shows
    entities seen on ≥ 2 selected crawled nodes.
- Phase 4: verify the two deferred Send-to-Crawl surfaces (single-
  node stub + cluster batch) end-to-end.
