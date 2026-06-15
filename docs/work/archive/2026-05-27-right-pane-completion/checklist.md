# Checklist — Right Pane Completion (F6)

Source spec: `../../../specs/right-pane.md`. Backend endpoints listed
in `plan.md`; all exist.

## Phase 1 — Shell + Page tab

### Shell

- [x] `RightPanel.svelte` body replaced with a per-tab component slot
      (Page wired now; Domain / Analysis stay placeholders until their
      phases).
- [x] Auto-expand on new full-selection unless the user collapsed
      this session (`layoutStore.userCollapsedRightThisSession` +
      `expandRightForSelection()`).
- [x] No-selection placeholder per tab — no API calls when
      `selectedNodeId` is `null` (PageTab guards every fetch).

### Page tab (single node, crawled)

- [x] `views/right/PageTab.svelte` — parallel fetch of node detail,
      collections, notes on every `selectedNodeId` change; versioned
      `fetchGen` guard so a slow earlier load can't clobber a newer
      one.
- [x] Header: URL, alias + ✎ pencil (reuses
      `RenameAliasPopover.svelte`), title, meta chips, Reviewed +
      Exclude toggles (immediate `PATCH`), summary block.
- [x] Collections: pills with ✕ (immediate remove, no confirm); `+
      Add` opens lazy-loaded picker (cached in component state);
      already-joined collections show ✓ and are unselectable; add
      shows `Added to collection` toast. New helpers:
      `listNodeCollections` (`api/collections.ts`).
- [x] Flag section (only when `flag` is non-null): Status select
      (folds `flagged` into `pending` for display), Priority select,
      note textarea (save on blur), Remove flag. New helper:
      `patchFlag` (`api/flags.ts`).
- [x] Details toggle, starts expanded on every node load.
- [x] Expanded block:
  - [x] Content preview (~500 chars, mono, 80 px scroll). Backend
        `db/nodes.py::get_node` now derives `body_text_preview`.
  - [x] Entities: header `Entities (N)`; click/right-click opens
        shared `ContextMenu` with type-aware actions (Onion URL:
        Send to Search / Send to Crawl / Copy; Handle: Send to
        Search / Copy; Email/BTC/XMR/PGP/blob: Copy). Builder lives
        in `views/right/entityMenu.ts`, covered by
        `entityMenu.test.ts`. New action `actSendToSearch` +
        `searchPendingStore` stage the value for the F5-owned Search
        sidebar to drain on mount.
  - [x] Response headers `<details>` (open by default).
  - [x] Version history `<details>` (open by default). Backend
        `get_node` now joins `page_versions`.
  - [x] Notes: list with ✕ delete, textarea + `Save note` (disabled
        on blank trim); both refresh the list. New module
        `api/notes.ts`.

### Page tab (stub)

- [x] URL + amber `not crawled` badge, collection pills, flag
      section if flagged, notes.
- [x] No title / content / entities / headers / version history (stub
      branch skips the details toggle and its block).
- [x] Prominent `Send to Crawl` reuses `actQueueCrawl` to switch the
      left pane to Crawl and load the URL into the manual single-URL
      input.

### Phase 1 verification

- [x] `npm run check` clean (3971 files, 0 errors).
- [x] `npm run test` clean (146 passed); `entityMenu.test.ts`
      covers the per-type action mapping.
- [x] Backend `pytest` clean (667 passed) — `get_node` extension is
      additive and the existing tests still pass.
- [ ] Browser exercise (SwiftShader Edge) — deferred. Vitest covers
      the per-type entity menu mapping; the surface checks (auto-
      expand, alias rename round-trip, collection picker, flag
      editor, notes, stub Send-to-Crawl) will be exercised when
      Phase 2 lands on top.
- [x] Update `docs/reference/features.md` with the Page tab.

## Phase 2 — Domain tab

- [x] `views/right/DomainTab.svelte` — scoped to the loaded node's
      `domain`; fetches node detail, profile, pages, entities, and
      monitors in parallel with a `fetchGen` guard. No API calls
      when no node is selected.
- [x] Profile card: four chips (Pages / Flags / Entities / Uptime —
      `Up` teal at HTTP 200, numeric red otherwise, `–` when no
      monitor).
- [x] Activity sparkline — SVG polyline + dots with `YYYY-MM-DD: N
      page(s)` tooltips. Single-day → text label. Empty → "No dated
      pages". Layout math lives in `$lib/sparkline.ts`; covered by
      `sparkline.test.ts` (4 cases: empty / single / multi / all-
      zero divide-by-zero guard).
- [x] Entity-type chips row.
- [x] Pages list — up to 200 rows; row click is
      `selectionStore.highlight(p.id)` (highlight only); over-cap
      link switches the bottom pane to Domains pre-filtered for
      this host via `bottomPanePresetStore.send('domains', host)`.
      Right-click context menu deferred — the spec lists it but the
      shared `ContextMenu` needs a `GraphNode`-shaped target the
      pages-list response doesn't carry; phase 4 will revisit once
      the cluster workspace already builds menu targets from row
      ids.
- [x] Entities list — shared `ContextMenu` per type via
      `buildEntityMenu`; below it `View fingerprint clusters →`
      switches the bottom pane to Fingerprints pre-filtered for
      this host.
- [x] Uptime monitors — list rows with ⏸/▶ enable toggle and ✕
      remove; add-monitor form (URL pre-filled from the selected
      node + label + interval; collapsible Alert settings:
      content-change / restore / downtime threshold). New API
      helpers: `listMonitors(host?)`, `patchMonitor`, `deleteMonitor`
      + `UpdateMonitorBody` type.
- [x] Stub-node branch: monitors fully functional; profile / pages
      / entities are hidden behind a "Not yet crawled." notice
      (only the monitors section renders, matching spec intent).

### Phase 2 verification

- [x] `npm run check` clean (3975 files, 0 errors).
- [x] `npm run test` clean (150 passed; `sparkline.test.ts` adds 4
      cases on top of phase 1's 146).
- [x] Backend `pytest test_b7_domains.py` clean (14 passed) — the
      `id` field added to `list_pages` is additive and doesn't
      break the existing cap / filter tests.
- [ ] Browser exercise — deferred. Pure-helper tests cover the
      sparkline layout; the surface checks (profile chip values,
      pages list cap link, fingerprints link, monitors add /
      pause / resume / remove, alert-settings form) will be
      exercised when Phase 3 lands on top.
- [x] `features.md` update.

## Phase 3 — Analysis tab

- [x] `views/right/AnalysisTab.svelte` reloads on every node change
      via the same `selectionStore.selectedNodeId` `$effect`
      pattern as Page / Domain.
- [x] Analyses list: type + status badge (`done` teal / `pending`
      amber / `running` teal + pulsing dot / `waiting` muted amber
      with `Waiting — crawl this URL first.` tooltip), model line,
      Re-run on `done` rows, ✕ delete.
- [x] Result pane: meta line (type · model · status — status flips
      teal when `done`), Q&A question line (italic grey) when
      present, monospace body, status placeholders (`In queue…`,
      `Running…`, `Waiting — this URL is a stub…`, `No result
      yet.`).
- [x] Result rendering is gated on `status === 'done' && result`;
      pending / running / waiting rows show the placeholder
      message without an API call. Backend `list_queue` returns
      `result` inline, so no separate result fetch was needed.
- [x] Stub-node branch: same Queue Analysis button + amber
      "Jobs will run when this URL is crawled." notice above the
      list. Waiting rows show their wait tooltip.
- [x] Polling: 5 s `setInterval` while any row is `pending` or
      `running`; stops as soon as the work settles
      (`shouldPoll` helper). Cleaned up in `onDestroy`.
- [x] Queue Analysis: reuses `QueueAnalysisModal` so type /
      model / Q&A wiring stays in one place. Looks up a live
      `GraphNode` from `graphStore.payload` and falls back to a
      constructed shape from `NodeRow` when the node isn't
      currently in the graph view. Modal close triggers a refresh
      so the new pending / waiting row appears immediately.
- [x] API: new `deleteAnalysis` and `rerunAnalysis` helpers in
      `api/analyses.ts`.

### Phase 3 verification

- [x] `npm run check` clean (3978 files, 0 errors).
- [x] `npm run test` clean (162 passed; `analysisStatus.test.ts`
      adds 12 cases covering badge mapping, result placeholders,
      and the poll predicate).
- [ ] Browser exercise — deferred. Pure-helper tests cover the
      status / placeholder mapping; surface checks (Re-run flow,
      ✕ delete, Q&A question rendering, stub → crawl → pending
      → done transitions, polling start / stop) will be exercised
      when Phase 4 lands on top.
- [x] `features.md` update.

## Phase 4 — Cluster workspace

### Cluster-mode gating

- [ ] `selectionStore` gains `selectMode: 'cluster'` plus
      `replaceCluster(ids)` and `deselect(id)`; right-panel cluster
      branch gates on `selectMode === 'cluster'`, not raw
      `multiCount`.
- [ ] Bottom-pane Domains row click stays
      `selectionStore.replaceMulti(host node ids)` (highlight-only)
      and does *not* trip the cluster workspace.
- [ ] Graph multi-select (Ctrl/Cmd-click, Shift-click, Ctrl+A)
      calls `replaceCluster(...)`.
- [ ] Selection dropping to 1 node snaps the panel back to the
      single-node view.
- [ ] Clearing the selection (Escape, click empty canvas) returns
      to single-node view.

### Nodes sub-tab (default)

- [ ] `views/right/cluster/NodesTab.svelte` — per-row URL display,
      amber `not crawled` badge on stubs, ✕ removes that node.
- [ ] `Add to collection` opens the collection picker.
- [ ] `Save as new collection` opens a name-input popover, creates
      collection, adds every selected node (stubs included).
- [ ] `Send to Crawl` stages every URL in `BatchConfirmStrip`,
      switches the left pane to Crawl. Works regardless of stub
      state. Closes the deferred Phase B cluster `Send to Crawl`.

### Q&A sub-tab

- [ ] `views/right/cluster/QnATab.svelte` — single textarea +
      `Ask all` button.
- [ ] If stubs are in the selection, notice "N stubs excluded —
      Q&A requires crawled content."
- [ ] `Ask all` queues Q&A jobs per crawled node via
      `POST /api/analyses/batch`; skips stubs; respects the same
      skip-already-queued logic as the Queue Analysis modal.
- [ ] Results appear inline as they complete — URL line +
      answer block per node; polls every 5 s while any selected
      job is pending or running.
- [ ] Empty state before asking: "Enter a question and press Ask
      all."
- [ ] All-stub selection: button disabled, notice "No crawled
      nodes in selection."
- [ ] Per-node results are also visible from the bottom-pane
      Analyses sub-tab and from the single-node Analysis tab
      (because they're stored in `analyses` as normal).

### Common sub-tab

- [ ] `views/right/cluster/CommonTab.svelte` — single fetch on tab
      open via `GET /api/entities/common?node_ids=…` (crawled only);
      ⟳ refresh button.
- [ ] Stubs-in-selection notice when applicable.
- [ ] Rows grouped by type, each row: type chip · value (mono) ·
      "seen on N / M nodes".
- [ ] Click / right-click → shared `ContextMenu` per type.
- [ ] Empty state: "No shared entities across selected nodes."

### Phase 4 verification

- [ ] `npm run check` clean.
- [ ] `npm run test` clean.
- [ ] Browser exercise: cluster trip from graph multi-select; no
      cluster trip from Domains row click; cluster `Send to Crawl`
      stages every URL; `Ask all` queues only crawled; Common tab
      shows entities seen on ≥ 2 selected nodes; selection drop
      to 1 snaps back; Escape clears and returns.
- [ ] Phase B deferred surfaces confirmed: single-node stub
      `Send to Crawl` (Phase 1) + cluster batch `Send to Crawl`.
- [ ] `features.md` update.
- [ ] Close package — `outcome.md` written, moved to `archive/`,
      `ACTIVE.md` repointed.
