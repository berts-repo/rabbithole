// Job-history retention status + manual run. The retention window itself is a
// normal setting (retention.jobs_days) read/written through settings.ts; these
// routes report how many job records are currently eligible and run the purge.

import { apiFetch } from './core';

export interface RetentionStatus {
  jobs_days: number;
  eligible_jobs: number;
}

export interface RetentionRunResult {
  jobs_days: number;
  deleted_jobs: number;
}

export const getRetentionStatus = () =>
  apiFetch<RetentionStatus>('/retention/status');

export const runRetention = () =>
  apiFetch<RetentionRunResult>('/retention/run', { method: 'POST' });
