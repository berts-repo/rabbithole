// Response + request types for every backend route. Pure types — no
// runtime — so route modules import these with `import type`.

// ---------------- Response shapes ----------------

export interface Health {
  ok: true;
}

export interface TorStatus {
  ok: boolean;
  latency_ms: number | null;
  error: string | null;
  engaged: boolean;
  consecutive_failures: number;
}

export interface Project {
  id: string;
  name: string;
  path: string;
}

export interface ProjectList {
  projects: Project[];
  active_id: string | null;
}

export interface Stats {
  domains: number;
  pages: number;
  flags: number;
  monitors: number;
}

export interface Setting<T = unknown> {
  key: string;
  value: T | null;
}

export interface Seed {
  url: string;
  label: string | null;
  added_at: string;
}

export interface Schedule {
  url: string;
  label: string | null;
  interval_hours: number;
  mode: string;
  active: 0 | 1 | boolean;
  collection_id: number | null;
}

export interface WatchlistTerm {
  id: number;
  term: string;
}

// Search-engine registry row (Settings → Engines). Per-engine enabled
// state is a separate templated setting (`search.engine.{id}.enabled`),
// not a column on this shape. See backend/backend/db/search_engines.py.
export interface SearchEngine {
  id: number;
  label: string;
  url: string;
  // Network the engine searches; derived from the URL on save ('tor' | 'i2p').
  network: string;
}

export interface EngineBody {
  label: string;
  url: string;
}

// GET /api/embed/models — 384-dim fastembed registry entries offered in
// the Embedding tab's model picker.
export interface EmbedModel {
  model: string;
  dim: number;
  size_in_GB: number | null;
  description: string | null;
}

// ---------------- Resource lifecycle + unified jobs ----------------

// Canonical resource lifecycle state (schema-reset v3) — replaces the old
// `stub` boolean everywhere a resource/page/node is surfaced.
//   unknown — referenced by a link, never queued
//   known   — queued / created but not yet fetched (the old "stub")
//   crawled — fetched at least once (has a current page_version)
//   dead    — repeatedly failed; auto-transitioned out of the active set
export type ResourceState = 'unknown' | 'known' | 'crawled' | 'dead';

// Unified work-tracking vocabulary — the `jobs` table. Every kind of work
// (crawls, scheduled fires, analyses, monitor probes, live-crawl, batch)
// reports one of these statuses; see backend/backend/db/jobs.py.
export type JobKind =
  | 'crawl'
  | 'schedule'
  | 'analysis'
  | 'probe'
  | 'live-crawl'
  | 'batch';
export type JobTargetType = 'url' | 'domain' | 'collection' | 'cluster';
export type JobStatus =
  | 'pending'
  | 'running'
  | 'done'
  | 'failed'
  | 'cancelled'
  | 'paused';

// A single jobs row — GET /api/jobs / GET /api/jobs/:id. `payload` and
// `result` are decoded JSON (kind-specific config / completion data).
export interface Job {
  id: number;
  kind: JobKind;
  target_type: JobTargetType;
  target_id: number;
  status: JobStatus;
  payload: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

// GET /api/jobs envelope — rows newest-first plus per-status totals.
export interface JobList {
  jobs: Job[];
  counts: Partial<Record<JobStatus, number>>;
}

// POST /api/jobs/batch — stage a batch intake. `urls` are validated +
// de-duped server-side; `mode` is required, the rest inherit crawl defaults.
export interface StageBatchBody {
  urls: string[];
  mode: string;
  source?: string;
  stay_on_domain?: boolean;
  max_depth?: number | null;
  collection_id?: number | null;
  collection_name_pending?: string | null;
  priority?: number;
  use_default_max_depth?: boolean;
}

// One rejected URL from staging (failed egress validation).
export interface BatchRejection {
  url: string;
  reason: string;
  message?: string;
}

// POST /api/jobs/batch result — the new pending batch job plus how many URLs
// were accepted / rejected.
export interface StageBatchResult {
  job: Job;
  staged: number;
  rejected: BatchRejection[];
}

// POST /api/jobs/:id/run result — the completed batch plus how many crawl
// children were spawned / skipped (already in-flight).
export interface RunBatchResult {
  job: Job;
  spawned: number;
  skipped: number;
}

// Node ("resource") detail as returned by GET /api/nodes/:id — see
// backend/backend/db/pages.py::get_page_detail. Combines the resources
// identity/state row, its 1:1 pages row, and the current page_versions
// snapshot. Notable shapes:
//   - state: canonical resource lifecycle (replaces the old `stub` boolean).
//   - title / status_code / body_text* come from the current page_version;
//     null when the resource has never been crawled.
//   - response_headers: Record<key, value> from the current version's headers.
//   - body_text_preview: first ~500 chars of body_text_clean (or body_text
//     fallback) — a short teaser; the Preview tab reads body_text_clean in full.
//   - history: page_versions rows for this page, newest first.
//   - entities / flag: joined from their child tables.
export interface NodeRow {
  id: number;
  url: string;
  domain: string | null;
  // Anonymity network the resource lives on ('tor' | 'i2p'), stored on the
  // resource and surfaced here so synthesized GraphNodes carry it too.
  network: string;
  state: ResourceState;
  first_seen: string | null;
  last_seen: string | null;
  last_state_change: string | null;
  // 1:1 page row — null until the resource has a page (created lazily on
  // first crawl or first analyst toggle).
  page_id: number | null;
  current_version_id: number | null;
  summary: string | null;
  category: string | null;
  reviewed: boolean;
  analysis_excluded: boolean;
  embed_excluded: boolean;
  opened_at: string | null;
  // Current page_version snapshot.
  title: string | null;
  status_code: number | null;
  body_text: string | null;
  body_text_clean: string | null;
  body_text_preview: string | null;
  response_headers: Record<string, string>;
  entities: NodeEntity[];
  history: NodeHistoryEntry[];
  flag: NodeFlag | null;
  // Label membership (item 11), ids only — resolve to name/color via the
  // catalog store. `label_ids` is directly attached; `domain_label_ids` is
  // inherited from the domain (rendered with a "via domain" badge), already
  // deduped against the direct set server-side.
  label_ids: number[];
  domain_label_ids: number[];
}

export interface NodeEntity {
  type: string;
  value: string;
  source: string;
}

// One page_versions row in a node's history — see get_page_detail. Newest
// first. `content_changed` is null on the first version (no prior to diff).
export interface NodeHistoryEntry {
  id: number;
  fetched_at: string | null;
  http_status: number | null;
  title: string | null;
  content_changed: boolean | null;
}

export interface NodeFlag {
  id: number;
  status: FlagStatus;
  source: FlagSource;
  priority: number;
  note: string | null;
}

// One full page_versions snapshot incl. body — GET /api/pages/versions/:id.
// Backs the right-pane version picker (pull up an older snapshot than the
// current one). See backend/backend/routes/pages.py::get_page_version.
export interface PageVersion {
  id: number;
  page_id: number;
  fetched_at: string | null;
  http_status: number | null;
  title: string | null;
  content_changed: boolean | null;
  body_text: string | null;
  body_text_clean: string | null;
}

// ---------------- Labels (item 11) ----------------

// A label in the taxonomy. `builtin` presets are recolorable/hideable but
// never renamable or deletable; custom labels (builtin=false) are fully
// editable and cascade their attachments on delete. `rank` is the single
// analyst ordering (lower = higher) driving picker order, dominant-label
// color, and collapse-home. Member counts come from the list endpoint.
export interface Label {
  id: number;
  name: string;
  color: string | null;
  description: string | null;
  builtin: boolean;
  rank: number;
  hidden: boolean;
  resource_count: number;
  domain_count: number;
}

export interface CreateLabelBody {
  name: string;
  color?: string | null;
  description?: string | null;
}

// PATCH /api/labels/:id — preset rename is rejected 409; `hidden` toggles a
// preset's picker visibility.
export interface UpdateLabelBody {
  name: string;
  color?: string | null;
  description?: string | null;
  hidden?: boolean;
}

// GET /api/labels/:id/members — the resources + domains carrying one label,
// for the bottom-pane Labels tab's expand row. A resource's `id` is its graph
// node id (resources.id); `alias`/`title` feed the row's display name.
export interface LabelResourceMember {
  id: number;
  url: string;
  host: string;
  alias: string | null;
  title: string | null;
}

export interface LabelDomainMember {
  host: string;
  alias: string | null;
}

export interface LabelMembers {
  resources: LabelResourceMember[];
  domains: LabelDomainMember[];
}

// On-demand text diff of two versions of the same page —
// GET /api/pages/versions/:a/diff/:b. `a` is always the older side, `b` the
// newer, regardless of arg order; `add`/`remove` read forward in time. Lines
// mirror a unified diff (hunk headers kept). See routes/pages.py::diff_page_versions.
export type DiffOp = 'hunk' | 'context' | 'add' | 'remove';

export interface VersionDiffLine {
  op: DiffOp;
  text: string;
}

export interface VersionDiffSide {
  id: number;
  page_id: number;
  fetched_at: string | null;
  http_status: number | null;
  title: string | null;
  content_changed: boolean | null;
}

export interface VersionDiff {
  a: VersionDiffSide;
  b: VersionDiffSide;
  identical: boolean;
  added: number;
  removed: number;
  truncated: boolean;
  lines: VersionDiffLine[];
}

// Notes — see GET /api/nodes/:id/notes. Newest first.
export interface NoteRow {
  id: number;
  body: string;
  created_at: string;
}

// Node ↔ collection membership row — GET /api/nodes/:id/collections.
export interface NodeCollection {
  id: number;
  name: string;
}

// /api/graph payload — see backend/backend/db/graph.py::build_payload.
// Metric fields (pagerank, betweenness, cluster_id, infra_cluster_id,
// is_bridge, in/out_degree_count) are server-computed; nulls indicate
// "no value yet" rather than "missing".
export interface GraphNode {
  id: number;
  label: string;
  alias: string | null;
  title_text: string;
  raw_url: string;
  color: string;
  domain: string | null;
  // Anonymity network the resource lives on ('tor' | 'i2p'); drives the
  // `network` colour mode.
  network: string;
  depth: number | null;
  flag_status: string | null;
  is_bridge: boolean;
  betweenness: number;
  pagerank: number;
  cluster_id: number | null;
  // Readable "Header:value" cluster signature (e.g. "Server:nginx"), not an
  // opaque id — the renderer hashes it for colour.
  infra_cluster_id: string | null;
  first_seen: string | null;
  is_cluster: boolean;
  state: ResourceState;
  analysis_excluded: boolean;
  reviewed: boolean;
  category: string | null;
  in_degree_count: number;
  out_degree_count: number;
  // Label membership (item 11), ids only — resolve via the catalog store.
  // `label_ids` is directly attached; `domain_label_ids` is inherited from
  // the node's domain, deduped against the direct set server-side.
  label_ids: number[];
  domain_label_ids: number[];
}

export interface GraphEdge {
  from: number;
  to: number;
  source: string;
  label: string | null;
}

export interface GraphPayload {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface CrawlActiveRow {
  id: number;
  seed_url: string;
  mode: string;
  status: JobStatus;
  pages_crawled: number;
  pages_failed: number;
  pages_queued: number;
  started_at: string | null;
  collection_id: number | null;
}

export interface Collection {
  id: number;
  name: string;
  description: string | null;
}

// GET /api/collections returns this shape per row — same as Collection
// plus the server-computed item count used by the Crawl-controls
// dropdown.
export interface CollectionListRow extends Collection {
  item_count: number;
}

// One member of a collection — joined with nodes for display.
export interface CollectionItem {
  id: number;
  url: string;
  title: string | null;
  state: ResourceState;
  status_code: number | null;
  domain: string | null;
}

// GET /api/collections/:id returns the meta row joined with its items.
export interface CollectionDetail extends Collection {
  items: CollectionItem[];
}

// PATCH /api/collections/:id — both fields optional, treated as "no
// change" when omitted. Empty-string name is rejected server-side.
export interface UpdateCollectionBody {
  name?: string;
  description?: string | null;
}

export type CollectionExportFormat = 'json' | 'csv' | 'gexf';

// Uptime monitor row — see backend/backend/db/monitors.py.
export interface Monitor {
  id: number;
  url: string;
  label: string | null;
  interval_hours: number;
  // Latest probe outcome, enriched from the most recent `probes` row.
  last_status: number | null;
  last_content_changed: boolean | null;
  last_checked_at: string | null;
  enabled: boolean;
  alert_on_change: boolean;
  alert_on_restore: boolean;
  downtime_threshold_hours: number;
}

// POST /api/collections/:id/items — batch membership add result.
export interface AddItemsResult {
  added: number;
  skipped: number;
}

// POST /api/analyses/batch — per-node queue outcome counts. Every known
// resource enqueues a `pending` job now, so the old `waiting` bucket is gone.
export interface AnalysesBatchResult {
  queued: number;
  skipped: number;
  unknown: number;
}

// Per-node analysis queue rows — see backend/backend/db/llm.py:list_queue.
// Status is the linked job's status (unified vocabulary).
export type AnalysisStatus = JobStatus;

export interface AnalysisRow {
  id: number;
  resource_id: number;
  analysis_type: string;
  model: string | null;
  // From the linked kind='analysis' job; null if the job row is missing.
  status: AnalysisStatus | null;
  job_id: number | null;
  result: string | null;
  question: string | null;
  priority: number;
  created_at: string | null;
  updated_at: string | null;
}

export type AnalysisQueueCounts = Partial<Record<JobStatus, number>>;

// One node with ≥1 successful completed analysis — the bottom-pane "Analyzed"
// tab row. `analysis_types` is the distinct set of types that landed (the
// server splits its comma-joined form); `last_analyzed` is the most recent
// job finish time.
export interface AnalyzedNodeRow {
  node_id: number;
  url: string;
  title: string | null;
  state: ResourceState;
  analysis_types: string[];
  last_analyzed: string | null;
}

// GET /api/llm/status — the worker snapshot, including the item-7 load block
// (capacity = jobs drained per tick; in_flight / queue_depth from live counts).
// See backend/backend/services/llm_worker.py:snapshot.
export interface LlmStatus {
  status: string;
  paused: boolean;
  model: string;
  ollama_url: string;
  processed: number;
  failures: number;
  queue: AnalysisQueueCounts;
  capacity: number;
  in_flight: number;
  queue_depth: number;
}

// GET /api/embed/status — embedding worker snapshot. Lifecycle (start/stop)
// lives in Settings → Embedding; Intel only pauses/resumes. See
// backend/backend/services/embed_worker.py:snapshot.
export interface EmbedStatus {
  status: string;
  paused: boolean;
  circuit_open: boolean;
  model: string | null;
  processed: number;
  failures: number;
  consec_loop_failures: number;
  embedded: number;
  eligible: number;
  queue_size: number;
}

// GET /api/embed/progress — coverage of the embeddable corpus.
export interface EmbedProgress {
  embedded: number;
  eligible: number;
  queue_size: number;
  percent: number;
}

// Prompt templates (item 7, D3). Built-ins (builtin=1) are hideable, not
// editable/deletable. See backend/backend/db/prompt_templates.py.
export interface PromptTemplate {
  id: number;
  name: string;
  analysis_type: string;
  body: string;
  builtin: number;
  hidden: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface CreatePromptTemplateBody {
  name: string;
  analysis_type: string;
  body: string;
}

export interface UpdatePromptTemplateBody {
  name?: string | null;
  analysis_type?: string | null;
  body?: string | null;
  hidden?: boolean | null;
}

// Cluster analyses (item 7, D1) — keyed by a membership fingerprint the server
// derives from resource_ids. See backend/backend/db/llm.py cluster helpers.
export interface ClusterAnalysisRow {
  id: number;
  fingerprint: string;
  label: string | null;
  analysis_type: string;
  model: string | null;
  result: string | null;
  question: string | null;
  prompt_id: number | null;
  priority: number;
  status: AnalysisStatus | null;
  job_id: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CreateClusterAnalysisBody {
  resource_ids: number[];
  // Cluster analyses are multi-page synthesis types (e.g. "Cluster Q&A",
  // "Cluster Summary") that live outside the single-page `AnalysisType` union,
  // so this is a plain string like `CreateCollectionAnalysisBody`.
  analysis_type: string;
  model?: string | null;
  question?: string | null;
  label?: string | null;
  prompt_id?: number | null;
  priority?: number;
}

// Collection synthesis rows — collection-scoped multi-page analyses.
// See backend/backend/db/llm.py collection helpers.
export interface CollectionAnalysisRow {
  id: number;
  collection_id: number;
  analysis_type: string;
  model: string | null;
  result: string | null;
  status: AnalysisStatus | null;
  job_id: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CreateCollectionAnalysisBody {
  analysis_type: string;
  model?: string | null;
}

// Auto-analysis rules (item 7, D4) — the single typed home for auto-analysis.
// trigger_kind 'crawl' fires on every newly crawled page; 'collection_add'
// fires when a page joins the collection in target_filter.
export type AutoRuleTrigger = 'crawl' | 'collection_add';

export interface AutoRule {
  id: number;
  trigger_kind: AutoRuleTrigger;
  analysis_type: string;
  model: string | null;
  prompt_id: number | null;
  target_filter: Record<string, unknown> | null;
  enabled: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface CreateAutoRuleBody {
  trigger_kind: AutoRuleTrigger;
  analysis_type: string;
  model?: string | null;
  prompt_id?: number | null;
  target_filter?: Record<string, unknown> | null;
  enabled?: boolean;
}

export interface UpdateAutoRuleBody {
  analysis_type?: string | null;
  model?: string | null;
  prompt_id?: number | null;
  target_filter?: Record<string, unknown> | null;
  enabled?: boolean | null;
}

// Header-fingerprint cluster + members — see backend/backend/db/fingerprints.py.
export interface FingerprintCluster {
  key: string;
  value: string;
  sites: number;
  idf: number;
}

export interface FingerprintMember {
  id: number;
  url: string;
  title: string | null;
  category: string | null;
  risk_score: string | null;
}

// POST /api/nodes/lookup per-URL result — canonical resource state, or
// 'invalid' when the URL fails egress validation (see routes/nodes.py).
export type NodeLookupState = ResourceState | 'invalid';

export interface NodeLookupRow {
  state: NodeLookupState;
  id?: number;
  last_seen?: string | null;
  reason?: string;
}

export interface CrawlStatus {
  running: boolean;
  crawl_id: number | null;
  active_row: CrawlActiveRow | null;
}

export interface CrawlHistoryRow {
  id: number;
  seed_url: string;
  status: JobStatus;
  mode: string;
  collection_id: number | null;
  pages_crawled: number;
  pages_failed: number;
  pages_queued: number;
  pages_skipped: number;
  max_depth: number | null;
  started_at: string | null;
  completed_at: string | null;
  paused_at: string | null;
  error: string | null;
}

// Flag lifecycle — see backend/backend/db/flags.py. `pending` is set by the
// watchlist auto-flagger; `flagged`/`investigating` are analyst states;
// `done`/`dismissed` are resolved (audit-only, no UI surfaces them yet).
export type FlagStatus =
  | 'pending'
  | 'flagged'
  | 'investigating'
  | 'done'
  | 'dismissed';

// Provenance — who raised the flag, independent of its lifecycle status.
export type FlagSource = 'watchlist' | 'analyst';

export interface FlagRow {
  id: number;
  node_id: number;
  status: FlagStatus;
  source: FlagSource;
  priority: number;
  note: string | null;
}

// GET /api/flags list rows — backend joins node url + title for the
// Flags sub-tab. POST/PATCH return the bare FlagRow above.
export interface FlagListRow extends FlagRow {
  url: string;
  title: string | null;
}

// GET /api/domains row — see backend/backend/db/domains.py::list_domains.
export interface DomainRow {
  host: string;
  alias: string | null;
  last_seen: string | null;
  page_count: number;
  fail_count: number;
  flag_count: number;
}

// GET /api/domains/:host — full profile for the right pane Domain tab.
export interface DomainProfile {
  host: string;
  alias: string | null;
  last_seen: string | null;
  page_count: number;
  flag_count: number;
  entity_count: number;
  // Most recent HTTP status from any monitor scoped to this host, or null
  // when no monitor exists.
  last_status: number | null;
  activity: DomainActivityPoint[];
  entity_types: DomainEntityTypeCount[];
  // Labels attached to this domain (item 11), ids only — resolved via the
  // catalog store.
  label_ids: number[];
}

export interface DomainActivityPoint {
  date: string;
  count: number;
}

export interface DomainEntityTypeCount {
  type: string;
  count: number;
}

// GET /api/domains/:host/pages row — capped at 200.
export interface DomainPage {
  id: number;
  url: string;
  title: string | null;
  status_code: number | null;
}

// GET /api/domains/:host/entities row — distinct (type, value) for crawled
// pages on that host.
export interface DomainEntity {
  type: string;
  value: string;
}

// Domain snapshot comparison (Phase 5) — GET /api/domains/:host/compare.
// Compares each page's version current "as of" two crawl dates. `pages`
// lists only the changed rows (identical pages are counted, not listed); a
// drifted row carries both version ids to deep-link the page diff. See
// backend/backend/db/domains.py::compare_snapshots.
export type DomainCompareStatus = 'added' | 'removed' | 'drifted';

export interface DomainComparePage {
  resource_id: number;
  url: string;
  status: DomainCompareStatus;
  a_version_id: number | null;
  b_version_id: number | null;
  http_status: number | null;
}

export interface DomainComparison {
  a: string;
  b: string;
  added: number;
  removed: number;
  drifted: number;
  identical: number;
  pages: DomainComparePage[];
}

// Per-node analysis types — backend keys from backend/backend/prompts.py.
// The Queue Analysis modal shows a friendlier label for 'Entities (LLM)'.
export type AnalysisType =
  | 'Summary'
  | 'Risk Score'
  | 'Entities (LLM)'
  | 'Category'
  | 'Domain Label'
  | 'Q&A';

// ---------------- Request bodies ----------------

export interface CreateProjectBody {
  name: string;
  path: string;
}

export interface CreateSeedBody {
  url: string;
  label?: string | null;
}

export interface CreateScheduleBody {
  url: string;
  interval_hours: number;
  mode: string;
  label?: string | null;
  collection_id?: number | null;
  active?: boolean;
}

export interface PatchScheduleBody {
  interval_hours?: number | null;
  mode?: string | null;
  label?: string | null;
  collection_id?: number | null;
  active?: boolean | null;
}

export interface AddWatchlistTermBody {
  term: string;
}

export interface CreateNodeBody {
  url: string;
}

export interface LookupNodesBody {
  urls: string[];
}

export interface CreateCollectionBody {
  name: string;
}

export interface CreateEdgeBody {
  from_id: number;
  to_id: number;
  label?: string | null;
  anchor_text?: string | null;
}

export interface CreateMonitorBody {
  url: string;
  label?: string | null;
  interval_hours: number;
  alert_on_change?: boolean;
  alert_on_restore?: boolean;
  downtime_threshold_hours?: number;
}

// PATCH /api/monitors/:id — every field optional, omitted = "no change".
export interface UpdateMonitorBody {
  enabled?: boolean;
  label?: string | null;
  interval_hours?: number;
  alert_on_change?: boolean;
  alert_on_restore?: boolean;
  downtime_threshold_hours?: number;
}

export interface CreateAnalysisBody {
  node_id: number;
  analysis_type: AnalysisType;
  model?: string | null;
  priority?: number;
  question?: string | null;
}

export interface CreateAnalysesBatchBody {
  node_ids: number[];
  analysis_type: AnalysisType;
  model?: string | null;
  priority?: number;
  question?: string | null;
  skip_existing?: boolean;
}

export interface CreateFlagBody {
  node_id: number;
  status?: FlagStatus;
  priority?: number;
  note?: string | null;
}

// PATCH /api/flags/:id — every field optional, omitted = "no change".
export interface UpdateFlagBody {
  status?: FlagStatus;
  priority?: number;
  note?: string | null;
}

