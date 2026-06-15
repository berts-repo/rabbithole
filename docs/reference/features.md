# Features

Rabbithole is a local-first dark-web OSINT workbench for journalism and
research. It is built around an analyst loop: crawl onion sites through Tor,
turn pages, domains, links, and entities into a graph, organize findings, and
run local search, embeddings, and LLM analysis without sending page content to
third-party services.

## Core User Workflow

1. Create or open a local project.
2. Add onion seeds manually, from bookmarks, search results, bulk import, graph
   context, or extracted entities.
3. Crawl through Tor with privacy guardrails.
4. Explore discovered pages, domains, links, entities, and infrastructure
   relationships in a graph.
5. Flag, review, annotate, collect, monitor, and analyze findings.
6. Use local search, semantic search, and Ollama-backed analysis to continue
   the investigation.

## Current Capabilities

- Local project workspaces backed by SQLite project databases.
- Loopback-only FastAPI app with local browser UI.
- Tor-routed onion crawling through SOCKS5h.
- Onion URL validation, redirect safety, size limits, content-type limits, and
  kill-switch behavior.
- Crawl modes: Cross-site, BFS, DFS, Diverse, and Focused.
- Watchlist terms for focused crawling and automatic flagging.
- Saved seed bookmarks and scheduled crawls.
- Resource lifecycle states (`unknown` / `known` / `crawled` / `dead`) replacing
  the old crawled-vs-stub split; a URL can be saved as "known" without crawling.
- Page versioning: every re-crawl appends a snapshot, with a right-pane version
  timeline + picker and an on-demand text diff between any two versions; monitors
  surface content changes against the latest snapshot.
- Unified Activity view: one bottom-pane tab over the `jobs` table covering
  crawls, scheduled firings, analyses, monitor probes, live-crawl progress, and
  batch intake, with per-row cancel / retry / pause / resume.
- Job-history retention (Settings → Retention): `retention.jobs_days` deletes
  terminal job-tracking rows older than N days (0 = keep forever), applied at
  startup and via `POST /api/retention/run`. Scoped to bookkeeping only — page
  snapshots, the version-history record, and analyses are never pruned.
- Page graph generation from crawled nodes and links.
- Graph metrics including PageRank, betweenness, Louvain clusters, bridge
  detection, and infrastructure clusters.
- Interactive graph canvas with workspace tabs, selection, multi-select, ego
  focus, layouts, graph filters, domain grouping, and exports.
- NodeSet workspaces: open any bottom-pane node set (a domain, a flagged set, a
  fingerprint cluster, bookmarks, or a graph multi-selection) as its own graph
  tab scoped to the induced subgraph of those nodes, filtered client-side from
  the loaded global payload.
- Inventory: a read-only bottom-pane overview of what's loaded into the current
  workspace — open graph tabs (click to focus), domains in the current graph
  (sorted by node count, click to highlight), and aggregate counts. Reflects
  the active workspace's rendered scope.
- Analyzed: a read-only bottom-pane list of every node with at least one
  successful completed LLM analysis (one row per node, dropped results excluded
  server-side), showing the distinct analysis types and last-analyzed time, with
  URL/title filter and refresh. Row click is a full select, driving the
  right-pane Analysis tab.
- Project-wide labeling for pages and domains: seven recolorable preset labels
  (Market, Forum, Directory, Blog, Service, Scam, Avoid) plus custom labels,
  applied from the shared right-click menu / right-panel action bar. A single
  analyst-controlled rank orders the picker, drives the "dominant label" graph
  color mode, and resolves collapse. Surfaced across a bottom-pane Labels tab
  (member counts + expand), a left-pane label browser in the Find sub-tab
  (highlight a label's members in the current graph), a graph color-by-label
  mode and include/exclude label filter, and a Settings → Labels tab (preset
  hide toggles, custom CRUD, colors, drag-reorder). Pages also gain an analyst
  alias (rename) alongside the existing domain alias, on the same rename seam.
- Graph collapse: fold many nodes into one summary node that stays on the
  canvas — distinct from Hide (which removes nodes). Collapse by domain
  (alias-aware) or by one or more labels; a page folds into the highest-ranked
  collapsed label it carries, with domain at the floor of the same ranking, and
  folded nodes show overlap counts. Collapse state persists per workspace tab.
- Collections for grouping pages and exporting investigation sets.
- Flags, notes, reviewed state, hidden graph filters, and analyst-created
  edges.
- Domain profiles, aliases, page lists, extracted entities, and uptime
  monitors.
- Fingerprint clustering from shared HTTP response headers.
- Local keyword search over crawled page text.
- Local semantic search using fastembed and sqlite-vec.
- Local LLM analysis through Ollama, including summaries, risk scores,
  categories, entities, Q&A, domain labels, and collection- and cluster-level
  synthesis. Auto-analysis rules (crawl + collection-add triggers) and
  project-local prompt templates back the analyzers.
- Search-engine backed dark-web discovery through Tor, with streamed results
  and optional probing.
- Settings for graph behavior, engines, watchlist, browser launch, embeddings,
  labels, and existing backend defaults. Tor / Privacy, Crawl & Queue,
  LLM / Ollama, and Retention tabs are still planned.
- Security guardrails for local auth, Origin/Host checks, CSP, path validation,
  Tor-only network egress, and build-blocking lint rules.

## Planned Or In Progress

- Settings Wave 2:
  - Tor / Privacy settings.
  - Crawl & Queue settings.
  - LLM / Ollama settings.
  - Retention settings for page versions, job history, and logs.
- Find result-row polish:
  - Entity-value context menu for Find entity rows.
  - Open Find result sets as graph tabs through the NodeSet workspace model.
- Prompt-template management UI + body substitution. The typed
  `prompt_templates` table, built-in seeds, and `prompt_id` provenance ship; the
  management UI and worker body-substitution are deferred to a focused
  follow-up. Editable bodies should drive the model only for free-form types
  (Summary / Q&A / Entities); typed contract types (Risk Score, Category, Domain
  Label) stay on audited backend prompt text.
- Crawler privacy cleanup:
  - Tor Browser-like request headers instead of a unique Rabbithole user agent.
  - Per-onion-host Tor circuit isolation.
  - Crawl pacing profiles: fast, polite, stealth.

## Future Or Deferred

- I2P support:
  - `.i2p` crawling through a local I2P router proxy.
  - Separate Tor and I2P network backends.
  - I2P-specific resolution metadata and browser/profile separation.
- Optional at-rest project database encryption, enabled later by standardizing
  the DB access path.
- Cross-country and cross-language exploration:
  - Operator-chosen Tor exit geography where applicable.
  - On-device translation for foreign-language page content.

## Product Boundaries

Rabbithole is not a hosted SaaS product, marketing site, or multi-user
platform. It is a local analyst workbench.

The current threat model prioritizes privacy toward malicious onion sites and
relays. Physical/device security, seizure resistance, and full at-rest
encryption are deferred unless the project threat model changes.
