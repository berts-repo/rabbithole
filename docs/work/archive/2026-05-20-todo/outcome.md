1. collapsible bars for bottom and left pane
   DONE (2026-05-20). Collapse/expand/toggle for left, right AND bottom
   panes was already implemented (`layout.svelte.ts`; collapsed rails +
   buttons in `LeftSidebar`/`BottomPane`/`RightPanel`). Verification in
   the browser surfaced a real layout bug: `AppShell` declared 5 grid row
   tracks but `TorBanner` rendered *nothing* when Tor was reachable, so
   `.shell` had only 4 children — every row shifted up one track, `.main`
   fell out of the `1fr` row into an `auto` row and stopped stretching.
   Symptoms: collapsing the bottom pane left a dead gap above the rail;
   collapsing left+bottom together shrank the canvas to a thin banner.
   Fixed by removing TorBanner (item 4 below) → stable 4-row grid
   (`auto 1fr auto var(--bottom-h)`). svelte-check clean; verified live.
2. in the graph when focused after clicking left click when I move the cursor off the node it brightens all the nodes again which is correct, but it is removing the highlighting of that node and its edges, it needs to keep the node and edges highlighted until you click the canvas or close out of focus.
   DONE (2026-05-20). No persistence bug remains. The selection model
   changed since this was filed — plain left-click no longer enters
   ego-focus (focus is its own gesture: F key / right-click → Focus).
   The focus root stays selected, and `edgeReducer`'s sticky ego-focus
   branch (`GraphCanvas.svelte:698-706`) keeps every edge touching the
   root teal regardless of hover, so the focused node and its edges
   already persist until a canvas click or focus-exit. Confirmed with
   the analyst. Only change made: swapped the selected-node fill from
   deep-orange `#f97316` to electric-green `#39ff14` (user preference)
   — single colour constant + comment in `GraphCanvas.svelte`
   `nodeReducer`.
3. when a node is focused and you hover over another node it needs to highlight the edges making a connection to the two (or multislect and hover)
   DONE (2026-05-20). Single-source path-on-hover was already built
   (`updatePathForHover` + `shortestPathEdges` in `GraphCanvas.svelte`;
   path edges lit bright teal `#7df3d0` in `edgeReducer`, sticky against
   the hover-dim) — focus root or highlighted selection → hovered node.
   This pass added the "(multiselect and hover)" case: with ≥ 2 nodes
   selected, `updatePathForHover` now unions the shortest path from
   *every* selected node to the hovered node. Capped at
   `MAX_MULTI_PATH_SOURCES = 50` (mirrors the select-all confirmation
   threshold) — above it, falls back to the single representative source
   to avoid lighting most of the graph and an N× BFS fan-out on each
   hover. svelte-check clean.

3. issue and bug when a node is selected and focused and i go into another desktop window it will disappear. UPDATE 2026-05-17: not just a desktop-switch trigger — it also happens after a period of idle time with the window in the foreground. Clicking the canvas brings the focused node back either way. Suggests Sigma's rAF loop is being throttled/paused by more than the cross-desktop compositor case (browser idle/inactive-tab rAF throttling, or our own invalidation effect not re-running on idle). Diagnose alongside item 5 (a).
   RESOLVED (2026-05-20). The desktop-switch trigger is patched:
   `GraphCanvas.svelte` registers `visibilitychange` + window `focus`
   listeners (`onPageVisible` / `onWindowFocus`) that clear `egoCache`
   and force a `renderer.refresh()` on return. The idle-in-foreground
   trigger is no longer reproducible per the analyst — likely
   incidentally fixed by changes since the 2026-05-17 note, or always
   rare. Closed on the analyst's hands-on observation; item 5's
   canvas-refresh redesign still nets this case if it ever resurfaces.

4. yellow tor banner is now redundant and wasted code space
   DONE (2026-05-20). Deleted `TorBanner.svelte` (~82 lines) + its
   `AppShell` import and grid slot. The kill-switch modal
   (`KillSwitchAlert`) already covers both the enforced and
   enforcement-off Tor-loss cases; the header Tor pill is the persistent
   indicator after the modal is acknowledged. Moved the
   `sudo systemctl start tor` recovery hint into the modal body so no
   guidance was lost. Updated TorBanner references in the comments of
   `pollers/torStatus.svelte.ts` and `pollers/killSwitch.svelte.ts`.
   This also eliminated the AppShell grid bug (see item 1).
4. when I killed tor it took about 7 seconds before i got the alert, would this be normal? We need to be sure somehow. Another thing, when I restored the tor connection and hit the banner's 'Retry connection' it states "tor reachable - waiting for backend monitor to clear" and it doesn't close out of banner or do anyhthing else, but 'acknowledge' and the 'x' button work.
   RESOLVED (2026-05-20). Both halves handled.
   • 7 s lag — working as designed. `kill_switch.py` probes Tor every
     5 s (`_PROBE_INTERVAL_SECONDS`) and trips only after 3 consecutive
     failures (`_FAIL_THRESHOLD`), so one flaky probe can't false-trip
     and kill a live crawl. Worst case ~10–15 s; the observed ~7 s is a
     fast case within tolerance. Analyst chose to keep the constants.
   • 'Retry connection' hang — fixed. `KillSwitchAlert.onRetry()` calls
     `probeTor()` → `POST /api/tor/probe`; `KillSwitch.probe_now()`
     runs a synchronous probe and publishes `kill_switch.clear` before
     the HTTP response returns. `killSwitch.svelte.ts` holds its own
     EventSource, structurally outside the shared SSE manager's
     `pauseAll()`, so the clear event can no longer be delivered to a
     closed stream (the old "Waiting for monitor… forever" hang). The
     modal auto-closes on a successful Retry. Closed on code review.

4. kill-switch crawl controls still get stuck after Tor is killed. Current behavior observed on 2026-05-17: the crawl itself stops after about 15 seconds, the Tor bullet flips to off, and the LLM crawl stops, but the left-pane Crawl controls remain in the "Stop" state: the stop button stays highlighted and Start cannot be pressed. The Explore graph status bar light also keeps flashing yellow as if crawling is still active. If the analyst clicks the still-red Stop button in this stale state, the UI throws `Stop failed: api error 404`, which confirms the frontend still thinks there is an active crawl after the backend has already torn it down. This stale-running state also appears to make unrelated graph/workspace checks fail spuriously, including the checklist item "Switching back to `Global` restores the full graph (all nodes, not just the collection's)" in situations where that normally is not broken. Likely frontend state bug/race around kill-switch trip versus crawl terminal-state propagation; keep this tracked even if partially mitigated.

   ROOT CAUSE (investigated 2026-05-18): SSE pipeline race.
   `kill_switch.engaged` and `crawl.status: stopped` both publish to the
   same `/api/crawl/events` stream. The engaged event arrives first, the
   FE handler calls `sse.pauseAll()` which actively closes every
   EventSource (intentional safety behavior per checklist-fixes §6), and
   the trailing `crawl.status: stopped` is dropped on the floor.
   `crawlStore.lifecycleStatus` stays `running`, `polledActiveRow` never
   clears, every UI surface keyed off `crawlStore.running` stays stuck.
   The 404 is the same race: backend has torn the crawl down, FE still
   thinks one exists.

   RESOLVED (2026-05-20). Fixed with a lean frontend-reconciliation
   approach. Option D (a backend "cancelled tasks" contract on the
   `engaged` payload) was rejected on implementation review: heavier
   (~6 files) AND incorrect — warn-only mode force-cancels nothing, so
   its `cancelled` list would be empty while the crawl still stops (the
   crawl loop exits on the shared `engaged` flag regardless of
   enforcement). The trip event is itself a sufficient signal: a Tor-loss
   trip always ends any running crawl, so the FE reconciles `crawlStore`
   directly instead of depending on the `crawl.status: stopped` SSE event
   that `sse.pauseAll()` drops. What shipped:
     • `crawl.svelte.ts` — new `crawlStore.markStopped()`: sets
       `lifecycleStatus = 'stopped'`, clears `polledActiveRow`. Mirrors
       the SSE terminal-status branch — same end state a normal Stop
       reaches.
     • `pollers/killSwitch.svelte.ts` — on `engaged`/`banner`, calls
       `markStopped()` when a crawl is running, before
       `tripKillSwitch()`. No engaged/banner split needed: both halt the
       crawl.
     • `routes/crawl.py` — `POST /api/crawl/stop` is now idempotent:
       returns `{ok, already_stopped}` instead of 404 when no crawl is
       active. Kills the stale-click `Stop failed: 404` toast.
     • `CrawlControls.svelte` — Start is disabled while the kill switch
       is engaged (phase ≠ `armed`), with an explanatory tooltip; you
       re-arm after Tor recovers, then start.
     • Copy fixes — `KillSwitchAlert.svelte` enforcement-off text and the
       `kill_switch.py` docstring no longer claim the crawl "continues"
       in warn-only mode. It halts; enforcement only controls mid-stream
       abort vs. graceful drain (analyst decision, 2026-05-20).
   Test: `test_b5c_routes.py` stop-when-idle case updated (404 → 200
   `{ok, already_stopped}`); `engaged`/`banner` payload shape unchanged.
   svelte-check clean; backend crawl + kill-switch suites green. The
   broader canvas/state-staleness unification remains item 5.

5. canvas-refresh trigger: unify the "graph canvas is stale" problem across cases

   Problem: the graph canvas can get out of sync with current state in
   at least three situations, and right now each one is (or would be)
   patched separately:
     a) Sigma's rAF loop goes idle and the focused node disappears
        until the canvas is clicked. Originally observed only when
        switching virtual desktops and returning (compositor pauses
        rAF), but per the 2026-05-17 update to item 3 it also fires
        after plain idle time with the window in the foreground — so
        the trigger set is broader than desktop-switch (likely browser
        rAF throttling and/or our own ego-focus invalidation effect
        not re-running on idle).
     b) during a crawl — new nodes/edges land in the backend and the
        15 s frontend poller fetches them, but the canvas does not
        always visibly update.
     c) cross-window graph sync (already tracked as §7 of
        docs/work/archive/2026-05-20-fixes/checklist.md) — Window B doesn't reflect Window A's
        crawl results until refocus.

   Each of these is a "the canvas should be showing newer state than
   it is" symptom with a different trigger. Rather than patching each
   one with its own timer or listener, do one of:

     • event-driven canvas invalidation. Whenever ANY of these happen,
       emit a single "invalidate" signal that the GraphCanvas picks
       up: new /api/graph payload version, crawl SSE event lands,
       window/workspace returns, kill-switch transitions. Sigma's
       refresh() becomes a subscriber to that signal. No timers.
     • or: tie graph refresh to the SSE event stream the backend
       already publishes for crawl progress / kill-switch state, and
       use a single browser-level "resumed" event (probably
       `webglcontextrestored` or `pointerenter` on the canvas) to
       cover the desktop-switch case. Same idea, narrower scope.

   The goal is one mechanism that covers all three, not three patches.
   Will come back to this — don't worry about it now. UPDATE
   2026-05-20: case (a) is now effectively handled — the desktop-switch
   half IS patched (`visibilitychange` + window-`focus` listeners →
   refresh) and the idle-in-foreground half is no longer reproducible
   (item 3 closed). The unification below still stands for cases (b)
   and (c); revisit when we sit down with this.

   Tried-and-removed (so you don't redo it): a 2 s `setInterval` in
   `GraphCanvas.svelte` that called `renderer.refresh()` while ego-focus
   was active. It worked for case (a) but was rejected as a placeholder
   — wasteful (repaints whether or not anything changed), doesn't help
   (b) or (c), and dodges the underlying "what's the right event to
   react to" question. The code was never committed; the shape was a
   `$effect(() => { if (!graphStore.egoFocus) return; const id =
   setInterval(() => renderer?.refresh(), 2000); return () =>
   clearInterval(id); })` attached after the existing `egoFocus`
   invalidation effect.

6. REVIEW DECISION (added 2026-05-17): the kill-switch retry path now
   calls a new `POST /api/tor/probe` endpoint. The backend runs a
   synchronous probe on demand and publishes `kill_switch.clear` before
   the response returns, so the modal closes within one round trip
   instead of waiting up to one 5 s background interval.

   Why this might need revisiting:
     - Adds a second entry point to `KillSwitch._tick()` (the route can
       now race with the background loop). Today it's "last write wins"
       on `_consec_failures` and `last_probe`, which is fine for the
       retry case but is implicit. If we ever add more on-demand probe
       callers, consider an `asyncio.Lock` around `_tick()`.
     - It's a single-purpose fix for the Tor modal. The "frontend asks
       backend to force a refresh" pattern could be generalized (force-
       refresh LLM/embed/crawler state), but no other caller wants it
       yet — keep an eye out for a second use case before generalizing.
     - The original 7 s detection-on-loss lag is NOT addressed by this
       change. Recovery is now fast; loss detection still takes 5–15 s
       (5 s probe × 3-fail threshold). Tightening those backend
       constants was discussed and deferred.

   Files touched: `backend/backend/services/kill_switch.py` (added
   `probe_now`), `backend/backend/routes/sse.py` (added route),
   `frontend/src/lib/api/` (added `probeTor`),
   `frontend/src/components/KillSwitchAlert.svelte` (uses `probeTor`).

7. Explore feature: preload the Crawl bookmarks dropdown with the
   global collection's primary/default seeds.

   Goal: when the analyst opens bookmarks on the Crawl tab, the list is
   already seeded with the global collection's canonical starting URLs
   instead of requiring them to save each one manually first.

   Open questions:
     - Do these appear as normal saved bookmarks, or as a separate
       read-only/preloaded section above user-saved seeds?
     - What is the source of truth for "primary/default" on the global
       collection: explicit collection metadata, first N items, or a
       dedicated seed flag?
     - Should preloaded seeds auto-refresh when the global collection
       changes, or only on app/project load?
     - If the analyst deletes one from bookmarks, is that hiding the
       preload locally or mutating the collection-level default?

8. Collection-tab crawl visibility: if a crawl is actively running into
   a collection tab/workspace, we may need a way to see stub nodes there
   before they are fully crawled/populated. Track whether collection
   views should expose in-flight stubs, how they should be styled, and
   whether this is gated behind a toggle/filter versus always visible
   during the crawl.

9. Graph layout selector: add a filter shelf control to switch between layout
   algorithms. Currently using the radial layout (domain clusters on a ring).
   The original ForceAtlas2 layout should be available as a second option.

   UI pattern: segmented button group in the filter shelf using the same
   `.seg` / `.active` pattern as `colorMode` and `edgeMode`. Add `LayoutMode`
   type + state to `graphFilters.svelte.ts`; branch on it in
   `applyPayloadAndLayout` in `GraphCanvas.svelte`; no backend persistence
   needed (session preference).

   **User-perspective notes (2026-05-18) — why two modes earn their keep:**

   - *Radial-by-domain (current default):* every domain becomes a small
     solar system. Domain hub (or first node if no cluster exists) sits
     at the centre of a sunflower spiral of that domain's pages; the
     hubs themselves sit evenly spaced on an outer ring. **Deterministic
     — same project lays out the same way every session.** Domain
     membership is the dominant visual signal: at a glance the analyst
     reads "here's everything from site A, here's everything from site
     B." Best for: domain-first investigations, repeat sessions where
     spatial memory matters, screenshots/exports, demos.
   - *ForceAtlas2 (to restore):* nodes settle under simulated forces —
     edges pull connected things together, repulsion pushes everything
     else apart. Non-deterministic across sessions; clusters emerge
     from *connectivity*, not domain. A heavily-linked pair across two
     sites lands visibly closer than an unrelated pair. Best for:
     finding cross-domain link structure, bridging nodes, surprise
     adjacencies the analyst didn't expect.
   - *Default choice:* keep radial as the default — it's faster (no
     iteration loop), deterministic, and matches the operator-privacy
     framing where the same analyst returning to the same project
     should see the same picture. FA2 is the "what links to what"
     drill-down view.
   - *Label copy suggestion:* `Domain` / `Force` rather than `Radial` /
     `ForceAtlas2` — domain-clustering and force-directed are what the
     analyst is choosing between, not algorithm names.

   **Original FA2 code to restore** (removed 2026-05-18, was in
   `GraphCanvas.svelte` inside the `shouldLayout && fetchedCount > 0` branch):

   Import:
   ```ts
   import forceAtlas2 from 'graphology-layout-forceatlas2';
   ```

   Constants:
   ```ts
   const LAYOUT_ITERATIONS = 300;
   const MAX_AUTO_LAYOUT_NODES = 3000;
   ```

   Layout call (replaces `radialLayoutByDomain(g)`):
   ```ts
   const layoutGraph = buildFetchedLayoutGraph(g);
   forceAtlas2.assign(layoutGraph, {
     iterations: LAYOUT_ITERATIONS,
     settings: {
       gravity: 1,
       scalingRatio: 10,
       slowDown: 5,
       adjustSizes: true,
       barnesHutOptimize: layoutGraph.order > 200,
     },
   });
   layoutGraph.forEachNode((node, attrs) => {
     if (!g.hasNode(node)) return;
     g.setNodeAttribute(node, 'x', attrs.x as number);
     g.setNodeAttribute(node, 'y', attrs.y as number);
   });
   ```

   Helper (also removed):
   ```ts
   function buildFetchedLayoutGraph(g: Graph): Graph {
     const out = new Graph({ type: 'directed', multi: false });
     g.forEachNode((node, attrs) => {
       const raw = attrs.raw as GraphNode | undefined;
       if (!raw || raw.stub) return;
       out.addNode(node, { x: attrs.x as number, y: attrs.y as number, size: attrs.size as number });
     });
     g.forEachEdge((edge, _attrs, src, tgt) => {
       if (!out.hasNode(src) || !out.hasNode(tgt)) return;
       out.addEdgeWithKey(edge, src, tgt);
     });
     return out;
   }
   ```

   Note: `countFetchedNodes` (also removed) is still needed for the
   `MAX_AUTO_LAYOUT_NODES` guard when FA2 is a selectable mode.

10. Maybe add `graphology-layout-noverlap` as an optional anti-collision
   pass exposed through the graph filter shelf (toggle: "Spread to
   prevent overlap").

   Context: tried adding it unconditionally as a post-pass after FA2 on
   2026-05-18 and it didn't visibly help — the residual clustering
   we're chasing isn't true geometric overlap, it's tight neighbourhood
   packing that noverlap leaves alone. The FA2 retune (linLogMode +
   outboundAttractionDistribution + lower gravity + higher
   scalingRatio) did the heavy lifting on that pass.

   Worth revisiting as a *user-controlled* filter, not an unconditional
   step. Use cases where it might earn its place:
     - very dense seed clusters where FA2 still produces overlap at
       readable zoom levels
     - exports / screenshots where overlap-free layout matters more
       than fidelity to the force layout
     - small graphs (< 50 nodes) where the macro layout is fine and
       only local collisions hurt

   Implementation sketch: add `noverlapSpread` to `graphFiltersStore`,
   surface a toggle in the graph filter shelf, run
   `noverlap.assign(layoutGraph, …)` between FA2 and the
   position-copy-back in `GraphCanvas.svelte` when the toggle is on.
   Re-install the dep when picked up: `npm install
   graphology-layout-noverlap`.

11. Revisit the kill-switch gate on `POST /api/nodes/:id/open` when the
   change-browser feature ships.

   Today the route reads `kill_switch.engaged.is_set()` (cached FSM,
   ~5 s staleness window) and deliberately skips the inline
   `kill_switch.probe_now()` that `POST /api/tor/probe` provides. The
   rationale: Tor Browser is the only browser in the allowlist today,
   and it self-isolates — if our system Tor (or its bundled Tor) is
   unreachable, the browser fails to connect inside its own window
   without ever touching the clearnet. The 0–5 s cache window has no
   leak vector under that assumption.

   That assumption breaks the moment we accept Mullvad / Brave Tor
   Window / Firefox+SOCKS into the allowlist. Mullvad is the closest
   to self-isolating (still routes through Tor), but Brave Tor Window
   only applies inside an already-open Brave instance — invoking the
   bin from CLI lands in a normal window unless we pass `--tor`. And
   Firefox with a SOCKS profile depends entirely on the analyst's
   profile config — we cannot verify the proxy is set.

   When that feature lands, switch the route to:
     - `await request.app.state.kill_switch.probe_now()` before launch,
     - return 409 if the fresh probe still reports `engaged`,
     - accept the ~1–3 s click latency as the cost of correct privacy
       posture for non-Tor-Browser launches.

   Files: `backend/backend/routes/nodes.py` (the `open_node_in_browser`
   handler). Update the cached-only comment block when you swap it.
   Frontend should also surface the latency — a spinner on the menu
   item or a "Probing Tor…" toast — so the analyst knows why the click
   isn't instant.

12. Flag resolution states (`done` / `dismissed`) are in the enum, the DB
   `CHECK` constraint, and the active-flag audit queries — but **no UI
   surfaces them yet**. The graph right-click menu only does Flag (→
   `flagged`) / Remove Flag; the lifecycle moves to `investigating` /
   `done` / `dismissed` are not exposed anywhere.

   When the F6 right-panel flag section and the F7 Flags sub-tab land,
   wire in Resolve (→ `done`) and Dismiss (→ `dismissed`) actions, plus a
   status filter that can show resolved flags. The backend already
   supports the transition — `PATCH /api/flags/:id` with `{status}` — and
   `flags.id` is available in those surfaces (unlike the graph payload).
   See the F4b flag-model note in the archived historical build plan and
   `backend/backend/db/flags.py` (`VALID_STATUSES`).
