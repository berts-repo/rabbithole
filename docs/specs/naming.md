# Naming Review

This document is an owner-review inventory for user-facing naming and terminology in Rabbithole. It is meant to collect the terms that may need review, renaming, or standardization across the product, docs, and exports. Current code and `docs/reference/` remain the source of truth for current behavior.

Rows that are only partially surfaced, stubbed, or otherwise not yet confirmed in the live UI should be treated as `needs verification` even if they appear in the spec docs.

## Naming Principles

- Keep the vocabulary aligned with a local-first OSINT workbench for journalists and researchers.
- Prefer dense, operational names that fit repeated analyst workflows.
- Use privacy and Tor terminology precisely when safety boundaries matter.
- Avoid generic SaaS language, marketing language, and vague product names.
- Keep one canonical term per concept where possible.
- Do not blur Tor/onion safety concepts with ordinary browser or network language.

## Owner Decisions Needed

| Current name | Surface | Why review | Suggested direction | Status |
| --- | --- | --- | --- | --- |
| `Explore` | Main tab label | The center tab is named differently from the graph workspace it contains. | Keep `Explore` for the top-level tab and `Graph` for the canvas/workspace inside it. | keep |
| `Collection` vs `Workspace` vs `Project` | Core object model | The app uses all three for different scopes, which can be confusing. | Keep `Project` for the local DB, `Collection` for item groups, `Workspace` for graph-tab state. | keep |
| `Bookmarks` vs `Seed bookmarks` | Crawl / bottom pane | The same saved URLs are called bookmarks and seeds in different places. | Canonical term in docs: `Seed bookmarks`; compact UI label: `Bookmarks` where space is tight. | review |
| `Flags` / `Flag` / `Marked reviewed` | Investigation workflow | Several labels cover adjacent states and could be simplified. | Keep `Flag` as the noun, with explicit lifecycle statuses. | review |
| `Hidden` | Bottom pane and graph filters | The tab name and action label are terse and potentially ambiguous. | Consider `Filters` or `Graph filters` as the canonical term. | review |
| `Embedding` | Settings and Intel | Singular/plural naming is inconsistent with the service behavior. | Decide whether the user-facing label should be `Embedding` or `Embeddings`. | review |
| `Q&A` | Analysis type | Punctuation-based names are harder to scan in menus and filters. | Keep if desired for brevity, otherwise consider `Questions`. | review |
| `Open in Tor Browser` | Browser action | This name is precise, but the behavior is more specific than a generic browser open. | Keep, because it communicates the Tor boundary clearly. | keep |
| `Kill switch` | Safety control | This is a core security concept and should stay distinct from pause/resume language. | Keep `Kill switch`; do not rename it to `Pause`. | keep |
| `Focused` | Crawl mode | The mode meaning is tied to watchlist scoring, not ordinary focus. | Consider whether `Focused` is the clearest term or whether `Watchlist` is better. | review |

## Product Surfaces

### App Shell And Global Navigation

| Current name | Type | Where found | User-facing meaning | Naming concern, if any | Rename candidate | Decision status |
| --- | --- | --- | --- | --- | --- | --- |
| `Search` | tab | `docs/specs/app-shell.md`, `frontend/src/views/AppShell.svelte`, `frontend/src/views/LeftSidebar.svelte` | Top-level search workspace | Clear and stable | keep | keep |
| `Explore` | tab | `docs/specs/app-shell.md`, `docs/specs/index.md` | Top-level investigation workspace | May be too generic compared with the graph it hosts | `Graph` | review |
| `Search`, `Intel`, `Crawl` | left sidebar tabs | `docs/specs/app-shell.md`, `frontend/src/views/LeftSidebar.svelte` | Sub-tabs inside the investigation shell | Clear as a trio | keep | keep |
| `Page`, `Domain`, `Analysis` | right panel tabs | `docs/specs/right-pane.md`, `frontend/src/views/RightPanel.svelte` | Detail tabs for a selected item | Good vocabulary, but `Analysis` overlaps with queue terminology | keep | keep |
| `Collection`, `Bookmarks`, `Live Crawl`, `Analyses`, `Domains`, `Flags`, `Fingerprints`, `Hidden` | bottom pane tabs | `docs/specs/explore-bottom-pane.md`, `frontend/src/views/BottomPane.svelte` | Sequential investigation strip | `Hidden` is the main outlier | review | review |
| `Open project` | modal title | `frontend/src/components/ProjectPickerModal.svelte` | Project picker overlay | Describes the action clearly | keep | keep |
| `Settings` | modal title | `frontend/src/components/SettingsStubModal.svelte`, `docs/specs/explore-left-pane-settings.md` | App settings surface | Clear | keep | keep |
| `Tor` | status pill label | `docs/specs/app-shell.md`, `frontend/src/components/TorPill.svelte` | Connectivity status | Good shorthand, but must stay tied to Tor specifically | keep | keep |
| `LLM` | status pill label | `docs/specs/app-shell.md` | Local model worker status | Clear inside the analyst UI, but opaque to non-domain users | keep | keep |
| `Kill switch` | status / safety control | `docs/specs/app-shell.md`, `frontend/src/components/KillSwitchToggle.svelte`, `frontend/src/components/KillSwitchAlert.svelte` | App-wide network safety gate | Must stay distinct from pause/resume semantics | keep | keep |
| `Resume` | toolbar action | `frontend/src/components/graph/GraphToolbar.svelte` | Re-arm the kill switch and resume polling | Could be mistaken for a generic pause/resume control | review | review |

### Search vs. Find

**Resolved 2026-06-09 (item 8.5).** Two surfaces previously both read "Search"
and did opposite things. The distinction is now fixed in the vocabulary, mirroring
the browser *Search the web* vs *⌘F Find on page* convention:

- **Search** — the engine tab (`search-tab.md`, `SearchTab.svelte`): outbound
  discovery, query external dark-web engines for new onions you don't have.
- **Find** — the left-pane lookup sub-tab (`explore-left-pane-find.md`): inbound
  lookup (keyword FTS5 + semantic) over data you already crawled.

The rows below inventory the **Find** sub-tab's strings.

| Current name | Type | Where found | User-facing meaning | Naming concern, if any | Rename candidate | Decision status |
| --- | --- | --- | --- | --- | --- | --- |
| `Search tab` | feature name | `docs/specs/explore-left-pane-find.md`, `frontend/src/views/SearchTab.svelte` | Keyword and semantic lookup surface | Clear | keep | keep |
| `Keyword` | mode | `docs/specs/explore-left-pane-find.md` | Full-text search mode | Clear | keep | keep |
| `Semantic` | mode | `docs/specs/explore-left-pane-find.md` | Vector search mode | Clear, but technical | keep | keep |
| `Find in crawled data…` | placeholder | `docs/specs/explore-left-pane-find.md` | Input hint for the search box | Good operational phrasing | keep | keep |
| `No results.` | empty state | `docs/specs/explore-left-pane-find.md` | No keyword matches | Fine | keep | keep |
| `No semantic matches.` | empty state | `docs/specs/explore-left-pane-find.md` | No vector matches | Fine | keep | keep |
| `Semantic search is unavailable` | error state | `docs/specs/explore-left-pane-find.md` | Embedding service not ready | Clear | keep | keep |
| `Send to Find` | row action | `docs/specs/explore-left-pane-find.md`, `docs/specs/right-pane.md`, `docs/specs/explore-bottom-pane.md` | Push a selected value into search | Clear but repetitive | keep | keep |

### Explore / Graph

| Current name | Type | Where found | User-facing meaning | Naming concern, if any | Rename candidate | Decision status |
| --- | --- | --- | --- | --- | --- | --- |
| `Graph tab` | feature name | `docs/specs/explore-graph.md`, `frontend/src/views/GraphTab.svelte` | Central graph workspace | Stable | keep | keep |
| `Workspace tabs` | feature name | `docs/specs/explore-graph.md`, `frontend/src/components/graph/WorkspaceTabs.svelte` | Global + collection graph tabs | Can be confused with product projects | keep | keep |
| `Global` | workspace tab | `docs/specs/explore-graph.md` | Full-project graph scope | Clear in context | keep | keep |
| `Collection` | workspace tab type | `docs/specs/explore-graph.md` | Graph scope filtered to a collection | Overlaps with the main collection concept | keep | review |
| `Draw analyst edge` | action | `docs/specs/explore-graph.md`, `frontend/src/components/graph/GraphToolbar.svelte` | Create analyst-authored edges | Good, explicit | keep | keep |
| `Add to Collection` | modal/action | `docs/specs/explore-graph.md`, `frontend/src/components/modals/CollectionPickerModal.svelte` | Add selected nodes to a collection | Capitalization varies by surface | keep | keep |
| `Expand to collection` | toolbar popover | `frontend/src/components/graph/GraphToolbar.svelte` | Add nodes within N hops to a collection | Phrase is descriptive but slightly awkward | `Expand to Collection` | review |
| `Graph layout` | select label | `frontend/src/components/graph/GraphToolbar.svelte` | Layout chooser | Clear | keep | keep |
| `Force`, `Radial`, `Hierarchical`, `Concentric`, `Timeline` | layout modes | `docs/specs/explore-graph.md`, `frontend/src/components/graph/GraphToolbar.svelte` | Graph arrangement modes | `Force` is the only technical one; it may deserve `ForceAtlas2` in docs | review | review |
| `Stop` | toolbar action | `docs/specs/explore-graph.md`, `frontend/src/components/graph/GraphToolbar.svelte` | Stop a settling layout | Can read like a generic stop button | keep | keep |
| `Fit` | toolbar action | `frontend/src/components/graph/GraphToolbar.svelte` | Fit graph to viewport | Fine | keep | keep |
| `Reset layout` | toolbar action | `frontend/src/components/graph/GraphToolbar.svelte` | Re-run layout from scratch | Clear | keep | keep |
| `Export graph` | toolbar action | `frontend/src/components/graph/GraphToolbar.svelte` | Open export menu | Clear | keep | keep |
| `GEXF (.gexf)` | export option | `docs/specs/explore-graph.md`, `backend/backend/routes/graph.py` | Graph export format | Technical but standard | keep | keep |
| `Nodes CSV (.csv)` | export option | `docs/specs/explore-graph.md`, `backend/backend/routes/graph.py`, `backend/backend/export/csv.py` | Flat node export | Clear enough | keep | keep |
| `Crawl selected` | context action | `docs/specs/explore-graph.md` | Queue selected stubs for crawl | Clear | keep | keep |
| `Hide from Graph` | context action | `docs/specs/explore-graph.md`, `docs/specs/right-pane.md` | Add a graph filter term | Good action label, but the underlying concept is a filter | keep | keep |
| `Focus` | context action | `docs/specs/explore-graph.md` | Enter ego-focus mode | Clear | keep | keep |
| `Cluster` | layout and color mode term | `docs/specs/explore-graph.md`, `docs/specs/explore-left-pane-settings.md` | Community grouping | Technical but meaningful | keep | keep |

### Crawl

| Current name | Type | Where found | User-facing meaning | Naming concern, if any | Rename candidate | Decision status |
| --- | --- | --- | --- | --- | --- | --- |
| `Crawl` | feature name | `docs/specs/crawl-left-pane.md`, `frontend/src/components/CrawlSidebar.svelte` | URL discovery and fetch workflow | Core term, stable | keep | keep |
| `Seed URL` | field label | `docs/specs/crawl-left-pane.md`, `frontend/src/components/crawl/CrawlControls.svelte` | Crawl starting point | Clear | keep | keep |
| `Saved seeds` | bookmark menu label | `frontend/src/components/crawl/CrawlControls.svelte` | Saved crawl seeds | Reasonable, but a little terse | `Seed bookmarks` | review |
| `Save current URL` | action | `frontend/src/components/crawl/CrawlControls.svelte` | Save current seed | Clear | keep | keep |
| `Mode` | field label | `docs/specs/crawl-left-pane.md` | Crawl mode selector | Generic, but acceptable in context | keep | keep |
| `Cross-site`, `BFS`, `DFS`, `Diverse`, `Focused` | crawl modes | `docs/specs/crawl-left-pane.md`, `frontend/src/components/crawl/CrawlControls.svelte` | Crawl traversal strategies | `Focused` is the least self-explanatory | review | review |
| `Stay on domain` | checkbox | `docs/specs/crawl-left-pane.md`, `frontend/src/components/crawl/CrawlControls.svelte` | Restrict crawl to the current host | Clear | keep | keep |
| `Add results to collection` | field label | `docs/specs/crawl-left-pane.md` | Auto-add crawl results to a collection | Clear | keep | keep |
| `Start` / `Stop` | buttons | `docs/specs/crawl-left-pane.md`, `frontend/src/components/crawl/CrawlControls.svelte` | Start or stop a crawl | Generic but standard | keep | keep |
| `Bulk Import` | section title | `docs/specs/crawl-left-pane.md`, `frontend/src/components/crawl/BulkImport.svelte` | Paste many URLs at once | Clear | keep | keep |
| `Paste domains or URLs, one per line…` | placeholder | `frontend/src/components/crawl/BulkImport.svelte` | Bulk import input hint | Good, but slightly long | keep | keep |
| `Crawl` | bulk action | `frontend/src/components/crawl/BulkImport.svelte` | Send a pasted line into crawl | Clear | keep | keep |
| `+ Stub` | bulk action | `docs/specs/crawl-left-pane.md`, `frontend/src/components/crawl/BulkImport.svelte` | Create an uncrawled node | Technical but accurate | keep | keep |
| `Scheduled Crawls` | section title | `docs/specs/crawl-left-pane.md`, `frontend/src/components/crawl/ScheduledCrawls.svelte` | Recurring crawl jobs | Clear | keep | keep |
| `+ Add` | schedule action | `frontend/src/components/crawl/ScheduledCrawls.svelte` | Add a schedule | Generic but fine | keep | keep |
| `Pause` / `Resume` | schedule toggle | `frontend/src/components/crawl/ScheduledCrawls.svelte` | Toggle a schedule on or off | Could be confused with kill switch resume | review | review |
| `No saved seeds.` | empty state | `frontend/src/components/crawl/CrawlControls.svelte` | Empty bookmark list | Fine | keep | keep |
| `No scheduled crawls.` | empty state | `frontend/src/components/crawl/ScheduledCrawls.svelte` | Empty schedule list | Fine | keep | keep |

### Intel And Analysis

| Current name | Type | Where found | User-facing meaning | Naming concern, if any | Rename candidate | Decision status |
| --- | --- | --- | --- | --- | --- | --- |
| `Intel` | tab | `docs/specs/app-shell.md`, `frontend/src/views/LeftSidebar.svelte` | AI analysis control panel | Domain-specific, but acceptable | keep | keep |
| `LLM Service` | section title | `docs/specs/explore-left-pane-intel.md` | Background analysis worker | Clear | keep | keep |
| `Analyse` | section title | `docs/specs/explore-left-pane-intel.md` | Queue a single-node analysis | British spelling is intentional but worth checking for consistency | keep | review |
| `Embedding Model` | section title | `docs/specs/explore-left-pane-intel.md` | Vector embedding worker | Singular/plural consistency issue | review | review |
| `Collection Analysis` | section title | `docs/specs/explore-left-pane-intel.md` | Batch analysis over a collection | Clear | keep | keep |
| `Summary` | analysis type | `docs/specs/explore-left-pane-intel.md`, `backend/backend/prompts.py` | Short prose summary | Clear | keep | keep |
| `Risk Score` | analysis type | `docs/specs/explore-left-pane-intel.md`, `backend/backend/prompts.py` | Integer severity score | Clear | keep | keep |
| `Entities (LLM)` | analysis type | `docs/specs/explore-left-pane-intel.md`, `backend/backend/prompts.py` | Entity extraction by model | Parenthetical suffix is awkward | `Entities` | review |
| `Category` | analysis type | `docs/specs/explore-left-pane-intel.md`, `backend/backend/prompts.py` | Page classification | Clear | keep | keep |
| `Domain Label` | analysis type | `docs/specs/explore-left-pane-intel.md`, `backend/backend/prompts.py` | Human-readable domain label | Clear | keep | keep |
| `Q&A` | analysis type | `docs/specs/explore-left-pane-intel.md`, `backend/backend/prompts.py` | Natural-language question answering | Punctuation-based term can be harder to scan | review | review |
| `Cluster Summary` | collection analysis type | `docs/specs/explore-left-pane-intel.md` | Collection synthesis by cluster | Clear | keep | keep |
| `Site Relationships` | collection analysis type | `docs/specs/explore-left-pane-intel.md` | Collection synthesis about relationships | Clear | keep | keep |
| `Investigation Digest` | collection analysis type | `docs/specs/explore-left-pane-intel.md` | Summary for analyst review | Strong, useful name | keep | keep |
| `Seed Suggestions` | collection analysis type | `docs/specs/explore-left-pane-intel.md` | Suggested next crawl seeds | Clear | keep | keep |
| `Embed service` | runtime term | `docs/specs/explore-left-pane-intel.md`, `docs/specs/explore-left-pane-settings.md` | Background embedding worker | Slightly technical, but accurate | keep | keep |

### Collections / Bookmarks / Flags / Notes

| Current name | Type | Where found | User-facing meaning | Naming concern, if any | Rename candidate | Decision status |
| --- | --- | --- | --- | --- | --- | --- |
| `Collection` | concept | `docs/specs/explore-graph.md`, `docs/specs/explore-bottom-pane.md`, `frontend/src/lib/api/types.ts` | Grouping of URLs/pages | Core noun, but easy to confuse with workspace or project | keep | review |
| `Bookmarks` | bottom pane tab | `docs/specs/explore-bottom-pane.md` | Saved seed URLs | Could be too generic | `Seed bookmarks` | review |
| `Save as Seed Bookmark` | context action | `docs/specs/explore-graph.md` | Save URL for later crawling | Clear, but long | keep | keep |
| `In collections` | right panel section | `docs/specs/right-pane.md` | Membership list | Clear | keep | keep |
| `Remove from collection` | action | `docs/specs/explore-bottom-pane.md`, `docs/specs/right-pane.md` | Remove one URL from a collection | Clear | keep | keep |
| `Add to collection` | action | `docs/specs/explore-graph.md`, `docs/specs/explore-bottom-pane.md`, `docs/specs/right-pane.md` | Add selected URLs to a collection | Lowercase `collection` varies by surface | keep | keep |
| `Flag` | noun/action | `docs/specs/explore-graph.md`, `docs/specs/explore-bottom-pane.md`, `docs/specs/right-pane.md` | Investigation marker | Could be confused with status instead of object | keep | review |
| `Mark Reviewed` / `Mark Unreviewed` | action | `docs/specs/explore-graph.md`, `docs/specs/right-pane.md` | Toggle review state | Clear, but overlaps with `Flag` lifecycle | keep | review |
| `Reviewed` | toggle label | `docs/specs/right-pane.md` | Review boolean | Clear | keep | keep |
| `Exclude from analysis` | toggle label | `docs/specs/right-pane.md` | Skip auto-queue and analysis | Clear | keep | keep |
| `Notes` | section | `docs/specs/right-pane.md` | Analyst notes per node | Clear | keep | keep |
| `Save note` | action | `docs/specs/right-pane.md` | Persist a note | Clear | keep | keep |
| `Flagged nodes` | overlay | `docs/specs/explore-left-pane-settings.md` | Highlight flagged nodes in graph | Clear | keep | keep |
| `Priority` | flag field | `docs/specs/right-pane.md` | High / Medium / Low ranking | Clear, but generic on its own | keep | keep |
| `pending`, `investigating`, `done`, `dismissed` | flag status | `docs/specs/right-pane.md`, `frontend/src/lib/api/types.ts` | Flag lifecycle states | `pending` and `investigating` are easy to conflate | keep | review |

### Right Panel

| Current name | Type | Where found | User-facing meaning | Naming concern, if any | Rename candidate | Decision status |
| --- | --- | --- | --- | --- | --- | --- |
| `Page` | tab | `docs/specs/right-pane.md` | Per-page details | Clear | keep | keep |
| `Domain` | tab | `docs/specs/right-pane.md` | Host-level details | Clear | keep | keep |
| `Analysis` | tab | `docs/specs/right-pane.md` | Analysis results for the selected node | Overlaps with queue terminology, but still useful | keep | keep |
| `Crawl now` | action | `docs/specs/right-pane.md` | Send a stub to crawl | Clear | keep | keep |
| `Response Headers` | detail section | `docs/specs/right-pane.md` | HTTP headers for the page | Clear | keep | keep |
| `Version History` | detail section | `docs/specs/right-pane.md` | Historical crawls of the page | Clear | keep | keep |
| `Entities` | detail section | `docs/specs/right-pane.md` | Extracted entities | Clear | keep | keep |
| `Add monitor` | form action | `docs/specs/right-pane.md` | Create uptime monitor | Clear | keep | keep |
| `Open in Tor Browser` | row action | `docs/specs/right-pane.md` | Open a URL in Tor Browser | Important safety cue | keep | keep |
| `Node not found` | error state | `docs/specs/right-pane.md` | Missing detail record | Clear | keep | keep |

### Bottom Pane

| Current name | Type | Where found | User-facing meaning | Naming concern, if any | Rename candidate | Decision status |
| --- | --- | --- | --- | --- | --- | --- |
| `Collection` | bottom pane tab | `docs/specs/explore-bottom-pane.md` | Collection contents | Conflicts with other uses of collection | keep | review |
| `Bookmarks` | bottom pane tab | `docs/specs/explore-bottom-pane.md` | Saved seed URLs | Same naming issue as above | keep | review |
| `Live Crawl` | bottom pane tab | `docs/specs/explore-bottom-pane.md` | SSE crawl log | Clear | keep | keep |
| `Analyses` | bottom pane tab | `docs/specs/explore-bottom-pane.md` | Queue/history of analysis jobs | Clear | keep | keep |
| `Domains` | bottom pane tab | `docs/specs/explore-bottom-pane.md` | Domain list and counts | Clear | keep | keep |
| `Flags` | bottom pane tab | `docs/specs/explore-bottom-pane.md` | Flagged URLs | Clear | keep | keep |
| `Fingerprints` | bottom pane tab | `docs/specs/explore-bottom-pane.md` | Shared-header clustering | Clear | keep | keep |
| `Hidden` | bottom pane tab | `docs/specs/explore-bottom-pane.md` | Graph suppression terms | Most likely candidate for renaming | `Graph filters` | review |
| `Send to Find` | row action | `docs/specs/explore-bottom-pane.md` | Push a domain into search | Clear | keep | keep |
| `Send to Crawl` | row action | `docs/specs/explore-bottom-pane.md` | Push a URL into crawl | Clear | keep | keep |
| `Open in Tor Browser` | row action | `docs/specs/explore-bottom-pane.md` | Launch URL in Tor Browser | Clear and precise | keep | keep |

### Settings

| Current name | Type | Where found | User-facing meaning | Naming concern, if any | Rename candidate | Decision status |
| --- | --- | --- | --- | --- | --- | --- |
| `Graph` | settings tab | `docs/specs/explore-left-pane-settings.md` | Graph rendering controls | Clear | keep | keep |
| `Engines` | settings tab | `docs/specs/explore-left-pane-settings.md` | Search engine registry | Clear | keep | keep |
| `Watchlist` | settings tab | `docs/specs/explore-left-pane-settings.md` | Focused crawl / auto-flag terms | Clear | keep | keep |
| `Browser` | settings tab | `docs/specs/explore-left-pane-settings.md` | Launch behavior and Tor Browser path | Clear | keep | keep |
| `Embedding` | settings tab | `docs/specs/explore-left-pane-settings.md` | Embedding service control | Singular/plural mismatch with surrounding wording | review | review |
| `Domain`, `Cluster`, `Depth`, `Category`, `Infra cluster` | color modes | `docs/specs/explore-left-pane-settings.md` | Node color by attribute | `Infra cluster` is shorthand and may need explanation | keep | keep |
| `All`, `Cross-site only`, `Same-site only` | edge filter modes | `docs/specs/explore-left-pane-settings.md` | Edge visibility filter | Clear | keep | keep |
| `Show stubs` | filter | `docs/specs/explore-left-pane-settings.md` | Show uncrawled nodes | Clear | keep | keep |
| `Hide orphans` | filter | `docs/specs/explore-left-pane-settings.md` | Remove isolated nodes | Clear | keep | keep |
| `Show all edges` | filter | `docs/specs/explore-left-pane-settings.md` | Disable domain deduping | Clear | keep | keep |
| `Mutual clusters only` | filter | `docs/specs/explore-left-pane-settings.md` | Keep only strongly connected components | Technical but okay | keep | keep |
| `Fresh instance` | browser launch mode | `docs/specs/explore-left-pane-settings.md` | New isolated Tor Browser window | Strong privacy term | keep | keep |
| `Reuse existing` | browser launch mode | `docs/specs/explore-left-pane-settings.md` | Reuse a running browser session | Clear, but privacy tradeoff should stay visible | keep | keep |
| `Auto-start` | toggle | `docs/specs/explore-left-pane-settings.md` | Start embedding service with backend | Clear | keep | keep |

### Projects / Workspaces

| Current name | Type | Where found | User-facing meaning | Naming concern, if any | Rename candidate | Decision status |
| --- | --- | --- | --- | --- | --- | --- |
| `Project` | concept | `docs/specs/app-shell.md`, `frontend/src/lib/api/types.ts`, `backend/backend/routes/projects.py` | One local SQLite-backed case | Should remain distinct from collection and workspace | keep | keep |
| `New project` | form title | `frontend/src/components/ProjectPickerModal.svelte` | Create a project | Clear | keep | keep |
| `Path` | project field | `frontend/src/components/ProjectPickerModal.svelte` | DB file path | Clear, but should stay paired with `Project` | keep | keep |
| `scans/case.db` | example path | `docs/specs/app-shell.md`, `frontend/src/components/ProjectPickerModal.svelte` | Example DB filename | Good as a conventional example | keep | keep |
| `Workspace` | concept | `docs/specs/explore-graph.md`, `docs/specs/explore-bottom-pane.md` | Graph tab context, including canvas state, layout, selection, and ego-focus | Not a project; this is the graph-tab scope around the canvas | keep | keep |
| `Workspace tabs` | concept | `docs/specs/explore-graph.md` | Global and collection-scoped graph tabs | Same issue as above | keep | keep |
| `Open this collection's workspace` | tooltip | `frontend/src/components/graph/GraphToolbar.svelte` | Open a collection tab | Clear, but uses workspace language that may not be canonical | keep | review |
| `projects.json` | file | `backend/backend/services/project_state.py`, `backend/backend/routes/projects.py` | Registry of local projects | Not user-facing, but important to document | keep | keep |

### Files And Exports

| Current name | Type | Where found | User-facing meaning | Naming concern, if any | Rename candidate | Decision status |
| --- | --- | --- | --- | --- | --- | --- |
| `graph.gexf` | download filename | `backend/backend/routes/graph.py` | Full graph export file | Standard export name | keep | keep |
| `nodes.csv` | download filename | `backend/backend/routes/graph.py` | Node export file | Standard export name | keep | keep |
| `JSON` | collection export option | `docs/specs/explore-bottom-pane.md` | Collection export format | Could be made more specific if needed | keep | keep |
| `Nodes CSV` | collection export option | `docs/specs/explore-bottom-pane.md` | Collection export file format | Clear | keep | keep |
| `GEXF` | collection export option | `docs/specs/explore-bottom-pane.md` | Collection graph export | Standard graph-tool name | keep | keep |
| `scans/<slug>.db` | project file pattern | `frontend/src/components/ProjectPickerModal.svelte` | Local project database path | Important for naming conventions | keep | keep |
| `projects.json` | registry file | `backend/backend/services/project_state.py` | Project registry file | Not user-facing, but part of naming contract | keep | keep |

### Notifications / Statuses / Errors

| Current name | Type | Where found | User-facing meaning | Naming concern, if any | Rename candidate | Decision status |
| --- | --- | --- | --- | --- | --- | --- |
| `Toast` | notification mechanism | `docs/specs/app-shell.md`, `frontend/src/components/Toast.svelte` | Transient app message | Clear | keep | keep |
| `A crawl is already running.` | error message | `frontend/src/components/crawl/CrawlControls.svelte` | Crawl conflict | Clear | keep | keep |
| `Tor connection lost` | alert title | `frontend/src/components/KillSwitchAlert.svelte` | Tor outage warning | Clear and specific | keep | keep |
| `Connect to Tor` | alert title | `frontend/src/components/KillSwitchAlert.svelte` | Startup state before Tor is reachable | Clear | keep | keep |
| `Tor recovered` | status text | `frontend/src/components/KillSwitchToggle.svelte`, `docs/specs/app-shell.md` | Tor connectivity restored | Clear | keep | keep |
| `No jobs in queue.` | empty state | `docs/specs/explore-left-pane-intel.md` | Idle queue | Fine | keep | keep |
| `No results.` | empty state | `docs/specs/explore-left-pane-find.md` | Empty search result state | Fine | keep | keep |
| `No projects yet.` | empty state | `frontend/src/components/ProjectPickerModal.svelte` | Empty project registry | Fine | keep | keep |
| `Browser launched successfully` | toast | `docs/specs/explore-left-pane-settings.md` | Browser test passed | Clear | keep | keep |
| `Failed — check the path.` | toast | `docs/specs/explore-left-pane-settings.md` | Browser test failed | Clear but terse | keep | keep |
| `Start failed`, `Stop failed`, `Delete failed` | toast prefixes | `frontend/src/components/crawl/CrawlControls.svelte`, `frontend/src/components/crawl/ScheduledCrawls.svelte`, `frontend/src/components/ProjectPickerModal.svelte` | Action failure reporting | Standardized but broad | keep | keep |

### Security / Privacy / Tor Terminology

| Current name | Type | Where found | User-facing meaning | Naming concern, if any | Rename candidate | Decision status |
| --- | --- | --- | --- | --- | --- | --- |
| `Tor` | security term | `docs/specs/app-shell.md`, `docs/specs/explore-left-pane-settings.md` | Network transport and browser context | Must stay precise | keep | keep |
| `Tor Browser` | security term | `docs/specs/explore-left-pane-settings.md`, `docs/specs/right-pane.md` | Browser used for isolated opens | Clear | keep | keep |
| `Open in Tor Browser` | action | `docs/specs/explore-left-pane-settings.md`, `docs/specs/right-pane.md`, `docs/specs/explore-bottom-pane.md` | Copy and launch via Tor Browser | Strong, necessary safety cue | keep | keep |
| `Fresh instance` | browser mode | `docs/specs/explore-left-pane-settings.md` | New isolated window and circuit | Clear if the user knows the browser context | keep | keep |
| `Reuse existing` | browser mode | `docs/specs/explore-left-pane-settings.md` | Reuse an existing browser session | Privacy tradeoff should remain explicit | keep | keep |
| `SOCKS5h` | transport term | `docs/specs/explore-left-pane-settings.md`, `CONTEXT.md` | DNS-safe Tor proxy mode | Technical but important to retain | keep | keep |
| `Kill switch` | safety term | `docs/specs/app-shell.md`, `frontend/src/components/KillSwitchAlert.svelte` | App-wide outbound network safety gate | Must not be softened into pause language | keep | keep |
| `armed`, `tripped`, `cleared_idle` | FSM states | `docs/specs/app-shell.md` | Safety state machine | Backend implementation detail that is still useful in docs | keep | keep |
| `No new requests will go out` | safety copy | `frontend/src/components/KillSwitchAlert.svelte` | Explains the safety boundary | Good, explicit copy | keep | keep |
| `no DNS leaks` | project constraint | `CONTEXT.md` | Security boundary | Not a label, but important terminology | keep | keep |

## Terminology Conflicts

- `Project`, `Collection`, and `Workspace` are all active nouns and should stay separated by scope. A `Project` is the local case database, a `Collection` is a user grouping, and a `Workspace` is the graph tab context around the canvas.
- `Bookmark` and `Seed` overlap. The current UI mixes `Saved seeds`, `Seed bookmarks`, and `Bookmarks`.
- `Flag` overlaps with `Reviewed` and `Analysis excluded`. These are distinct concepts but can read like one state machine.
- `Explore` and `Graph` both describe the central investigation surface. One is a top-level tab, the other is the actual canvas/workspace.
- `Analysis`, `LLM`, `Q&A`, and `Collection Analysis` all point at the same system from different angles.
- `Page`, `Node`, `URL`, and `Domain` are all used for related but different scopes. The UI should prefer `Page` for a crawled item and `Domain` for a host.
- `Hidden`, `Hide from Graph`, and `Graph filters` all refer to suppressing nodes. `Hidden` is the least explicit term.
- `Open in Tor Browser`, `Fresh instance`, and `Reuse existing` belong to the same privacy boundary and should remain grouped in naming guidance.
- `Embed service`, `Embedding`, and `Semantic search` describe a single processing pipeline from three angles.

## Suggested Naming Map

| Concept | Recommended name | Avoid | Reason |
| --- | --- | --- | --- |
| Main case database | `Project` | `Workspace`, `Case` | Matches the current registry and UI terminology. |
| Graph tab scope | `Workspace` | `Project`, `Collection tab` | Keeps the tab-level graph state separate from the case database and the canvas distinct from the surrounding tab context. |
| User grouping | `Collection` | `Bucket`, `Folder`, `List` | Already established in the UI and backend. |
| Saved crawl seed | `Seed bookmark` | `Bookmark` alone | Makes the crawl meaning explicit. |
| Crawled item | `Page` | `Node` | Better for user-facing investigation language. |
| Host | `Domain` | `Site`, `Host` | The app already models `.onion` hosts this way. |
| Investigation marker | `Flag` | `Pin`, `Alert` | Short, established, and semantically correct. |
| Review state | `Reviewed` | `Checked`, `Done` | Clear boolean meaning. |
| Graph suppression | `Graph filters` | `Hidden` | More explicit about what the term does. |
| Local model analysis | `Analysis` | `LLM task`, `AI job` | The app already exposes analysis as the umbrella term. |
| Embedding pipeline | `Embedding` or `Embeddings` | `Vectorizer` | Decide one spelling and use it everywhere. |
| Tor safety control | `Kill switch` | `Pause` | Preserves the security boundary. |
| Isolated browser open | `Open in Tor Browser` | `Open in browser` | Keeps the Tor-specific behavior obvious. |

## Open Questions

- Should the top-level tab stay `Explore`, or should the product call the graph workspace `Graph` everywhere?
- Should the collection-scoped graph tab be called `Workspace` or something closer to `Collection view`?
- Should `Bookmarks` become `Seed bookmarks` so the saved crawl-seed meaning is explicit?
- Should `Hidden` be renamed to `Graph filters` in the bottom pane and settings?
- Should `Embedding` become `Embeddings` to match the service name and user expectation?
- Should `Q&A` remain punctuation-based, or should the analysis type move to a flatter term such as `Questions`?
- Should `Focused` crawl mode be renamed to make the watchlist dependency obvious?
- Should `Entities (LLM)` drop the parenthetical suffix and become just `Entities`?

## Maintenance Notes

Update this document when:

- user-facing labels change in the UI or backend responses
- new features add new visible names or action labels
- specs introduce new surfaces or rename existing ones
- import/export filenames change
- the project wants a new canonical term for an existing concept

This document should stay aligned with the current code, `docs/reference/`, and `docs/specs/index.md`, but it should not be used as the source of truth for behavior.
