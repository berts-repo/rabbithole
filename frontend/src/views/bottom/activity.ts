// Pure helpers for the bottom-pane Activity view (the unified `jobs` table).
//
// View-free + runes-free so it unit-tests under the node-env vitest config,
// mirroring how liveCrawl.ts backs the LiveCrawlTab/crawlLog store. The
// reactive store lives in lib/stores/jobs.svelte.ts; ActivityTab.svelte (the
// component pair) lands in Task 5 and will grow this module with row-shaping.

import type { Job, JobKind, JobStatus, JobTargetType } from '$lib/api';

// The decoded `jobs.changed` SSE pointer. Workers publish at least these
// three fields (some add `source`/`url`); consumers rely only on the trio.
export interface JobChange {
  job_id: number;
  kind: JobKind;
  status: JobStatus;
}

interface ChangeEnvelope {
  channel?: string;
  job_id?: unknown;
  kind?: unknown;
  status?: unknown;
}

/**
 * Parse one raw SSE `data` payload into a JobChange, or null if it is not a
 * well-formed `jobs.changed` envelope (mirrors parseLogMessage for the
 * crawl-log store).
 */
export function parseJobsChange(raw: string): JobChange | null {
  let env: ChangeEnvelope;
  try {
    env = JSON.parse(raw);
  } catch {
    return null;
  }
  if (env.channel !== 'jobs.changed') return null;
  if (typeof env.job_id !== 'number') return null;
  if (typeof env.kind !== 'string' || typeof env.status !== 'string') return null;
  return {
    job_id: env.job_id,
    kind: env.kind as JobKind,
    status: env.status as JobStatus,
  };
}

// --- Row shaping (ActivityTab) ---------------------------------------------
//
// ActivityTab renders one row per `jobs` row. These helpers stay here (pure,
// runes-free) so the filter/sort/group/gate logic is unit-tested under the
// node-env vitest config; the component only wires them to reactive state and
// owns the target-label resolution (which needs graphStore.payload).

// The display row the Activity tab renders (spec §Row Shape). `target.label`
// is resolved component-side from the graph payload; everything else is a
// direct projection of the Job.
export interface ActivityRow {
  id: string; // `job:${job.id}`
  kind: JobKind;
  target: { type: JobTargetType; label: string };
  status: JobStatus;
  startedAt?: string;
  finishedAt?: string;
  progress?: { current: number; total: number };
  error?: string;
  // True when a probe job detected a content change vs the prior probe.
  contentChanged?: boolean;
}

// --- Action gating — mirrors backend/backend/routes/jobs.py transitions ----
// cancel: any non-terminal row; retry: only terminal; pause: only pending;
// resume: only paused. Keep these in lock-step with the route guards so the
// UI never offers a 409-bound action.
const TERMINAL_STATUSES: readonly JobStatus[] = ['done', 'failed', 'cancelled'];

export function isTerminal(status: JobStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}
export function canCancel(status: JobStatus): boolean {
  return !isTerminal(status);
}
export function canRetry(status: JobStatus): boolean {
  return isTerminal(status);
}
export function canPause(status: JobStatus): boolean {
  return status === 'pending';
}
export function canResume(status: JobStatus): boolean {
  return status === 'paused';
}

// Batch intake: a staged (pending) batch can be Run (spawn its crawl
// children) — backend POST /api/jobs/:id/run is batch-only + pending-only.
// Discard is the ordinary cancel path (pending → cancellable).
export function canRunBatch(job: Job): boolean {
  return job.kind === 'batch' && job.status === 'pending';
}

// A row opens its target in the right pane only when it points at a real
// resource node: a url target with a resolved id. Batches (multi-URL, no
// single node) and url rows whose resource doesn't exist yet (target_id 0)
// are not clickable.
export function canOpenTarget(job: Job): boolean {
  return (
    job.kind !== 'batch' && job.target_type === 'url' && job.target_id > 0
  );
}

// A batch row labels by its staged URL count rather than a (meaningless)
// `{type} #{id}`; reads `payload.count`, falling back to the URL list length.
export function batchUrlCount(job: Job): number | null {
  const payload = job.payload;
  if (!payload) return null;
  const count = finiteNum(payload.count);
  if (count !== null) return count;
  return Array.isArray(payload.urls) ? payload.urls.length : null;
}

// --- Kind filter -----------------------------------------------------------
export type KindFilterValue = 'all' | JobKind;

export const KIND_FILTER_OPTIONS: {
  value: KindFilterValue;
  label: string;
}[] = [
  { value: 'all', label: 'All kinds' },
  { value: 'crawl', label: 'Crawls' },
  { value: 'analysis', label: 'Analyses' },
  { value: 'probe', label: 'Probes' },
  { value: 'schedule', label: 'Schedules' },
  { value: 'batch', label: 'Batches' },
  { value: 'live-crawl', label: 'Live Crawl' },
];

export function matchesKind(job: Job, value: KindFilterValue): boolean {
  return value === 'all' || job.kind === value;
}

export function filterByKind(jobs: readonly Job[], value: KindFilterValue): Job[] {
  return jobs.filter((j) => matchesKind(j, value));
}

// --- Recency sort ----------------------------------------------------------
// Newest activity first: a finished job sorts on when it finished, an active
// one on when it started, an untouched pending one on when it was created.
// ISO-8601 strings compare lexicographically, so a plain string compare is a
// correct chronological order; null timestamps sort last.
export function recencyKey(job: Job): string {
  return job.finished_at ?? job.started_at ?? job.created_at ?? '';
}

export function sortJobsByRecency(jobs: readonly Job[]): Job[] {
  return [...jobs].sort((a, b) => recencyKey(b).localeCompare(recencyKey(a)));
}

// --- Progress extraction ---------------------------------------------------
// `jobs.payload`/`result` are kind-specific JSON. We recognise two shapes:
// an explicit `{current,total}` and the crawl runner's
// `{pages_crawled,pages_queued}` (current = crawled, total = crawled+queued).
// `result` wins over `payload` (a finished job's result is authoritative).
function finiteNum(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

export function extractProgress(
  job: Job,
): { current: number; total: number } | undefined {
  for (const src of [job.result, job.payload]) {
    if (!src) continue;
    const current = finiteNum(src.current);
    const total = finiteNum(src.total);
    if (current !== null && total !== null && total > 0) {
      return { current, total };
    }
    const crawled = finiteNum(src.pages_crawled);
    const queued = finiteNum(src.pages_queued);
    if (crawled !== null && queued !== null) {
      const sum = crawled + queued;
      if (sum > 0) return { current: crawled, total: sum };
    }
  }
  return undefined;
}

// A probe job's payload carries `content_changed` (true/false/null). Surface
// the positive case so an Activity probe row can flag meaningful drift.
export function probeContentChanged(job: Job): boolean {
  return job.kind === 'probe' && job.payload?.content_changed === true;
}

// --- Job → ActivityRow -----------------------------------------------------
export function toActivityRow(job: Job, label: string): ActivityRow {
  return {
    id: `job:${job.id}`,
    kind: job.kind,
    target: { type: job.target_type, label },
    status: job.status,
    startedAt: job.started_at ?? undefined,
    finishedAt: job.finished_at ?? undefined,
    progress: extractProgress(job),
    error: job.error ?? undefined,
    contentChanged: probeContentChanged(job) || undefined,
  };
}

// --- Grouping (spec §Behaviour: group by status or target) -----------------
export type GroupMode = 'none' | 'status' | 'target';

export interface JobGroup {
  key: string;
  label: string;
  jobs: Job[];
}

// Fixed display order so the status groups read active-first, terminal-last.
const STATUS_GROUP_ORDER: readonly JobStatus[] = [
  'running',
  'pending',
  'paused',
  'failed',
  'done',
  'cancelled',
];

function groupByStatus(jobs: readonly Job[]): JobGroup[] {
  const buckets = new Map<JobStatus, Job[]>();
  for (const j of jobs) {
    const bucket = buckets.get(j.status);
    if (bucket) bucket.push(j);
    else buckets.set(j.status, [j]);
  }
  return STATUS_GROUP_ORDER.filter((s) => buckets.has(s)).map((s) => ({
    key: s,
    label: s,
    jobs: buckets.get(s) as Job[],
  }));
}

function groupByTarget(
  jobs: readonly Job[],
  labelFor: (job: Job) => string,
): JobGroup[] {
  const order: string[] = [];
  const buckets = new Map<string, Job[]>();
  for (const j of jobs) {
    const key = `${j.target_type}:${j.target_id}`;
    const bucket = buckets.get(key);
    if (bucket) bucket.push(j);
    else {
      buckets.set(key, [j]);
      order.push(key);
    }
  }
  return order.map((key) => {
    const groupJobs = buckets.get(key) as Job[];
    return { key, label: labelFor(groupJobs[0]), jobs: groupJobs };
  });
}

// Group an already-filtered, already-recency-sorted job list. `none` returns a
// single anonymous group so the component can render groups uniformly.
export function groupJobs(
  jobs: readonly Job[],
  mode: GroupMode,
  labelFor: (job: Job) => string,
): JobGroup[] {
  if (mode === 'status') return groupByStatus(jobs);
  if (mode === 'target') return groupByTarget(jobs, labelFor);
  return jobs.length ? [{ key: 'all', label: '', jobs: [...jobs] }] : [];
}

// --- Timestamp formatting --------------------------------------------------
// HH:MM:SS local time for the row's most recent timestamp; '—' when the job
// has no timestamp yet (a freshly-created pending row).
export function formatJobTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}
