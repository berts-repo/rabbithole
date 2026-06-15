# Security Decisions Log

> Archive of the topic-by-topic security review that produced the rules in `stack.md` (§ Security). This file is the rationale; `stack.md` is the canonical contract. If they ever disagree, `stack.md` wins and this file is amended to match.
>
> Renamed from `plan.md` to remove the case-only collision with the historical
> build plan. That plan now lives at
> `../work/archive/2026-05-21-build-plan-history/plan.md`.

## Security decision track

Goal: replace the rough security notes in `stack.md` with approved implementation rules after review, not before.

Process for this review:

1. Discuss one security topic at a time.
2. For each topic, capture:
   - risk being addressed
   - recommended default
   - notable alternative(s)
   - tradeoff summary
   - final decision
3. Update `stack.md` only after the decision is made.

Decisions recorded so far:

- [x] Tor egress model: mixed
  - Rule: non-local outbound traffic must use Tor and fail closed if Tor is unavailable.
  - Direct access is allowed only for local integrations.
- [x] Base allowlist boundary
  - Default direct-connect allowlist is limited to literal loopback addresses (`127.0.0.1/8`, `::1`) and optional Unix domain sockets.
  - Private LAN ranges and hostname-based exceptions are not allowed by default.
- [x] Remote target scope
  - Remote network access is limited to `.onion` targets only.
  - Direct non-Tor access is limited to local loopback services only.
- [x] Optional operator-managed exception list
  - Rejected for now.
  - Non-loopback helper integrations are out of scope unless revisited later as an explicit security exception.
- [x] Redirect policy and crawl-boundary enforcement
  - Seeds, discovered links, and redirect destinations must all resolve to valid `.onion` URLs over `http` or `https`.
  - Redirects are allowed only when the destination is another valid `.onion` URL over `http` or `https`.
  - Enforce a small redirect cap.
  - Log every blocked redirect.
- [x] Response limits, decompression, and parser safety
  - Enforce strict connect, read, and total request timeouts.
  - Enforce a maximum decompressed response size of `10 MB`, checked while streaming rather than after full buffering.
  - Keep a small redirect cap.
  - Parse only explicitly supported content types.
  - Never execute page JavaScript or other active content.
- [x] Storage model for hostile content (`store raw` vs `sanitize before persist`)
  - Preserve raw fetched body text as evidence.
  - Sanitize or escape at render time, not at storage time.
  - Store any cleaned or normalized text as a separate derived form for search, snippets, and LLM processing.
  - Never treat stored HTML as trusted HTML.
- [x] API auth model: cookie shape, session lifetime, and CSRF/origin checks
  - Use a random in-memory session cookie for the local UI.
  - Set `HttpOnly`.
  - Set `SameSite=Strict`.
  - Rotate the session on server restart.
  - Require strict `Origin` validation on all state-changing requests.
  - Reject cross-origin requests by default.
  - Do not add a separate CSRF token for now.
- [x] Local binding, CORS, and localhost/DNS-rebinding hardening
  - Bind the backend to `127.0.0.1` only.
  - Do not bind to `0.0.0.0`.
  - Do not enable permissive CORS.
  - Reject unexpected `Host` headers.
  - Browser access is limited to the expected local origin.
- [x] Project path handling, browser launch safety, and shell injection risk
  - Each project is a user-selected directory root.
  - The project database lives at a fixed path under that project root.
  - Arbitrary external DB paths are not supported.
  - Project paths and browser paths are treated as data and canonicalized.
  - External programs are launched only via direct exec with explicit argument lists.
  - No shell interpolation is used for URLs, paths, or browser launch commands.
- [x] File permissions for DB, registry, exports, and temp files
  - Create project root directories with restrictive permissions such as `0700`.
  - Create the DB and other sensitive project files with owner-only permissions such as `0600`.
  - Treat exports as sensitive by default and save them with owner-only permissions.
  - Default export location is under the project root.
  - If the user exports outside the project root, warn that destination permissions may expose the data.
  - Temp files should be owner-only and deleted promptly when no longer needed.
  - Logs containing sensitive data should be avoided or treated as sensitive files.
- [x] LLM prompt-injection containment and data minimization
  - Treat crawled page content as untrusted data, never as instructions.
  - Send the model only the minimum bounded derived text needed for the task.
  - Keep system/task instructions separate from page content.
  - Model outputs are advisory only.
  - Model outputs may suggest seeds, tags, flags, or follow-up actions, but cannot directly trigger tools, network requests, or persistent state changes.
  - Any state change requires explicit application logic or user approval.
- [x] `.onion` HTTPS / certificate-verification policy
  - Valid `.onion` targets may use `http` or `https`.
  - HTTPS certificate verification remains enabled.
  - Verification failures are logged and treated as fetch failures.
  - The crawler does not silently bypass or downgrade broken HTTPS.
- [x] Frontend rendering policy, CSP, and external-resource restrictions
  - The SPA never treats crawled content as trusted HTML.
  - Hostile content is rendered as escaped text or from a separately sanitized derived form.
  - The SPA does not load external scripts, styles, fonts, images, or frames from crawled pages.
  - The app serves with a restrictive self-only CSP.
  - Full-page viewing belongs in Tor Browser, not the SPA.

Decision queue, in order:

- [x] Tor egress and DNS leak prevention
- [x] Direct-connect exception setting for non-loopback destinations
- [x] Redirect policy and crawl-boundary enforcement
- [x] Response limits, decompression, and parser safety
- [x] Storage model for hostile content (`store raw` vs `sanitize before persist`)
- [x] API auth model: cookie shape, session lifetime, and CSRF/origin checks
- [x] Local binding, CORS, and localhost/DNS-rebinding hardening
- [x] Project path handling, browser launch safety, and shell injection risk
- [x] File permissions for DB, registry, exports, and temp files
- [x] LLM prompt-injection containment and data minimization
- [x] `.onion` HTTPS / certificate-verification policy
- [x] Frontend rendering policy, CSP, and external-resource restrictions

Status note:

- `stack.md` currently contains draft security guidance that still needs review and cleanup.
- Do not treat that section as final until the decisions above are resolved.

---

## Architecture decisions (locked in)

| Concern | Decision |
|---------|----------|
| State management | Module-level `$state` rune stores in `src/lib/stores/*.svelte.ts` — one focused store per domain |
| SSE connections | Centralized manager in `src/lib/sse.svelte.ts` for data-plane streams — one connection per endpoint, ref-counted, pause/resume on kill-switch trip. Control-plane channels (e.g. `/api/kill_switch/events`) deliberately bypass the manager and own their own EventSource so the recovery signal survives a trip. |
| API layer | Typed client in `src/lib/api.ts` — one function per endpoint, all response shapes as TypeScript interfaces, single base path and error handling |

---

## Build phases

### Phase 1 — Foundation
_Invisible but everything depends on it._

- [ ] Vite + Svelte 5 + TypeScript scaffold (`npm create svelte`, strict TS config)
- [ ] Single-bundle build output: `bundle.js` + `bundle.css` in `public/` (no chunk splitting)
- [ ] CSS custom properties + global base styles (dark terminal aesthetic)
- [ ] `src/lib/api.ts` — full typed API client (all endpoints + response interfaces from spec)
- [ ] `src/lib/sse.svelte.ts` — centralized SSE manager with ref-counting and kill-switch hook
- [ ] `src/lib/stores/selection.svelte.ts` — selected node URL, highlight-only vs full-select
- [ ] `src/lib/stores/services.svelte.ts` — LLM worker status, Tor status, kill switch state, embed service
- [ ] `src/lib/stores/workspace.svelte.ts` — active graph workspace tab, bottom pane active sub-tab
- [ ] `src/lib/stores/navigation.svelte.ts` — active left pane sub-tab, active right panel tab
- [ ] `src/lib/stores/crawl.svelte.ts` — active crawl status, SSE stream ref

### Phase 2 — App shell
_Visual frame. Connects to the backend. Nothing else can be tested without this._

- [ ] Pane layout: left sidebar / graph canvas / right panel / bottom pane, full viewport
- [ ] Drag handles (left, right, bottom) with min/max constraints and localStorage persistence
- [ ] Right panel collapse toggle (◀/▶), snaps to 24 px
- [ ] App header: Search + Explore tab buttons (counts moved out of the header — domains/pages on the graph toolbar status line, flags/monitors as bottom-pane tab badges)
- [ ] Settings gear icon with dot badge (non-default graph settings active)
- [ ] LLM pill (start/stop, queue count badge, 15 s poll, synced with Intel sub-tab)
- [ ] Tor pill (30 s poll, teal/red dot)
- [ ] Kill switch toggle (persisted in `settings` table, pauses crawl + services on Tor down)
- [ ] Tor warning banner (below header, dismiss button)
- [ ] Project picker modal (list, create, switch, delete)
- [ ] Toast system (fixed bottom-centre, auto-dismiss, pointer-events none)

### Phase 3 — Crawl sub-tab
_Populates the DB so every phase after has real data to work with._

- [ ] Left sidebar with three sub-tab buttons (Search · Intel · Crawl), Crawl active
- [ ] Seed URL input + Enter to submit + invalid URL toast
- [ ] Bookmarks dropdown (★ button) + save bookmark popover
- [ ] Mode select (Cross-site / BFS / DFS / Diverse / Focused) + Focused contextual note/warning
- [ ] Stay on domain checkbox (disabled + tooltip when Cross-site mode selected)
- [ ] Add results to collection dropdown (+ New collection… inline)
- [ ] Start / Stop buttons + live status row (seed, counts, elapsed time via SSE)
- [ ] Bulk Import section (paste area, parsed list with crawled/stub/unknown states, per-row actions)
- [ ] Scheduled Crawls section (add form, schedule list with pause/resume/remove)

### Phase 4 — Graph canvas
_Centerpiece. Unblocks testing of all remaining phases._

- [ ] Sigma.js + graphology integration, graph data fetch + 15 s refresh via SSE
- [ ] Workspace tab bar (Global tab always present, collection tabs, + button, ✕ close)
- [ ] Active workspace context propagation to bottom pane Collection + Domains sub-tabs
- [ ] Node rendering: color modes, stub nodes (hollow/dashed), `analysis_excluded` overlay (⊘)
- [ ] Hover-dim (adjacent nodes/edges stay full opacity)
- [ ] Single click → full selection, auto-expand right panel
- [ ] Multi-select: Ctrl+click (`Cmd+click` on macOS; `Shift+click` also works), box-drag, Ctrl+A (with confirmation >50 nodes), Escape to clear
- [ ] Right-click context menu — single node (all items per spec)
- [ ] Right-click context menu — multi-select (all items per spec)
- [ ] Right-click on analyst edge → Delete analyst edge
- [ ] Ego-focus mode (overlay, depth slider 1–3, click-to-refocus, Escape to exit)
- [ ] Domain cluster nodes (group by domain, double-click to expand)
- [ ] Graph toolbar: status line, Draw analyst edge (sequential + batch modes + modal), Expand to collection popover, Pause/Resume physics, Layout tabs (Force / Hierarchical / Timeline / Concentric), Fit, Reset layout, Export dropdown
- [ ] Timeline layout legend (date range, day count, undated count)
- [ ] Add Monitor modal (from right-click → Add Monitor…)
- [ ] Queue Analysis modal (from multi-select right-click)
- [ ] Collection picker modal

### Phase 5 — Left pane (Find + Intel + Settings)
_Depends on graph selection being wired up._

**Find sub-tab**
- [ ] Find input (300 ms debounce, 2-char minimum, ✕ clear)
- [ ] Keyword / Semantic mode toggle
- [ ] Keyword results (page / entity / note rows, highlight-only on click)
- [ ] Semantic results (similarity score rows)
- [ ] Right-click context menu on results
- [ ] Find state persists across sub-tab switches
- [ ] Receives domain from bottom pane "Send to Find"

**Intel sub-tab**
- [ ] Section 1 — LLM Service: status row, Start/Stop, queue list with reorder (↑/↓/move-to-top), ✕ and ⊘ per row, waiting jobs pinned at bottom
- [ ] Section 2 — Analyse: URL auto-fill, type select, question input (Q&A), model dropdown, Queue button
- [ ] Section 3 — Embedding Model: status row, progress line, Pause/Resume
- [ ] Section 4 — Collection Analysis: collection dropdown, type select (per-URL + collection-scoped), Queue/Analyse button, inline result for collection-scoped jobs
- [ ] Collapse state persisted per section
- [ ] LLM status synced with header pill (shared services store)

**Settings modal**
- [ ] Modal overlay (⚙ opens, ✕/Escape closes)
- [ ] Graph tab: View section (color, edges, group-by-domain), Filters section (max hops, show stubs, hide orphans, show all edges, mutual clusters), Overlays section (flagged nodes, isolate, highlight bridges with sub-controls)
- [ ] Engines tab: engine list (edit/delete inline), + Add engine
- [ ] Watchlist tab: term list (edit/delete), + Add term
- [ ] Browser tab: path input, Test button, launch mode select, info box
- [ ] Embedding tab: auto-start toggle, status, Start/Stop, model select (with re-index warning), progress

### Phase 6 — Right panel
_Depends on graph selection. Domain click (Domains sub-tab) opens Domain tab for first crawled page._

- [ ] Panel collapse/expand (◀/▶), auto-expand on node select unless user-collapsed
- [ ] No-selection placeholder state (no API calls)
- [ ] Stub node simplified state across all three tabs

**Page tab**
- [ ] Header block: URL, domain alias + rename popover, title, meta chips, Reviewed toggle, Exclude toggle, AI summary
- [ ] Collections section: pill badges with ✕, + Add picker (lazy-fetch, checkmark for existing)
- [ ] Flag section (shown only when flagged): status select, priority select, note textarea, Remove flag
- [ ] Details toggle + expanded block: content preview, entities (with context menu), response headers (`<details>`), version history (`<details>`), notes (list + add)

**Domain tab**
- [ ] Domain profile card: 4 stat chips, activity sparkline (SVG), entity type breakdown chips
- [ ] Pages list (cap 200, "view all" link to Domains sub-tab)
- [ ] Pages list right-click context menu
- [ ] Entities list + "View fingerprint clusters →" link
- [ ] Entities right-click context menu
- [ ] Uptime monitors list (⏸/▶, ✕) + Add monitor form (with collapsible alert settings)

**Analysis tab**
- [ ] Analyses list: type, status badge, model, Re-run button, ✕ button
- [ ] Result pane (below list, 50% height, scroll): meta line, question line (Q&A), result body, pending/running states
- [ ] Lightweight polling while selected node has pending/running jobs

**Cluster workspace (multi-select)**
- [ ] Nodes tab: selected URL list, ✕ per row, Add to collection, Save as new collection, Crawl selected (stubs only)
- [ ] Q&A tab: question textarea, Ask all button, inline results per node (5 s poll), stub notice
- [ ] Common tab: shared entities (≥2 nodes), grouped by type, refresh button, entity context menu

### Phase 7 — Bottom pane
_Depends on graph + right panel._

- [ ] Header row (always visible, ▽/△ toggle, 7 sub-tab buttons)
- [ ] Shared row pattern: visibility toggle (●/○) + content button
- [ ] Right-click context menu (all items per spec, Remove from collection only in Collection sub-tab)

- [ ] **Collection sub-tab**: collection name header (rename, export, delete), search input, item count, Crawl all uncrawled popover, URL rows with stub badge
- [ ] **Live Crawl sub-tab**: SSE log feed, domain filter, 200-line buffer, clickable URL rows, status colour coding
- [ ] **Analyses sub-tab**: status + type filters, count badge, rows with type/model/status, 5 s poll while active, click → right panel Analysis tab
- [ ] **Domains sub-tab**: filter input, count badge, rows with alias/hostname/page count/fail count, click → domain highlight (all domain nodes highlighted, rest dimmed, not a multi-select) + Domain tab for that domain
- [ ] **Flags sub-tab**: URL filter, status + priority dropdowns, count badge, rows with priority badge + status label
- [ ] **Fingerprints sub-tab**: Sites ≥ N control, refresh, CSV export, cluster list (header key/value/site count/IDF), expandable rows with member list
- [ ] **Hidden sub-tab**: filter term list (✕ per term), add-filter input (Enter or Add button)

### Phase 8 — Search tab
_Mostly standalone. Good to finish on._

- [ ] Search bar (input + Search/Stop button, disabled while searching)
- [ ] Source selector row (checkbox pills, per-source status badges)
- [ ] Results list: crawled rows (darker bg, crawled badge, detail row) + uncrawled rows (probing state)
- [ ] Action bars: crawled (→ Graph, + Collection, Queue Analysis) + uncrawled (Queue Crawl, + Collection, Flag)
- [ ] SSE stream event handling (result / probe / done / error / all_done)
- [ ] Empty states (no engines, before search, no results, all sources failed)

---

## Key constants (from spec)

| Constant | Value |
|----------|-------|
| Graph refresh interval | 15 s |
| LLM status poll (header pill) | 15 s |
| LLM status poll (Intel sub-tab) | 8 s |
| Embed status poll (Intel sub-tab) | 10 s |
| Tor status poll | 30 s |
| Analyses sub-tab poll | 5 s |
| Right panel Analysis tab poll | 5 s (only while pending/running jobs exist) |
| Collection synthesis poll | 4 s |
| Search debounce | 300 ms |
| Search min query length | 2 chars |
| Live crawl log buffer | 200 lines |
| Left sidebar min/default/max | 180 / 260 / 420 px |
| Right panel min/default/max | 220 / 320 / 520 px |
| Bottom pane min/default/max | 120 / 220 px / 60% vh |
| Right panel collapse width | 24 px |
| Graph toolbar height | 34 px |
| Header/bottom bar height | 24 px |
| Domain pages list cap | 200 rows |
| Semantic search result cap | 50 results |
| Ctrl+A confirmation threshold | 50 nodes |
| LLM worker batch size | 5 jobs |
| LLM worker retry interval (Ollama down) | 30 s |
| Monitor interval minimum | 0.25 hours |
