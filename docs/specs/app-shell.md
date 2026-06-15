# App Shell

The shell is the persistent frame that wraps every tab. It has two parts: the app header
(tab row + status pills) and full-screen overlays (project picker, toast).

---

## App Header

One row of content, always visible, at the very top of the viewport.

### Row 1 — Tab row

Left side: two tab buttons: **Search** and **Explore**. Crawl is a left sidebar sub-tab.
Nodes tab has been removed — domain browsing lives in the bottom pane Domains sub-tab and
the right panel Domain tab. Clicking a tab switches the main view. The active tab has a
highlighted background and teal text.

The header carries no count cells. Counts live next to the data they describe:
**domains / pages** join nodes / edges on the Explore graph toolbar's status
line, scoped to the active workspace (derived from the graph payload — see
`graphCounts.deriveScopeCounts`); **flags / monitors** are project-wide count
badges on their bottom-pane tabs, sourced from `/api/stats`.

Right side: gear icon + two status pills:

**⚙ Settings icon** — opens the Settings modal (see settings modal doc). Shows a dot
badge when any non-default graph setting is active.



**LLM pill** — clickable button that starts or stops the AI worker. Shares state with the
LLM Service section in the Intel sub-tab — both always reflect the same worker status.
- Dot: teal = running, grey = stopped.
- Label: `LLM` when idle; `LLM (N)` when there are jobs in the queue (amber digit badge).
- Disabled (pointer-events off) while the toggle request is in flight.
- Status refreshes every **15 seconds**.
- Clicking Start from the pill uses the same startup sequence as the Intel section (crash
  recovery + legacy bridge). Clicking Stop is ignored if the worker is crawl-owned — a
  toast explains: "Worker is running a crawl — stop the crawl first."

**Tor pill** — non-clickable span.
- Dot: teal = connected, red = unreachable.
- Checked every **30 seconds**.
- When disconnected, a full-width amber banner appears below the header (see below).

**Kill switch** — a single source of truth for whether the app is allowed to make outbound network requests. Implemented as a three-state finite state machine driven by SSE so every open window stays in agreement. Shown immediately to the right of the Tor pill as a pill-style indicator. Rationale and architectural detail live in `docs/work/archive/2026-05-20-fixes/checklist.md` §6; the contract below is canonical for implementation.

**States:**

| State | Meaning | What is running | How you got here |
|-------|---------|-----------------|-------------------|
| `armed` | Safety off, network activity allowed | Whatever the user explicitly started (poll, crawl, LLM, embed) | Normal startup, or explicit re-arm |
| `tripped` | Safety on, all network activity forbidden | Nothing — polling stopped, crawl stopped, LLM paused between jobs (does not kill the running job), embed paused | Tor lost (auto), other future safety checks, or user manually flipped it |
| `cleared_idle` | Safety off again, but app sits waiting | Nothing — until the user explicitly resumes | User cleared a `tripped` state |

A `reason` field rides on the `tripped` transition: `tor_lost`, `manual`, or future values (`bridge_auth_fail`, `circuit_timeout`, etc.).

**Pill rendering** — colour is `$derived` from the FSM. No independent polling, no independent logic.
- `armed` → green/solid (idle), pulsing teal (fetch in flight), or pulsing yellow (crawl active) — see status dot rules in `docs/work/archive/2026-05-20-fixes/checklist.md` §1.
- `tripped` → red/solid.
- `cleared_idle` → green/dim or grey — visibly distinct from full `armed`-and-running so the user can tell the safety was just released but nothing is running yet.

**Pill state must flip within ~1 s (target < 100 ms) of any FSM transition.** Cross-window sync is free via SSE.

**Auto-trip modal** — when the FSM enters `tripped` with an auto-`reason` (any value other than `manual`), a centered alert modal renders (`KillSwitchAlert.svelte`):
- Red border (`#ff4444`-ish), `--bg`-tinted body, light text. Dimmed page behind. Always dismissable (analyst may want to keep reading existing data).
- Buttons: **Acknowledge** (close) and **Retry connection** (ping Tor; if up, transition FSM to `cleared_idle` — does **not** auto-resume crawl/poll).
- Fires on every auto-trip. No per-session suppression — every safety event is a real event.
- Suggested copy for `reason=tor_lost`:
  > **Tor connection lost**
  > The crawl has been halted. No new requests will go out until Tor is reachable again and you re-arm.
  > [Acknowledge] [Retry connection]

**Manual trip** — no modal. Optional small toast. User just flipped it themselves; a giant modal would insult their intelligence.

**Clearing a tripped switch does NOT auto-resume.** Clearing (manual or via Retry connection) moves the FSM `tripped → cleared_idle`. Polling stays paused. Crawl stays paused. The user must explicitly resume each from its own control (the Resume button in the graph toolbar — see `docs/specs/explore-graph.md`). A kill switch is a safety device, not a pause button. If pause semantics are needed later, build a separate pause feature; do not share a button with the safety.

**Tor coming back while still `tripped`** does not auto-clear. Analyst explicitly clears.

**Transport** — FSM transitions are pushed over SSE (channel events: `kill_switch.engaged`, `kill_switch.banner`, `kill_switch.clear`). Polling-based status checks are not the source of truth; they may be used only as a backup heartbeat. `CLAUDE.md` already calls SSE out for real-time updates and this is the canonical SSE use case.

**Persistence** — current FSM state (and last `reason`) is held in memory by the backend service and broadcast to clients on connect. The user-set default for kill-switch enforcement is persisted in the `settings` table (`tor.kill_switch`, default `true`); this controls whether Tor-down auto-trips at all, not whether the FSM exists.

### Tor warning banner

Appears below the header when Tor is unavailable. Shows:
- Warning text + `sudo systemctl start tor` in monospace.
- Kill switch status reflects the FSM: "Kill switch tripped — crawl and services halted (Tor lost)", "Kill switch cleared — click Resume to restart", or "Kill switch disabled — activity continuing (will fail)".
- A ✕ dismiss button that hides the banner for the session.

---

## Toast

A fixed bottom-center notification banner. Appears when there is a message to show and
disappears automatically after a short delay. Not
interactive — `pointer-events: none`. Fades in from below on appearance.

---

## Project Picker

A full-viewport modal overlay shown on initial load if no project is active, or after a
project fails to load.

Project list is fetched from `GET /api/projects` on modal open. Project state is owned
by the backend (`projects.json`) — no localStorage involved.

**Existing projects list** — each row shows the project name and file path. Clicking a row
calls `POST /api/project/switch` and reloads the page on success. Each row also has a
✕ delete button — calls `DELETE /api/projects/:id` (removes from registry, does not delete
the DB file). Confirm before deleting.

**Empty state** — if no projects exist yet, shows: "No projects yet. Create one below to get started."

**Create new project form** — always visible below the list:
- Name input (free text)
- Path input (e.g. `scans/case.db`)
- Create button — calls `POST /api/projects`, then switches to the new project and reloads.

Both name and path are required. Toast shown on validation failure or API error.

---

## Pane Layout & Resizing

The Graph tab layout is a three-region split: left sidebar · graph canvas · right panel, with the bottom pane spanning the full width below.

All four boundaries are user-adjustable via drag handles:

| Handle | Between | Axis |
|--------|---------|------|
| Left handle | Left sidebar ↔ Graph canvas | Horizontal |
| Right handle | Graph canvas ↔ Right panel | Horizontal |
| Bottom handle | Graph canvas + panes ↔ Bottom pane | Vertical |

**Drag handles** — a 4 px bar rendered at each boundary. On hover it widens to 8 px and changes colour to `--accent`. Cursor changes to `col-resize` or `row-resize`. Dragging moves the boundary in real time.

**Constraints:**
- Left sidebar: min 180 px, max 420 px. Default 260 px.
- Right panel: min 220 px, max 520 px. Default 320 px.
- Bottom pane: min 120 px, max 60% of viewport height. Default 220 px.

**Persistence** — pane sizes are saved to `localStorage` under `onionhole.pane.*` keys (not the project DB — they are per-browser preferences, not per-project). Restored on next load. If a saved size violates the current viewport, it is clamped to the constraint.

The right panel still has its own ◀/▶ collapse toggle independent of resizing. Collapsing snaps it to 24 px; re-expanding restores the last dragged width.

---
