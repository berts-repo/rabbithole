# Checklist Fix Plan

Fixes and decisions arising from the tester checklist walk-through.
Items are added one at a time as we discuss them. Scope is not limited
to any single feature slice — anything surfaced by testing lands here
until resolved.

Status legend (applied per-section in the header): `[landed]` shipped ·
`[deferred]` agreed not-next · `[blocked]` cannot proceed until a
dependency lands · `[open]` still being investigated · `[pending]`
spec'd but implementation not started.

Section numbers are stable — archived docs, including the historical build plan
and `docs/work/archive/2026-05-20-f4a/checklist.md`, reference them by number,
so do not renumber.

## Index

| § | Title | Status |
|---|-------|--------|
| 1 | Toolbar status dot — add crawl-active state | landed |
| 2 | Re-focus on a different node while in ego-focus | landed |
| 3 | Remove the `F` keyboard shortcut for ego-focus | landed |
| 4 | Stub rendering | deferred |
| 5 | `analysis_excluded` ⊘ overlay | blocked (AI Analysis) |
| 6 | Kill switch as single source of truth | landed |
| 7 | Cross-window graph sync after crawl | open |

Spec carry-overs (changes that should propagate beyond this doc):

- §6 changed the kill-switch contract from a binary toggle to a
  three-state FSM. The new contract lives in
  `docs/specs/app-shell.md` (kill switch section) and
  `docs/specs/explore-graph.md` (Resume control in graph
  toolbar). Treat those spec files as the canonical contract; this
  doc is the rationale archive.
- §1 introduced a `--warn` palette token for crawl-active UI.
  Re-use it for any other "background activity, not an error" state.

---

## 1. Toolbar status dot — add crawl-active state  *[landed — commit 79b0ec7]*

**Source:** `docs/work/archive/2026-05-20-f4a/checklist.md` line 21–22 (`[o]`)

**Current behaviour:** Dot pulses teal during `/api/graph` fetch, then
goes solid. Silent about background crawl activity.

**Target behaviour:** Three states, driven by fetch state AND crawl
status:

| State | Colour | Animation | Meaning |
|---|---|---|---|
| Idle | Green/teal | Solid | No fetch in flight, no crawl running |
| Fetching | Teal | Pulse | `/api/graph` request in flight |
| Crawl active | Yellow | Pulse | Crawl worker is running in the background |

**Precedence rule:** When both a fetch is in flight AND a crawl is
active, **yellow wins** — the crawl is the more meaningful signal to
surface.

**Open decision:** What does "crawl active" mean exactly?
- If the graph live-streams during the crawl (SSE / fast poll), yellow
  = "crawl running, results landing in real time."
- If the graph only refreshes after the crawl finishes, yellow =
  "you're looking at stale data; new results pending."

Either is fine — pick one and the colour stays meaningful. Recommend
deciding this when wiring the crawl-status subscription.

**Implementation sketch:**
- Subscribe the toolbar to the crawl-status source (existing endpoint
  or SSE channel — confirm which during implementation).
- Derive dot state from `{ fetching: bool, crawlActive: bool }` via a
  `$derived` rune.
- Add a `--warn: #e6c200` (or similar amber) custom property to the
  palette in the global stylesheet; reuse for other crawl-active UI.

**Acceptance:**
- Idle app shows solid green dot.
- Triggering a manual refresh pulses teal, then back to green.
- Starting a crawl flips the dot to pulsing yellow within ~1 s and
  keeps pulsing until the crawl ends AND the next graph refresh
  reflects the new data.

---

## 2. Re-focus on a different node while in ego-focus  *[landed — commit 7e0e3cb]*

**Source:** `docs/work/archive/2026-05-20-f4a/checklist.md` lines 72-73 (`[!]`)

**Current behaviour:** Once ego-focus is active on Node A, clicking
another visible node does not switch focus. The user is stuck on
Node A until they exit (Escape or ✕).

**Target behaviour:** **Left-click** another visible node while in
ego-focus → re-focuses to that node. Depth setting (1 / 2 / 3) is
preserved across the switch.

**Gesture rationale:** Left-click already enters ego-focus
(commit `7e0e3cb`). Keeping left-click as the re-focus gesture means
one consistent mental model: "left-click is always focus." Right-click
stays reserved for the context menu, which is about to grow in F4b
(Flag, Copy URL, Queue Crawl, Open in Tor Browser, etc.).

**Implementation sketch:**
- The graph's left-click handler currently no-ops (or just re-selects)
  when an ego-focus session is active. Change it to call the same
  enter-focus routine, passing the depth from the existing focus
  session rather than the default.
- Confirm the overlay (top-centre with domain + depth slider + ✕)
  updates to the new node's domain on switch.

**Acceptance:**
- Enter ego-focus on Node A at depth 2.
- Left-click a visible Node B → focus switches to Node B at depth 2;
  reachable set re-computes; overlay shows Node B's domain.
- Escape and ✕ still exit cleanly.

---

## 3. Remove the `F` keyboard shortcut for ego-focus  *[landed]*

**Source:** `docs/work/archive/2026-05-20-f4a/checklist.md` lines 74-75 (`[!]`)

**Decision:** Remove the `F` binding entirely. It duplicated a
single-click gesture, so it earned nothing. The key stays unbound for
now — do not pre-allocate it to Flag or anything else; decide later
if and when a real need appears.

**Scope of cleanup:**
- Remove the `F` keydown handler / binding wherever it lives in the
  graph component.
- Remove any helper function that exists only to serve that handler.
- Remove any tooltip or hint text that mentions pressing `F` to focus.
- Remove the checklist row on line 74-75 (or mark it as N/A) when
  this lands.
- Grep for `'f'` / `"F"` / `KeyF` in keyboard-handling code to make
  sure no orphaned references remain.

**Acceptance:**
- Pressing `F` with a node highlighted does nothing.
- No dead code or stale references to a focus-via-keyboard path.
- Left-click is the only entry point to ego-focus.

---

## 4. Stub rendering  *[addressed — halo layout, 2026-05-17]*

**Source:** `docs/work/archive/2026-05-20-f4a/checklist.md` lines 82-83 (`[?]`)

**Status:** Addressed by the **halo layout** change (2026-05-17, see
`/home/guy/.claude/plans/yes-make-a-plan-tidy-engelbart.md`). Stubs no
longer go through ForceAtlas2; each stub renders as a small dot (size
2.5) placed in a Vogel sunflower halo around its parent fetched node.
Two side effects:

1. **Toggle is instant.** The previous synchronous FA2 on the full
   stub-heavy graph (38k+ nodes on real crawls) used to freeze the
   browser for minutes and persist the setting, soft-bricking the app.
   Halo placement is O(stubs) with no force calculations.
2. **Halo density doubles as a centrality glance.** A fetched node
   with a dense fan around it is visually a *link directory* / hub
   without needing PageRank turned on. Isolated stubs (no parent in
   view) stick out as worth-a-look.

**Original discussion (kept for context, partly superseded):**
- Option **A** (fade stub nodes and edges to recede visually) was the
  agreed cheap win. The size-2.5 halo dot achieves the same recession
  without needing alpha.
- Collapse-to-parent agreed in principle. The halo IS the visual
  collapse — the parent is the orbit centre, the dots are the
  affordance. A future explicit "collapse to badge" overlay (number on
  the parent, no individual dots) is still on the table for hubs with
  thousands of stubs, but the halo handles the common case.
- Stubs stay in the backend / data model regardless — crawl
  candidates, link topology, Hidden / Domains bottom sub-tabs all
  depend on that. Unchanged.

**Still open (don't file as bugs):**
- Dashed-stroke / hollow stub render — no longer load-bearing, the
  size + position already encode "this is a stub". Revisit only if
  colour-blind / contrast feedback comes in.
- Numeric badge on parents (e.g. "+200" for hubs with huge halos) —
  cleaner than 200 individual dots once a node tops some threshold.
  Not needed yet.

---

## 5. `analysis_excluded` ⊘ overlay  *[blocked — depends on AI Analysis feature]*

**Source:** `docs/work/archive/2026-05-20-f4a/checklist.md` lines 84-85 (`[?]`)

**Status:** Blocked. Cannot test until the AI Analysis feature exists
to set the `analysis_excluded` flag on nodes. Not a bug, not deferred
by choice — just unreachable from here.

**Actions:**
1. Add to AI Analysis acceptance criteria: "verify ⊘ overlay renders
   on nodes where `analysis_excluded` is true."
2. Confirm the node-rendering code already has the branch
   `if analysis_excluded → draw ⊘`. If yes, leave it in place. If no,
   add it now so the AI Analysis ship-day check is purely visual.
3. Mark checklist line 84-85 as **blocked** (not failed) so it does
   not read as an open bug.

**Acceptance (whenever AI Analysis lands):** Setting
`analysis_excluded = true` on a node causes a ⊘ overlay to draw over
it in the graph. Clearing the flag removes the overlay.

---

## 6. Kill switch as single source of truth  *[landed — commit 79b0ec7]*

**Source:** `docs/work/archive/2026-05-20-f4a/checklist.md` lines 94-97 (`[o]` + `[!]`)

**Why this matters:** This is a dark-web investigation tool. If Tor
drops, the user **must** know immediately, the crawl **must** stop,
and clearing the alert **must not** silently resume traffic. Silently
continuing — or briefly drifting between "OK" UI and a dead crawler
— is a real safety and operational issue. The kill switch is a
safety device, not a pause button.

The three checklist items in this region (pill lag, missing alert,
auto-resume) all share one root cause: status, alerting, and the
crawl/poll lifecycle are currently three loosely-coupled concerns
that have to agree by coordination. The fix is architectural —
make the **kill switch the single source of truth** and have
everything else read from it.

### Architecture

```
                   ┌──────────────────┐
   Tor monitor  →  │                  │  → Status pill
   User toggle  →  │  Kill switch FSM │  → Alert modal (reason-aware)
   Future checks→  │  (single state)  │  → Crawl worker (on/off)
                   │                  │  → Poll timer (on/off)
                   └──────────────────┘
                            │
                            ↓
                       SSE channel
                            │
                            ↓
                   All open windows
```

**State machine — three states:**

| State | Means | How you got here | What's running |
|---|---|---|---|
| **Armed** | Safety off, network activity allowed | Normal startup, or explicit re-arm by user | Whatever the user explicitly started (poll, crawl) |
| **Tripped** | Safety on, all network activity forbidden | Tor died, future safety checks, or user manually flipped it | Nothing — polling stopped, crawl stopped |
| **Cleared-idle** | Safety off again, but app sits waiting for user to start things | User cleared a Tripped state | Nothing — until user explicitly clicks Start |

The state carries a **`reason`** field on trip (`tor_lost`,
`manual`, etc.) so consumers can render appropriately.

**Transport:** Push state changes over **SSE**, not poll.
`CLAUDE.md` already calls SSE out for real-time updates. Kill-switch
state is the canonical SSE use case — rare event, must propagate
instantly to every open window. Cross-window sync is free.

**Interim if SSE isn't wired yet:** Drop the status-pill poll
interval to ~2 s as a stopgap. Cheap and ugly but unblocks testing
while SSE is built. Do not ship long-term.

### 6a. Status pill — view of the FSM

**Behaviour:** Pill colour is `$derived` from the current kill switch
state. No independent polling, no independent logic.

- **Armed** → green/solid (idle) or pulsing teal (fetch in flight) or
  pulsing yellow (crawl active) — see section 1.
- **Tripped** → red/solid.
- **Cleared-idle** → green/dim or grey — visibly different from full
  Armed-and-running so the user can tell the safety was just released
  but nothing is running yet.

**Acceptance:** Pill state flips within ~1 s (ideally < 100 ms) of
any FSM transition.

### 6b. Alert modal — reason-aware view of the FSM

**Behaviour:** Modal renders when FSM enters Tripped state; behaviour
depends on `reason`:

| `reason` | UI |
|---|---|
| `tor_lost` (and future auto-trips) | **Big centered modal**, red border, dimmed background, blocks attention but not the underlying app. User surprised — must be alerted. |
| `manual` | **No modal** (optional small toast). User just flipped it themselves; a giant modal would insult their intelligence. |

**Modal shape (for auto-trips):**
- Centered overlay, dimmed background.
- Red border (`#ff4444`-ish), `--bg`-tinted body, light text — reuse
  the dark-terminal palette.
- Always dismissable. User may want to keep reading existing data.
- Buttons: **Acknowledge** (just close) and **Retry connection**
  (ping Tor; if up, transition FSM to Cleared-idle — do **not**
  auto-resume crawl/poll; see 6c).
- Fires on every transition into Tripped with an auto-reason. No
  per-session suppression — every drop is a real event.

**Suggested copy (tor_lost):**
> **Tor connection lost**
> The crawl has been halted. No new requests will go out until Tor is
> reachable again and you re-arm.
> [Acknowledge] [Retry connection]

### 6c. Cleared kill switch must NOT auto-resume

**Source:** `docs/work/archive/2026-05-20-f4a/checklist.md` lines 96-97 (`[!]`)

**Current (wrong) behaviour:** Clearing the kill switch resumes
polling and crawl automatically. The original checklist row was
written against this, which is itself wrong.

**Correct behaviour:** Clearing transitions FSM from
Tripped → **Cleared-idle**, not back to Armed-and-running. The user
must explicitly start polling and/or the crawl again from the
relevant control. Two extra clicks for "I paused on purpose" — the
right protective default for a safety device.

This applies equally to manual trips and auto-trips. A kill switch
is never a pause button. If the user wants pause semantics, we can
build a separate pause feature later — but it should not share a
button with the safety.

**Update needed:** `docs/work/archive/2026-05-20-f4a/checklist.md` line 96-97 should be rewritten to
reflect the new spec ("clearing the kill switch returns the app to
an idle state; polling does NOT resume until the user explicitly
starts it").

### Why this architecture is better than three separate fixes

- **One source of truth.** "Is the app armed?" has exactly one
  answer at any time, lives in one place. All UI reads from it.
- **No drift.** Pill lag (the bug in 9a) is impossible because pill
  and crawler and banner all read from the same FSM event, not from
  separate polls.
- **Cheap to extend.** Future failure modes (bridge auth fail,
  circuit timeout, expired tokens) become new `reason` values, not
  new banner/pill/coordination code.
- **Free cross-window sync.** Every open window listens to the same
  SSE channel; they all transition together.

### Acceptance (whole section)

- Killing Tor flips pill, shows modal, halts crawl, halts poll —
  all within ~1 s, all driven by one SSE event.
- Multiple open windows all transition together.
- Manually flipping the kill switch halts the same things but does
  NOT show the modal.
- Clearing a Tripped kill switch (manual or auto) leaves the app
  visibly Cleared-idle. Polling does not resume. Crawl does not
  resume. User must explicitly start each.
- Tor coming back while still Tripped does not auto-clear the kill
  switch — user explicitly clears.

---

## 7. Cross-window graph sync after crawl  *[open]*

**Source:** `docs/work/archive/2026-05-20-f4a/checklist.md` cross-window sync row.

**Reported behaviour:** Open the app in two tabs/windows. Start a
crawl in Window A. Switch to Window B. Window B's graph does not
pick up the new nodes on the next 15 s `/api/graph` tick.

**Expected behaviour (per `CLAUDE.md` and `explore-graph.md`):**
Graph data is poll-based (15 s). Two windows share the same backend
SQLite DB. Window B should see the new nodes on its next tick with a
brief Sigma re-mount blink.

**Why this is unrelated to §6:** The kill-switch FSM landed in commit
`79b0ec7` uses SSE for kill-switch state only. Graph data is still
polled. So this bug is not "missing SSE wiring." Most likely causes,
to investigate in order:

1. **Tab visibility throttling.** Browsers throttle `setInterval` /
   `setTimeout` in backgrounded tabs (down to once a minute in
   Chromium). Confirm by leaving Window B focused for 30 s after the
   crawl — if it updates with focus but not without, this is it.
   Fix: use `visibilitychange` to force a refetch on re-focus, or
   switch the poller to an SSE-driven invalidation push.
2. **Poller paused by a stale kill-switch state.** If Window B
   received a `kill_switch.engaged` event at any point and never saw
   the matching `clear`, its poller is paused.
3. **`/api/graph` response is cached.** If the backend or a layer
   above is returning a 304/cached body, Window B sees no diff.
   Check response headers in DevTools.

Note: commit `d511b78` already added a "refresh graph on tab/window
return so ego-focus repaints" path. That fix is about ego-focus
repaint, not the cross-window poll-tick refresh. They are adjacent
but separate; (1) above is the most likely root cause.

**Acceptance:** With two windows open and a crawl running in Window
A, Window B's graph reflects the new nodes within at most one
15 s tick of receiving focus (today's contract) or within ~1 s of
the backend committing them (if we ever push graph deltas over SSE).
