# Frontend Structure

The frontend is a Svelte 5 app built with Vite. It is developed separately on
Vite's dev server and built into `backend/public` for production serving by the
FastAPI backend.

## Entrypoints

| File | Role |
| --- | --- |
| `frontend/src/main.ts` | Imports global CSS, bootstraps the backend session cookie in dev via `/__session`, and mounts the Svelte app. |
| `frontend/src/app.svelte` | Starts top-level stores and pollers, loads project/settings/workspace state, and renders `AppShell`. |
| `frontend/src/views/AppShell.svelte` | Main application grid: header, Tor banner, left sidebar, center tab, right panel, bottom pane, splitters, project picker, settings modal, kill-switch alert, toast host. |

## Views

Views live in `frontend/src/views/` and represent major shell regions.

| File | Role |
| --- | --- |
| `AppShell.svelte` | Overall application layout. |
| `LeftSidebar.svelte` | Crawl/search/navigation side area. |
| `GraphTab.svelte` | Main graph workspace. |
| `SearchTab.svelte` | Search workspace. |
| `RightPanel.svelte` | Node/domain/detail side panel. |
| `BottomPane.svelte` | Lower activity/log/status area. |

## Components

General components live directly under `frontend/src/components/`.

Feature components are grouped by subdirectory:

- `components/graph/` contains graph canvas, graph toolbar, tooltips, overlays,
  context menus, workspace tabs, and graph-specific controls.
- `components/crawl/` contains crawl controls, bulk import, and scheduled
  crawl UI.
- `components/modals/` contains shared and feature-specific modals, including
  `SettingsModal.svelte` (the gear-icon settings panel) and its left-rail tab
  components under `components/modals/settings/` (Graph, Labels, Engines,
  Watchlist, Tor / Privacy, Crawl & Queue, Browser, LLM / Ollama, Embedding).
  Each tab autosaves per control via `PUT /api/settings/{key}` (or a dedicated
  CRUD route for the Engines / Watchlist list tabs). The Graph tab's filter
  controls are the shared
  `components/graph/GraphFilterControls.svelte`, also embedded in the graph
  toolbar's `FilterShelf.svelte`.
- `views/left/intel/` contains the Intel sub-tab sections (Analyse compose form,
  worker controls, auto-analysis rules, embedding, collection analysis).

Analysis compose has one path per target kind, each writing to its own table:
**nodes** funnel through `views/left/intel/ComposeForm.svelte` (every node
"Queue Analysis" surface — graph menu, right-pane action bar, right-pane
Analysis tab — stages a node target via `lib/contextMenu/actions.ts`
`queueAnalysis` rather than opening a modal); **collections** compose in
`CollectionAnalysis.svelte`; **clusters** compose inline in
`views/right/cluster/QnATab.svelte`, which keys answers by a membership
fingerprint (`views/right/cluster/fingerprint.ts`, pinned to the backend by
test). The old `QueueAnalysisModal` is gone.

Icon components come from `lucide-svelte`.

## API Client

`frontend/src/lib/api/` is the typed API client. It uses same-origin `fetch`
against `/api/*`; the backend session cookie is sent automatically.

When adding a backend route that the UI calls, add the matching request/response
types and client function in the relevant `frontend/src/lib/api/` domain module
rather than scattering raw `fetch` calls through components.

## Stores

Stores live in `frontend/src/lib/stores/` and use Svelte 5 rune-style state.

Important stores:

| Store | Role |
| --- | --- |
| `projects.svelte.ts` | Project list and active project state. |
| `services.svelte.ts` | Tor and kill-switch state. |
| `crawl.svelte.ts` | Active crawl and crawl controls state. |
| `jobs.svelte.ts` | Unified work/Activity state over the `jobs` table (SSE-fed), backing the bottom-pane Activity tab across all job kinds. |
| `graph.svelte.ts` | Graph payload and Graphology instance. |
| `selection.svelte.ts` | Current graph/node selection. |
| `graphFilters.svelte.ts` | Render-time graph filtering options. |
| `graphLayout.svelte.ts` | Graph layout choice and layout settings. |
| `layout.svelte.ts` | Shell pane dimensions and collapse state. |
| `workspace.svelte.ts` | Center tab state for `global`, `collection`, and `nodeset` workspaces. A `nodeset` tab carries a typed `NodeSetSource` (domain, flag, fingerprint, bookmarks, label, hidden, or selection); derived sources re-evaluate membership from the live payload on each compute, captured sources freeze their member ids at open. Tabs persist across sessions and dedup by source signature. |
| `workspaceSnapshots.svelte.ts` | Graph viewport/layout snapshots per workspace. |
| `intelCompose.svelte.ts` | Staged node-compose target buffer (over the rune/DOM-free `intelComposeTarget.ts`) + per-section collapse state. Surfaces that "Queue Analysis" stage a node target here and switch to the Intel tab; the Analyse form drains it. |
| `toast.svelte.ts` | Toast messages. |

## Pollers And SSE

Pollers live in `frontend/src/lib/pollers/` and are started from
`app.svelte` or feature components.

| Poller | Role |
| --- | --- |
| `torStatus.svelte.ts` | Periodic Tor reachability status. |
| `killSwitch.svelte.ts` | Kill-switch state polling. |
| `stats.svelte.ts` | Project-wide counts for the bottom-pane Flags/Monitors tab badges. |
| `crawlStatus.svelte.ts` | Active crawl state. |
| `graph.svelte.ts` | Graph payload refresh. |

`frontend/src/lib/sse.svelte.ts` owns browser-side SSE plumbing for live
server events.

## Graph Code

Graph rendering and layout are split across:

- `components/graph/GraphCanvas.svelte` for Sigma rendering and interaction.
- `lib/stores/graph.svelte.ts` for Graphology graph construction and payload
  state.
- `lib/graph/layouts/` for layout implementations.
- `lib/graph/expand.ts` for collection expansion helpers over the in-memory
  graph.

The backend computes graph metrics and returns `/api/graph`; the frontend owns
render filtering, viewport state, interaction state, and layout presentation.

## Build Output

`frontend/vite.config.ts` writes production assets to `../backend/public`:

- `backend/public/bundle.js`
- `backend/public/bundle.css`

The Makefile `build` target checks that exactly those top-level JS/CSS files
exist after a production build.
