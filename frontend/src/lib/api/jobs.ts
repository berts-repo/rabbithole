// Unified work/activity HTTP surface — the `jobs` table. One function per
// route on backend/backend/routes/jobs.py, kept symmetric with the other
// $lib/api modules so call sites import from one specifier.
//
// Types (Job/JobList/JobKind/JobStatus/JobTargetType) live in ./types and
// flow through the $lib/api barrel; this module only adds the route fns and
// the SSE path constant.

import { apiFetch, qs, BASE } from './core';
import type {
  Job,
  JobList,
  JobKind,
  JobStatus,
  JobTargetType,
  RunBatchResult,
  StageBatchBody,
  StageBatchResult,
} from './types';

// --- Calls ------------------------------------------------------------------

export const listJobs = (params?: {
  kind?: JobKind;
  status?: JobStatus;
  target_type?: JobTargetType;
  since?: string;
  limit?: number;
}) => apiFetch<JobList>(`/jobs${qs(params ?? {})}`);

export const getJob = (id: number) => apiFetch<{ job: Job }>(`/jobs/${id}`);

// A running crawl is stopped through the queue runner, which writes the
// terminal status itself — that path returns `cancelling`; everything else
// transitions directly and returns the final `cancelled` status.
export const cancelJob = (id: number) =>
  apiFetch<
    | { ok: true; job_id: number; cancelling: true }
    | { ok: true; job_id: number; status: 'cancelled' }
  >(`/jobs/${id}/cancel`, { method: 'POST' });

// Re-enqueues a terminal job as a fresh `pending` row, returning the new job.
export const retryJob = (id: number) =>
  apiFetch<{ job: Job }>(`/jobs/${id}/retry`, { method: 'POST' });

export const pauseJob = (id: number) =>
  apiFetch<{ job: Job }>(`/jobs/${id}/pause`, { method: 'POST' });

export const resumeJob = (id: number) =>
  apiFetch<{ job: Job }>(`/jobs/${id}/resume`, { method: 'POST' });

// --- Batch intake -----------------------------------------------------------

// Stage a batch: one pending kind='batch' job holding the URL list. No crawl
// children are created until runBatch.
export const stageBatch = (body: StageBatchBody) =>
  apiFetch<StageBatchResult>('/jobs/batch', {
    method: 'POST',
    body: JSON.stringify(body),
  });

// Run a staged batch: spawns one kind='crawl' child per staged URL and marks
// the batch done. Batch-only, pending-only (one-shot).
export const runBatch = (id: number) =>
  apiFetch<RunBatchResult>(`/jobs/${id}/run`, { method: 'POST' });

// SSE path — consumers pass this to sse.subscribe(), not apiFetch.
// Emits `jobs.changed` messages with shape `{job_id, kind, status}`.
export const JOBS_STREAM_PATH = `${BASE}/jobs/stream`;
