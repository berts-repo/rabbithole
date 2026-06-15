# F4a tester checklist — Graph canvas

Walk through this end-to-end after a fresh pull. Each box should pass before
F4b starts. Notes about *expected* gaps (placeholder right panel, stub
rendering) are called out inline so they're not mistaken for bugs.

Prerequisites: a project with at least a handful of crawled nodes. If you
don't have one yet, run a short crawl from the **Crawl** sub-tab first.

## Boot

- [x] `make dev-backend` — backend listens on `:7654`, no errors in log
- [x] `make dev-frontend` — Vite running on `:5173`, opens cleanly
- [X] Open `http://127.0.0.1:5173` — app shell renders, header stats bar shows non-zero page count
- [x] Project picker shows the project you want to test against (or pick one)

## First render

- [x] Switch to **Explore** (centre tab). Graph appears within ~1 s on a GPU-backed browser. Software WebGL (SwiftShader) adds a one-off shader-compile penalty on first mount, but it should still be sub-second — anything in the 10+ s range is a regression, not expected behaviour.
- [x] Toolbar status line reads `updated HH:MM:SS · N nodes · M edges`
- [x] Teal dot pulses during the first fetch, then steadies
    + Fixed: dot now has three states — solid teal idle, pulsing teal during `/api/graph` fetch, pulsing yellow while a crawl is active. Crawl-active takes precedence over fetch. See `docs/work/archive/2026-05-20-fixes/checklist.md` §1.
- [x] Layout is computed synchronously to convergence — nodes appear already settled, no drift animation
- [x] On the next 15 s poll the layout does **not** re-jiggle and the camera does **not** zoom — existing node positions are preserved

## Stubs toggle

- [x] Toolbar shows an eye-shape button between **Show/Hide stubs** and **Fit**
- [x] Default is *stubs hidden* (closed-eye icon); only fetched pages render
- [x] Click the toggle → stubs and their connecting edges appear; toolbar counts jump up; icon flips to open-eye
- [x] Click again → stubs disappear; counts drop back

## Camera

- [x] Plain drag on empty canvas pans the camera
- [x] Mouse wheel zooms in/out
- [x] **Fit** button (Maximize2 icon) re-centres the graph (animated, ~300 ms)
- [x] **Reset** button (RotateCcw icon) re-randomises positions, re-runs the layout synchronously, and refetches `/api/graph`

## Hover

- [x] Hover a node → tooltip with the page title appears above it
- [x] Non-adjacent nodes dim to a near-bg colour
- [x] Non-adjacent edges dim; adjacent edges turn accent-teal
- [x] Moving the cursor off the node clears the dim immediately

## Single-select

- [x] Click a node → it gains a teal ring
- [x] Right panel auto-expands (unless you previously collapsed it manually)
- [x] Right-panel **Page** tab is the active tab
- [x] Right-panel body shows the F6 placeholder text — **expected**, real content lands in F6
- [x] Click empty canvas (no drag) → selection clears; right panel stays open

## Multi-select

- [x] Ctrl+click a second node (`Cmd+click` on macOS; `Shift+click` also works) → both nodes ringed; toolbar status flips to `2 nodes selected` (orange dot)
- [x] Ctrl+click the same node again (`Cmd+click` on macOS; `Shift+click` also works) → it's removed; toolbar count goes back to 1

## Ctrl/Cmd+A

- [x] On a graph with ≤ 50 visible nodes, Ctrl+A (Cmd+A on macOS) selects everything immediately
- [x] On a graph with > 50 visible nodes, Ctrl+A pops a confirmation modal "Select all N nodes?"
- [x] **Cancel** closes the modal, selection unchanged
- [x] **Select all** selects everything; toolbar status shows the full count

## Ego-focus

- [x] Right-click a node → top-centre overlay appears with that node's domain, a Depth slider, and an ✕ button
- [x] Nodes outside the depth horizon are hidden
- [x] Move the slider to 1 / 2 / 3 → reachable set re-computes; visibility updates immediately
- [x] Left-click a different (visible) node while focused → re-focus to that node; depth setting preserved
- [x] Press `Escape` → exits ego-focus
- [x] Press `Escape` again → clears any remaining selection
- [x] Click the ✕ on the overlay → exits ego-focus

## Stubs and analysis_excluded

- [N/A — deferred] Stub nodes render with a near-bg fill + accent ring — F4a hint only. Real dashed-outline custom Sigma program is **deferred**, not next. Stubs stay hidden by default; revisit rendering (fade + collapse-to-parent with affordance) when stub handling becomes a real friction point in an investigation. See `docs/work/archive/2026-05-20-fixes/checklist.md` §4.
- [N/A — blocked] Nodes with `analysis_excluded` currently don't show the `⊘` overlay — **blocked on AI Analysis feature**. Cannot be tested until something sets the flag. Verification rolls into the AI Analysis acceptance criteria. See `docs/work/archive/2026-05-20-fixes/checklist.md` §5.
## Polling and kill switch

- [x] Toolbar timestamp updates every 15 s without interaction
- [x] Confirm `/api/graph` is hit on each 15 s tick. Steps:
    1. Open the app in Chromium/Firefox at `http://127.0.0.1:5173`.
    2. Open DevTools (F12 or Ctrl+Shift+I) and click the **Network** tab.
    3. In the Network filter row, type `graph` to narrow to graph requests.
    4. Make sure the **Preserve log** checkbox is on (otherwise the list clears on navigation).
    5. Wait ~30 s on the Explore tab. You should see **two** `GET /api/graph` rows ~15 s apart, each returning `200`.
    6. Click one row → **Response** sub-tab → confirm it carries a `nodes` and `edges` array.
    + If only the first request appears: the poller has stopped (kill switch tripped, tab not focused, or a JS error). Open the **Console** tab and look for red entries.
- [!] Open the same app in a second browser tab or window, start a crawl there, then return to the first app view → new nodes appear in the first view on the next `/api/graph` poll tick (a momentary blink while Sigma re-mounts is expected). **Reported broken — open bug, see `docs/work/archive/2026-05-20-fixes/checklist.md` §7.**
    + Clarification: this tests cross-window sync between two open instances of the app. It does **not** mean a new in-app workspace tab, graph tab, or Firefox/Tor Browser tab should be created by the crawl.
    + Note: the kill-switch FSM landed in commit `79b0ec7` uses SSE for kill-switch state only. Graph data still polls every 15 s per `CLAUDE.md` / `docs/specs/explore-graph.md`. So a backgrounded tab returning to focus should pick up new nodes on the next tick. If it doesn't, the issue is in the poller's lifecycle (visibility change, tab-not-focused throttling) — not the SSE wiring.
- [x] Toggle the kill switch in the header so it fires (Tor down or manual) → polling stops
    + Fixed: kill switch is now a three-state FSM (`armed` / `tripped` / `cleared_idle`) driven by SSE (`kill_switch.engaged|banner|clear`). Pill flips colour on the same event the crawler stops on — no pill lag. A big centred red modal (`KillSwitchAlert.svelte`) opens on auto-trip with Acknowledge / Retry connection. See `docs/work/archive/2026-05-20-fixes/checklist.md` §6.
- [x] Clear the kill switch → polling resumes; the next tick fetches fresh data
    + Spec changed (per `docs/work/archive/2026-05-20-fixes/checklist.md` §6c): clearing a tripped kill switch now moves the FSM to `cleared_idle`, **not** back to running. SSE streams stay paused and `/api/graph` polling skips until the analyst clicks **Resume** in the graph toolbar (or re-arms from the pill). A kill switch is a safety device, not a pause button.

## Build sanity

- [x] `cd frontend && npm run check` — 0 errors, 0 warnings
- [x] `cd frontend && npm run build` completes; `backend/public/` contains exactly `bundle.js`, `bundle.css`, `index.html`
- [x] No additional `.js` or `.css` chunks under `backend/public/`

## Known gaps (do NOT file as bugs — these are F4b)

- Right panel body — placeholder until F6
- Stub dashed outline — currently rendered as filled-bg-with-ring
- `analysis_excluded` ⊘ overlay — not yet drawn
- Workspace tab bar (Global + collections + ✕) — not in F4a
- Right-click context menu items beyond Focus (Flag, Copy URL, Queue Crawl, etc.) — F4b
- Layout tabs (Hierarchical / Timeline / Concentric) — F4b
- Client-side filters (max hops, show stubs, edge mode, colour modes, overlays) — F4b
- Draw analyst edge / Expand to collection / Export dropdown — F4b
- Shared modals (Add Monitor, Queue Analysis, Collection picker, Draw Edge) — F4b
