# F4b tester checklist — Graph canvas advanced controls

Walk through this end-to-end after each F4b slice lands. Each box should
pass before F4b is considered shipped. Notes about *expected* gaps
(unblocked-by-later-phases, deferred renderings) are called out inline
so they're not mistaken for bugs.

Prerequisites: a project with at least a handful of crawled nodes, a
couple of stubs, and at least two collections (one open, one not).
Spin up with `make dev-backend` and `make dev-frontend`. Source of
truth is `docs/specs/explore-graph.md` and the archived historical build plan's
F4b section (`docs/work/archive/2026-05-21-build-plan-history/plan.md`).
Deferrals and blocks are tracked in
`docs/work/archive/2026-05-20-fixes/checklist.md` §4, §5, §6c, §7.

## Boot

- [x] `make dev-backend` — backend listens on `:7654`, no errors in log
- [x] `make dev-frontend` — Vite running on `:5173`, opens cleanly
- [x] Open `http://127.0.0.1:5173` — app shell renders, Explore is the active centre tab
- [x] All F4a items in `docs/work/archive/2026-05-20-f4a/checklist.md` still pass (no regressions)

## To verify now — 2026-05-17 sitting

Branch `feat/f4b-workspace-tabs` carries four commits that re-apply
F4b slices 1, 2+3, 3.5, 3.6 on top of `main` (`3516fef`). Backend
suite: 548/548 green. Frontend: 0 errors / 0 warnings, single
bundle.js + bundle.css. Walk the items below before merging.

Prereq: at least two existing collections; the rest of the
prerequisites at the top of this file.

## 2026-05-19 browser-test pass (Claude in browser)

Headline findings — see inline `+` notes per item for detail:

1. **Domain colour mode is a no-op by design** (`GraphCanvas.svelte:150-160`) — contradicts the spec line "all five colour modes produce visibly distinct palettes". **Decision 2026-05-19: fix the renderer.** Wire Domain mode to `categoricalColor(domain)` so each domain gets one of the 8 hues (matching Cluster/Infra). Drop the "adds noise" comment. Rationale: with Group-by-domain off, domain colour is genuinely useful for spotting which page belongs to which domain at a glance; the colour-mode shelf shouldn't have a dead toggle.
2. **Backend bug:** `infra_cluster_id` stores the **raw Content-Security-Policy header text**, not a stable cluster id. Hashing still produces stable colours because the hash is opaque, but the field name lies. **Decision 2026-05-19: normalise + hash at write time.** Parse the CSP, sort directives, strip whitespace, drop nonces, then SHA1 (first 8 chars) into a short cluster id. Two sites running the same hosting stack will land in the same cluster regardless of cosmetic differences — turns the field from a misleading blob into a real "shared infra" signal. Migration: backfill existing rows from a one-shot script that re-reads the stored CSP and writes the normalised hash; drop the legacy text column after backfill verifies. — **RESOLVED 2026-05-20, revised: no hash, no migration.** `infra_cluster_id` is computed in-memory at graph-build time (`db/graph.py::_populate_infra_clusters`), not a stored column — so there is no legacy column and no backfill script. `db/graph.py` now normalizes the CSP (sorts directives, strips per-request `'nonce-…'` tokens) so equivalent policies share a cluster. The field keeps its readable `Header:value` form deliberately — it is exported to CSV/GEXF where a human reads it; an opaque hash would only make that column unreadable. Frontend `infra_cluster_id` type corrected `number` → `string`.
3. **Category colour mode is silently flat** — every node in this DB has `category: null` (LLM worker populates `category` via `llm_worker.py:484` — no jobs have run yet on this project). **Decision 2026-05-19: grey the button + hover tooltip.** When 0 nodes have a value for the active mode's field, render the colour-mode button greyed with a hover tooltip explaining how to populate it (e.g. "No category data yet — queue an AI Category analysis to populate this"). Generalise to any colour-mode field that depends on an upstream pipeline (covers Cluster / Infra cluster too if their populators ever lag).
4. **`flag_status` enum drift** — `createFlag()` writes `'pending'` (`GraphCanvas.svelte:1100, 1197`) but the spec uses `'flagged'` / `'investigating'`. Renderer covers it by checking truthiness, but standardise. **Decision 2026-05-19: three states + typed constants.** Canonical enum is `pending` (auto-set by alert/entity matcher) → `flagged` (analyst-confirmed interesting) → `investigating` (actively working). Lift the strings into a shared constants module on both backend (`backend/backend/flags_enum.py` or similar) and frontend (`frontend/src/lib/types/flags.ts`), import everywhere. Renderer adds an explicit branch per state (amber for `pending`+`flagged`, coral for `investigating`), drop the "any truthy" shortcut. Right-click menu surfaces a "Flag → pending/flagged/investigating" submenu instead of a single Flag/Remove toggle. F7 Flags sub-tab filters drive off the same enum. — **RESOLVED 2026-05-20, revised after review.** The backend already shipped a 4-state enum (`pending/investigating/done/dismissed`) in B7, so the "three states" proposal was superseded. Final design (decided with the analyst): `status` is a 5-state lifecycle (`pending → flagged → investigating → done`, plus `dismissed`) and a **new `flags.source` column** (`watchlist`/`analyst`) carries provenance separately — splitting the two axes the old enum conflated. Constants live in `db/flags.py` (`VALID_STATUSES`/`VALID_SOURCES`/`ACTIVE_STATUSES`); FK-safe `flags`-table rebuild migration in `db/core.py::_migrate_flags_table`. Graph ring is 3-tone by status (dim amber `pending` / bright amber `flagged` / coral `investigating`). The right-click menu was kept lean — single-node offers `Flag — High/Medium/Low` (writes `flagged`) / `Remove Flag`; the `investigating`/`done`/`dismissed` transitions need the flag id and belong in the F6 right panel. `done`/`dismissed` have no UI yet — todo.md item 12.
5. **Workspace tabs are volatile across reload** — opened "testing" tab was gone after refresh. **Decision 2026-05-19: persist server-side.** Store the open-tab list under `settings.workspace.tabs` (array of `{kind, collection_id}` records) and the active tab under `settings.workspace.active`. On app load, restore tabs and call `workspaceStore.reconcileCollections(known)` against a fresh `listCollections()` — drop any tab whose collection has been deleted (the existing reconciliation toast handles this), fall back to `Global` if the active tab was dropped. Mirrors the filter-shelf persistence pattern; gives consistency across windows on the same machine.
6. ~~**Global → collection → Global has a ~1-2 s transient at 10/10**~~ **Shipped 2026-05-19 (SWR slices 2+3).** Per-tab payload + camera cache added to `workspaceSnapshots`; `onSwitch` applies the cached payload immediately (no flash); diff-update on poll return preserves positions; first-visit skeleton shown while loading; `invalidatePayloads()` called after `addGraphFilter` so hidden nodes can't reappear via the optimistic path. Retest: switch Global → collection → Global — no status-line flash; zoom level survives; dragged nodes hold position across polls.
7. **Escape doesn't exit ego-focus** when focus was entered via right-click → Focus. Worked via the × on the pill. F4a's keyboard handler may not be wired through this path. — **RESOLVED 2026-05-20.** The keydown handler is path-agnostic (right-click → Focus and the F key share `actFocus`), so the likely culprit was the `onKey` early-return for `INPUT/TEXTAREA` focus swallowing `Escape` while the ego-focus depth slider had focus. `GraphCanvas.onKey` now handles `Escape` *before* the form-control guard — Escape always exits draw-edge / ego-focus / selection regardless of where focus sits. Confirm in the manual browser pass.
8. **Group-by-domain N/A note is stale** — Slice 7 has shipped, the row is visible. Cluster nodes are synthesised client-side in `graphStore` so they do not appear with `is_cluster: true` in the raw `/api/graph` payload.
9. **Toolbar additions row is genuinely absent** (Draw edge, Expand to collection, Layout tabs, Export, Resume) — matches the archived historical build plan's F4b "in progress" note.
10. **Multi-select right-click not exercised** — shift+click on the dense halo layout kept being treated as camera drag. Needs a manual tester pass on a spread-out layout.

## 2026-05-20 F4b close-out — to verify

The three remaining F4b items shipped 2026-05-20 (flag model, infra-cluster
CSP normalization, Escape fix). `make test` is green (599 passed) and
`npm run check`/`build` are clean; these are the manual checks left.

- [ ] **Escape exits ego-focus from right-click → Focus** *(was finding #7)* —
  right-click a node → **Focus**; the ego-focus pill appears. Press
  `Escape` → ego-focus exits (without needing the × button). Then re-enter,
  click/drag the depth slider so it has focus, press `Escape` → still
  exits.
- [ ] **Flag ring is 3-tone by status** — with the Flagged-borders overlay
  on: a watchlist auto-flag (`pending`) draws a **dim-amber** ring, an
  analyst flag (`flagged`) a **bright-amber** ring, an `investigating` flag
  a **coral** ring.
- [ ] **Single-node Flag submenu** — right-click an *unflagged* node → the
  Investigation section shows `Flag — High` / `Flag — Medium` /
  `Flag — Low`; picking one flags the node (bright-amber ring on the next
  graph tick). Right-click a *flagged* node → a single `Remove Flag` row.
- [ ] **Flag All (multi-select)** — select ≥2 unflagged nodes, right-click
  within the selection → **Flag All** → each draws the bright-amber
  `flagged` ring.

Infra-cluster CSP normalization needs specific response headers to observe,
so it is covered by an automated test
(`test_b6_graph.py::test_infra_cluster_csp_normalized`) rather than a manual
step.

## Workspace tab bar

- [x] A tab bar sits above the graph toolbar with the `Global` tab present and active
- [x] `Global` cannot be closed (no ✕ shown)
- [x] `+` button opens the collection picker modal
- [x] Picking an unopened collection opens a new workspace tab and switches to it
- [x] Picking a collection that is already open switches to the existing tab (no duplicate)
- [x] `+ New collection…` row in the picker creates and opens the tab in one step
- [x] Closing a collection tab via ✕ removes the workspace but does NOT delete the collection (verify the collection still appears in the picker after closing its tab)
- [x] Switching tabs preserves each tab's node positions independently (pan/drag a node on Global, switch to a collection tab, switch back — the moved node sits where you left it)
+ Retest after halo-layout change (2026-05-17): the "cluttered mess on Global" complaint should be gone — stubs no longer fight FA2 for space, they orbit their parents.
- [x] Switching tabs preserves selection and ego-focus per tab
- [x] Activating a collection tab sets `workspaceStore.activeWorkspaceId` to the collection id — verify by reading the bottom-pane placeholder line `… (workspace: <id>)`. Bottom-pane Collection / Domains sub-tab *content* filtering still lands in F7; this checklist only verifies propagation here.
- [x] Toolbar scope chip — when on a collection tab, the collection name renders in `--accent` next to the status dot; on Global it disappears
- [x] Switching back to `Global` restores the full graph (all nodes, not just the collection's)
+ Retest after halo-layout change (2026-05-17): clutter should be much reduced — fetched nodes lay out as before, stubs orbit them in a halo instead of being shoved around by FA2.
+ Browser test 2026-05-19: status line flickered `10/10` for ~1-2 s. **Fixed 2026-05-19 by SWR slice 2** — cached Global payload applied instantly on switch, no flash.
- [ ] Deleting a collection elsewhere (e.g. via a future bottom-pane control) and then opening the picker again drops the tab and fires the toast. **Known limitation:** the auto-close fires on the *next picker open*, not the instant a delete happens elsewhere — there is no listener for cross-window deletes yet. Toast wording is `Collection "<name>" — workspace closed.`
+ dont think i can test this yet

## Collection-scoped graph view (slice 2+3)

- [x] With a collection tab active, the canvas shows ONLY that collection's members and the edges between them
- [x] DevTools Network — `/api/graph?collection_id=<id>` is the request fired on tab activation and on the 15 s tick
- [x] Switching from a collection tab back to Global re-fetches without `collection_id` and the canvas grows back to the full graph
- [x] Pan/zoom is preserved per tab — camera state captured on switch via `workspaceSnapshots` camera getter and restored via `camera.setState()` (not animatedReset) so the analyst's zoom survives tab switches. Initial fit still runs on first open; subsequent switches snap to the last camera position.
+ **Fixed 2026-05-19 by SWR slice 2.** Camera `{ x, y, ratio, angle }` stored in each tab's snapshot. Retest: zoom into a subgraph on Global, switch to a collection tab, switch back — zoom level should be exactly where you left it.

- [x] Empty collection tab → status line reads `0 nodes · 0 edges` and the canvas is blank (no error0)
- [?] Server returns 404 with `{error: "unknown_collection", collection_id: N}` if you `curl /api/graph?collection_id=99999` while authenticated
+ can you walk me through how to do this one.

## Crawl ↔ workspace wiring (slice 3.5)

- [x] Left-pane Crawl → "Add results to collection" dropdown **defaults to the active workspace's collection** when the dropdown is at `none`. Switching workspaces updates the suggestion; an explicit pick (a specific collection or `new`) survives workspace switches.
- [x] Start a crawl with a collection set → the collection's workspace tab auto-opens and becomes active
- [x] Start a crawl with `none` → no extra tab opens (still on Global)
- [x] Start a crawl into a `new` collection → the freshly-created collection's tab auto-opens
- [x] While a crawl is running into a collection, switch to Global → a `crawling → <name>` chip appears in the toolbar status line (accent pill)
- [x] Click the chip → the collection's tab opens / activates
- [ ] When the crawl finishes (status row drops back to no active crawl), the chip disappears

## Crawler populates the collection (slice 3.6)

- [ ] Crawl with a targeted collection → after the first page lands, the collection workspace tab's graph grows by one (within ~15 s)
+ Retest after halo-layout change (2026-05-17): a freshly-fetched page should appear at its FA2 position; any newly-discovered stubs from it should land in that page's halo on the same poll tick.
- [ ] DB sanity (optional): `SELECT COUNT(*) FROM collection_items WHERE collection_id = <cid>;` matches `pages_crawled` for the crawl
- [x] Stubs (discovered-but-not-crawled URLs) are NOT in `collection_items` — only successfully recorded pages

## Client-side filters (no refetch on toggle)

A filter shelf or popover lives off the toolbar. Toggling **any** filter
re-renders the graph from the already-fetched `/api/graph` payload — it
does NOT re-hit the API. Only the Hidden sub-tab's `graph_filters`
table is server-side.

### Topology

- [x] **Max hops** slider — depth from seed; updates immediately without a network request
- [x] **Show stubs** toggle (moved from toolbar into the filter shelf) — toolbar status line counts update on toggle
+ Fixed 2026-05-17 (halo layout): stubs no longer go through FA2, they orbit their parent fetched node. Expected: toggle is instant, no freeze, each fetched node sprouts a fan of small dots, fetched layout is unchanged. Retest with the 38k-stub Global graph.
+ Browser test 2026-05-19: 130 → 2351 nodes on toggle, status line updates instantly, zero new `/api/graph` requests fire.
- [x] **Hide orphans** — nodes with no rendered edges drop out and reappear without a fetch; status-line counts update
+ Browser test 2026-05-19: toggle state writes through, but no orphans exist in this dataset so node count was unchanged. Visual verification still needs a graph with at least one orphan.
- [x] **Mutual clusters only** — drops every node missing an in-edge OR an out-edge; the remaining set is fully reciprocal
+ Browser test 2026-05-19: 2351 → 92 nodes on toggle. No refetch.
- [x] **Edge mode** — `All` / `cross-site` / `same-site` switches rendered edges; node visibility cascades (hide-orphans + mutual react to the new edge set)
+ Browser test 2026-05-19: Cross-site = 2332/2368, Same-site = 70/72 (most edges in this DB are cross-site directory links). Orphan cascade works.
- [x] **Dedup edges per domain** — collapses parallel edges between two domains into one; toggle off and the multiplicity returns
+ Browser test 2026-05-19: 2351 → 109 nodes on toggle (with hide-orphans cascading). Restores on untoggle.
- [x] **Group by domain (cluster nodes)** — Slice 7 has shipped (filter shelf row is now visible). Toggling reduces count by the cluster-collapse delta (in this DB: 2351 → 2283 → 68 synthetic clusters).
+ N/A note is stale — row is no longer hidden. Cluster rendering ships via client-side `graphStore` synthesis (no `is_cluster: true` flag in `/api/graph` payload — clusters are created in the store).

### Colour

- [x] **Colour mode** — `Domain` / `Cluster` / `Depth` / `Category` / `Infra cluster`; each option recolours every node and the active option highlights in the shelf
- [!] All five colour modes produce visibly distinct palettes (depth runs a teal→deep gradient; the other four use the eight-hue categorical palette via a deterministic hash, so the same key reloads to the same colour)
+ Browser test 2026-05-19: spec / implementation mismatch.
+ — `Domain` mode is **intentionally a no-op**: `GraphCanvas.svelte:150-160` returns `raw.color` (backend monochrome tone) with a comment that domain-hash colouring "just adds noise". **Decision 2026-05-19: fix the renderer** — wire Domain mode to `categoricalColor(domain)` so it matches Cluster/Infra. Drop the "adds noise" comment. Re-test this row after the renderer change.
+ — `Cluster` and `Infra cluster` produce visibly distinct categorical palettes (verified on this DB — pink/teal/blue/yellow/orange groups).
+ — `Depth` palette runs only across 4 discrete levels (0/1/2/3); gradient is subtle and easy to miss with `Group by domain` on.
+ — `Category` shows no variance because every node in this DB has `category: null` (populated by `llm_worker.py:484`, no LLM jobs have run on this project). **Decision 2026-05-19: grey the colour-mode button + hover tooltip** when 0 nodes carry a value for the active mode's field. Generalise to any pipeline-fed field.
+ — Backend bug surfaced while probing: `infra_cluster_id` field stores the **raw Content-Security-Policy header text**, not a cluster id. Hashing is still stable because the hash treats it as opaque, but the field name lies. **Decision 2026-05-19: normalise + SHA1 at write time** (parse CSP, sort directives, strip whitespace, drop nonces) and migrate existing rows via a one-shot backfill.
- [ ] Switching colour mode does NOT alter `selection` / `hover` / `ego-focus` styling — those overrides win over the colour-mode fill

### Overlays

- [x] **Flagged borders** — flagged nodes draw a coloured **ring** (amber `#ffb852` for `flagged`, coral `#fb7185` for `investigating`) around the node. The underlying node fill stays whatever the active colour mode produced — colour mode + flag overlay coexist
+ Verification path until the right-click **Flag** menu ships: flag a node by hand against the project DB, e.g. `sqlite3 <project>.db "UPDATE nodes SET flag_status='flagged' WHERE id=<n>;"` then wait one 15 s poll tick (or hit Reset) and toggle the overlay. Re-test after the single-node context menu lands and remove this line.
+ Browser test 2026-05-19: renderer code path confirmed (`GraphCanvas.svelte:526-529`) — any truthy `flag_status` gets a ring, coral for `'investigating'` else amber. But note: `createFlag` writes `status: 'pending'` (`GraphCanvas.svelte:1100, 1197`), not `'flagged'` per spec — the enum has drifted. Renderer covers it because it only checks truthiness, but standardise on one set of strings. **Decision 2026-05-19: three-state enum** (`pending`/`flagged`/`investigating`) lifted into shared backend + frontend constants modules. Right-click menu becomes a Flag-state submenu instead of a binary toggle.
- [ ] **Flagged borders** — toggling the overlay off restores the un-bordered look; flagging a node while the overlay is on shows the ring on the next graph tick without a refetch
- [x] **Isolate** — with the overlay on and **nothing selected**, hovering a node fades non-neighbours harder than the default hover-dim; leave the node and the dim recedes (animated)
+ Browser test 2026-05-19: confirmed — hover snapped non-neighbours to a hard dim, leaving the hovered node bright.
- [ ] **Isolate** — with the overlay on and **a node selected** (no hover), every non-selected, non-neighbour node snaps to the hard-dim target until the selection clears. Cursor parked off-canvas — the dim still holds. Behaviour is *snap*, not faded, because selection itself is sticky/unanimated
- [ ] **Isolate** — multi-select grows the bright set (selection ∪ each selected node's neighbours); deselecting (click empty canvas) restores full opacity
- [ ] **Isolate** — toggling the overlay off while a selection is held immediately restores full opacity without needing to deselect
- [x] **Bridge highlight** — uses `is_bridge` plus the two threshold sliders in the shelf (`betweenness`, `in_degree`); bumping the thresholds shrinks the highlighted set in real time
+ Browser test 2026-05-19: toggle on exposes the min-betweenness slider. Threshold drag not specifically exercised — leave as smoke-only until real bridge nodes are visible in viewport.

### Persistence + zero refetch

- [x] Every shelf setting persists under `settings.graph.*` and rehydrates on reload (dirty every control, refresh the page, confirm each control returns to its last value)
+ Browser test 2026-05-19: persistence is server-side via `/api/settings/:key` (not localStorage — `localStorage` stays empty). Reload kept Show stubs / Hide orphans / Group by domain / Infra cluster mode / Flagged borders / Isolate hover/selection all on.
+ Tangent: workspace tabs do NOT persist across reload (the opened "testing" tab was gone). **Decision 2026-05-19: persist server-side** under `settings.workspace.tabs` + `settings.workspace.active`, reconcile against `listCollections()` on load.
- [x] DevTools Network → filter `/api/graph` → toggle every shelf control end-to-end → zero new requests fire
+ Browser test 2026-05-19: confirmed via `read_network_requests` — only the 15 s poll fires; no toggle re-hit `/api/graph`.

## Node rendering

- [ ] All five colour modes from the filter shelf produce visibly distinct palettes (also covered in the Colour subsection above; this line is the cross-section sanity check)
- [ ] Selected colour mode persists in `settings.graph.color`
- [ ] Flagged nodes render their coloured ring via `@sigma/node-border` (`BorderedNodeProgram`); ring is rendered outside the fill so the colour-mode hue stays intact. The bordered program is opt-in per node (`type: 'bordered'` set in the reducer only when the flag overlay applies) — unflagged nodes stay on sigma's default circle program.
- [ ] **No AA regression on unflagged nodes** — flip the Flagged borders overlay on with at least one flagged + many unflagged nodes in view. Unflagged node outlines should look identical to before the flagged-borders work (no stair-step / pixelation on the rim). If they look stepped, the bordered program has likely been re-set as `defaultNodeType` — its transparent-outer-layer AA collapses the fill→transparent gradient into a hard edge.
- [N/A — addressed differently] Dashed stub stroke — superseded by the halo layout (2026-05-17, see `docs/work/archive/2026-05-20-fixes/checklist.md` §4). Stubs render as size-2.5 dots orbiting their parent fetched node; the size + position already encode "this is a stub", no dashed stroke needed.
- [N/A — blocked] `analysis_excluded` ⊘ overlay — the render branch (`if analysis_excluded → draw ⊘`) is in place ready for visual sign-off, but cannot be exercised until the AI Analysis feature sets the flag (`docs/work/archive/2026-05-20-fixes/checklist.md` §5)

## Domain cluster nodes

- [ ] With **Group by domain** on, multi-page domains collapse into a single cluster node (`is_cluster = true`)
- [ ] Cluster nodes render with a distinct shape/size from individual pages
- [ ] Double-clicking a cluster node expands it, replacing the cluster with its individual pages
- [ ] Double-clicking again (or via context menu) re-collapses
- [ ] Single-domain entries (1 page only) do NOT cluster
- [ ] Stub nodes are excluded from cluster metrics (consistent with F4a stub policy)

## Toolbar additions

### Draw analyst edge (Spline icon)

- [ ] **Sequential mode** (0 or 1 nodes selected): clicking the icon enters draw mode; status line is replaced by "Click source node"
- [ ] Click a source node → status line becomes "Click destination node"; source highlights in canvas
- [ ] Click a destination node → Draw Analyst Edge modal opens showing `source URL → destination URL`
- [ ] **Batch mode** (≥2 nodes selected): clicking the icon opens the modal immediately with "Connect N selected nodes — will create M edges" and the URL list
- [ ] Pressing `Escape` while in sequential mode exits cleanly; status line restores
- [ ] Cancel button on the modal closes it; selection and graph unchanged

### Expand to collection (FolderPlus icon)

- [ ] Button is disabled while no node is selected
- [ ] Clicking opens a popover anchored to the toolbar button
- [ ] Collection dropdown is pre-filled with the current workspace collection when a collection tab is active; blank on `Global`
- [ ] Hops selector offers 1 / 2 / 3
- [ ] `+ New collection` option at the bottom of the dropdown creates one inline via name input + Enter
- [ ] `Add to collection` button is disabled until a collection is chosen
- [ ] Clicking Add adds every node within the hop radius to the chosen collection; toast confirms the count

### Layout picker (dropdown)

- [ ] Five layout options in the dropdown: `Force` / `Radial` / `Hierarchical` / `Concentric` / `Timeline`
- [ ] `Force` (default) — ForceAtlas2 runs in a Web Worker and settles; the page never freezes during the settle
- [ ] While Force is settling a **Stop** button appears in the toolbar; clicking it freezes the layout where it is
- [ ] `Radial` — pages grouped into per-domain hubs on a ring; applies instantly
- [ ] `Hierarchical` — top-down tiers by crawl depth (depth 0 at the top)
- [ ] `Concentric` — rings by crawl depth; depth 0 at centre
- [ ] `Timeline` — nodes positioned by `first_seen` down the y-axis, same-day nodes spread along x; legend appears bottom-centre with date range, day count, and undated count
- [ ] Picking a layout re-lays-out immediately; the choice survives a page reload (persisted as `settings.graph.layout`)
- [ ] `Reset layout` (RotateCcw) re-runs whichever layout is currently selected

### Export dropdown (Download icon)

- [ ] Click opens a small dropdown
- [ ] `GEXF (.gexf)` downloads the full graph as GEXF (server export — honours the Hidden/`graph_filters` set, not the client-side filter shelf)
- [ ] `Nodes CSV (.csv)` downloads a flat CSV of the graph's nodes

### Resume button (already in F4a)

- [ ] Visible only when kill-switch FSM is in `cleared_idle`; hidden in `armed` and `tripped`
- [ ] Clicking transitions FSM to `armed` and re-arms the graph poller plus any user-started crawl/worker the user explicitly resumes elsewhere

## Right-click context menus

### Single node menu

Stateful items show their current state in the label. Dividers carry labels.

Slice 1 shipped (2026-05-18): items that don't need a separate modal /
external launcher. The Tor-launcher, alias popover, Add Monitor, Queue
Analysis, and Clear Analyses items are intentionally absent from the
rendered menu until their modal/service slices land — `buildSingleNodeSections`
in `GraphCanvas.svelte` only emits the implemented rows, no greyed placeholders
for slice-1 items.

- [~] **Copy URL** — copies URL to clipboard; toast confirms
+ Browser test 2026-05-19: row present in rendered menu (`ref_119` neighbourhood). Not clicked end-to-end; clipboard write/toast unverified.
- [~] **Open in Tor Browser** — launches the configured browser (default: Tor Browser, auto-discovered from canonical install paths); records `opened_at`. Refuses with toast `Open failed: tor_unavailable` when the kill switch is engaged; row is greyed out with tooltip `Tor not connected` in the same state. Backend: `POST /api/nodes/:id/open` (slice 4 shipped 2026-05-18). Browser-change UI is deferred — `browser.path` setting can be hand-set via the API today, the future F5 Settings → Browser tab will surface it. **Reminder:** when that lands, swap the route's cached kill-switch read for a fresh `probe_now()` because non-Tor browsers don't self-isolate the same way Tor Browser does (see `docs/work/archive/2026-05-20-todo/outcome.md` item 11).
+ Browser test 2026-05-19: row rendered. Not clicked (didn't want to launch Tor Browser mid-test).
- [N/A — inline alias popover not yet built] **Rename alias…** — opens inline popover, pre-filled with current alias; Enter saves; Escape closes. Backend `PATCH /api/domains/:host` already exists (see `routes/domains.py:71`); only the inline popover component is missing.
- [x] **— CRAWL —** divider label visible
- [x] **Queue Crawl** — present on stub nodes only; queues this URL as a seed
+ Row is always rendered; greyed with reason "Already crawled" on non-stubs.
+ Browser test 2026-05-19: row rendered under CRAWL divider on the right-clicked node (a flagged crawled page).
- [x] **Save as Seed Bookmark** — saves the URL to the crawl bookmarks list
- [x] **— INVESTIGATION —** divider label visible
- [x] **Flag** / **Remove Flag** — label flips based on current `flag_status`
+ Browser test 2026-05-19: confirmed — menu showed `Remove Flag` on a node whose `flag_status` was truthy. Label flip works.
- [~] **Mark Reviewed** / **Mark Unreviewed** — label flips based on current reviewed state
+ Browser test 2026-05-19: row rendered as `Mark Reviewed`. Label flip not exercised (didn't click).
- [N/A — Add Monitor modal pending] **Add Monitor…** — opens the Add Monitor modal pre-filled with this URL (works on stubs too)
- [N/A — Queue Analysis modal pending] **— ANALYSIS —** divider label visible (divider is suppressed until at least one Analysis item is implemented)
- [N/A — Queue Analysis modal pending] **Queue Analysis** — queues an AI analysis job; on stub nodes the job sits in `waiting` and fires automatically once the stub is crawled. Backend `POST /api/analyses` exists; only the modal is missing.
- [N/A — pairs with Queue Analysis] **Clear Analyses** — deletes all AI analyses for this node. Backend `DELETE /api/analyses/:id` exists per-row; needs a node-scoped bulk endpoint or N parallel deletes.
- [x] **— GRAPH —** divider label visible
- [x] **Focus** — enters ego-focus mode for this node (parity with F4a left-click)
+ Browser test 2026-05-19: clicked, ego-focus pill appeared at top of canvas with depth slider, target node went orange, node count filtered to 747/746 at depth 2. Parity with left-click confirmed.
+ Bug observed: Escape did not exit ego-focus when entered via right-click → Focus. Had to use the × on the pill. F4a's keyboard handler may not be wired through this entry path.
- [x] **Hide from Graph** — present on crawled nodes only; adds URL as a graph filter term (server-side `graph_filters` row); node disappears immediately
+ Row is always rendered; greyed with reason "Crawled nodes only" on stubs.
+ Browser test 2026-05-19: row rendered. Not exercised (didn't want to remove a node mid-test).

### Multi-select menu (≥2 nodes selected)

Items that don't apply to the current selection are **greyed out with a
short reason** (not hidden).

Slice 2 shipped (2026-05-18): the four direct-action items (Crawl
selected, Flag All, Mark Reviewed, Hide All) plus the disabled
placeholders for the three modal-backed items. The right-click handler
picks the multi menu only when the right-clicked node is part of the
existing ≥ 2 selection — right-clicking outside the set falls back to
the single-node menu for that specific node (file-manager convention).
Item labels carry counts (`Flag All (5)`, `Mark Reviewed (3)` etc.) so
the analyst sees the operating set before clicking.

- [N/A — Collection picker modal pending] **Add to Collection** — opens the Collection picker; adds all selected nodes (stubs and crawled). Disabled placeholder row is rendered today with reason "Collection picker modal not yet implemented".
- [N/A — Draw analyst edge modal pending] **Draw Edge…** — opens the Draw Analyst Edge modal in batch mode; creates a fully-connected set of analyst edges across the selection. Disabled placeholder row is rendered today.
- [ ] **— CRAWL —** divider label visible
- [ ] **Crawl selected** — queues all stub nodes in the selection; greyed with reason if no stubs selected; toast: "Queued N URLs for crawl."
+ Crawler is one-active-at-a-time (`backend/routes/crawl.py:94`), so the second+ stub in a multi-stub selection lands as `(N skipped — crawl in progress)` in the toast. That phrasing is intentional — surfaces the limit instead of silently failing.
- [ ] **— INVESTIGATION —** divider label visible
- [ ] **Flag All** — flags all selected (stubs and crawled) immediately
+ Already-flagged nodes are skipped so a repeat click doesn't multiply flag rows; toast reports `Flagged N (M already flagged)` when that happens.
- [ ] **Mark Reviewed** — applies to crawled nodes; greyed with reason if selection is all stubs
+ Toast reports `Marked N reviewed (… stubs excluded)` for mixed selections; already-reviewed nodes are skipped.
- [ ] **— ANALYSIS —** divider label visible
- [N/A — Queue Analysis modal pending] **Queue Analysis…** — opens the Queue Analysis modal; stubs receive `waiting` jobs; count in toast excludes stubs. Disabled placeholder row is rendered today.
- [ ] **— GRAPH —** divider label visible
- [ ] **Hide All** — adds all crawled nodes to the graph filter; greyed with reason if selection is all stubs
+ 409 responses (already hidden) and stub exclusions surface in the toast as `Hidden N from graph (M already hidden, K stubs excluded)`.

### Analyst edge menu

- [ ] Right-clicking a dashed analyst edge (source = `analyst`) shows a menu with "Delete analyst edge"
- [ ] Right-clicking a crawl-derived edge shows nothing (or no edge-specific menu)
- [ ] Deleting removes the edge from the graph immediately
+ Slice 3 wired (2026-05-18): `enableEdgeEvents: true` on the Sigma renderer + `rightClickEdge` handler in `GraphCanvas.svelte`. A separate `edgeMenu` state drives a `NodeContextMenu` instance with a single "Delete analyst edge" item; non-analyst edges suppress both the browser and Sigma defaults but don't open the menu. The action calls `DELETE /api/edges` then triggers `graphPoller.refresh()` so the canvas drops the edge on the same tick instead of waiting for the next 15 s poll. `edgeMenuSections` re-reads the raw edge on every `graphStore.version` bump so a poll landing between right-click and click closes the menu rather than acting on a stale edge.

## Shared modals (`frontend/src/components/modals/`)

All four modals live under `frontend/src/components/modals/` and are
imported by the graph context menus, F6 right panel, and F7 bottom pane.
The Add Monitor modal must be the same component used by the Domain tab.

### CollectionPicker.svelte

- [ ] Extracted from the F3 inline picker (historical build-plan backlog item)
- [ ] Lists all collections
- [ ] Includes `+ New collection…` inline at the bottom
- [ ] Supports a single URL (search/result row) and bulk (multi-select)
- [ ] F3 Crawl sub-tab still works after the extraction (no regression)

### AddMonitor.svelte

- [ ] **URL** field, pre-filled, read-only
- [ ] **Label** — optional text input
- [ ] **Interval** — hours between checks; min `0.25`, default `24`
- [ ] **Alert on content change** checkbox, default on
- [ ] **Alert on restore** checkbox, default on
- [ ] **Downtime alert after N hours** number input, default `48`
- [ ] **Add** / **Cancel** buttons
- [ ] Domain tab's Add Monitor form renders the same component

### QueueAnalysis.svelte

- [ ] **Type** dropdown — Summary / Risk Score / Entities / Category / Domain Label / Q&A
- [ ] **Question** text input appears only when `Q&A` is selected; required when shown; applied to every selected node
- [ ] **Skip already-queued** checkbox, default on
- [ ] **Queue N nodes** button — count excludes stubs in the label
- [ ] On confirm, toast reads: "Queued summary for 14 nodes (2 skipped — already queued, 3 stubs excluded)."
- [ ] Jobs land in the `analyses` table and appear in the bottom-pane Analyses sub-tab and Intel queue

### DrawAnalystEdge.svelte

- [ ] Sequential mode: shows `source URL → destination URL`
- [ ] Batch mode: shows "Connect N selected nodes — will create M edges" plus the URL list
- [ ] **Type** select — `Same operator` / `Shared wallet` / `Mirrors` / `Affiliate` / `Custom…`
- [ ] Choosing `Custom…` reveals a free-text **Label** input; the label applies to every created edge
- [ ] `Create` adds dashed green edges; batch mode creates a fully-connected set across every pair in the selection
- [ ] `Cancel` closes the modal; selection and graph unchanged

## Cross-window graph sync after crawl (`checklist-fixes.md` §7)

Folded into F4b because the fix sits inside the same poller lifecycle
that the workspace tab bar and filter shelf already touch.

- [ ] Open the app in two browser windows
- [ ] Start a crawl in Window A
- [ ] Switch focus to Window B → graph reflects the new nodes within one 15 s tick of receiving focus
- [ ] DevTools Network in Window B confirms `/api/graph` is being hit on tick after refocus
- [ ] Confirm investigation order from §7 — tab visibility throttling addressed (visibilitychange refetch), no stale `kill_switch.engaged` pause, no 304/cached response

## Build sanity

- [ ] `cd frontend && npm run check` — 0 errors, 0 warnings
- [ ] `cd frontend && npm run build` completes; `backend/public/` contains exactly `bundle.js`, `bundle.css`, `index.html`
- [ ] No additional `.js` or `.css` chunks under `backend/public/`

## Known gaps (do NOT file as bugs — these are post-F4b)

- Right panel body — placeholder until F6 (single-node Page/Domain/Analysis tabs and the cluster workspace for multi-select)
- AI Analysis itself — when it lands it will unblock the `analysis_excluded` ⊘ overlay (`checklist-fixes.md` §5) and exercise the Queue Analysis modal end-to-end
- Stub dashed outline — superseded by the halo layout (`checklist-fixes.md` §4, 2026-05-17). Stubs render as size-2.5 dots orbiting their parent; dashed outline is no longer load-bearing.
- Bottom-pane Collection / Domains real wiring — F7; this checklist only verifies that the workspace tab bar propagates the right `activeWorkspaceId` and `BottomTab` state
- Left-pane Settings modal Graph tab — F5; the filter shelf in F4b uses an inline popover, not the Settings modal
