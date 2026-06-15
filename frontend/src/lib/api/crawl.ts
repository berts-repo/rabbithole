// Crawl routes plus the seeds + schedules that feed them, and the SSE
// channel paths crawl consumers subscribe to.

import { apiFetch, qs, BASE } from './core';
import type {
  Seed,
  Schedule,
  CrawlStatus,
  CrawlHistoryRow,
  CreateSeedBody,
  CreateScheduleBody,
  PatchScheduleBody,
} from './types';

// ---------------- Seeds ----------------

export const listSeeds = () => apiFetch<{ seeds: Seed[] }>('/seeds');

export const createSeed = (body: CreateSeedBody) =>
  apiFetch<{ ok: true; url: string; added: boolean }>('/seeds', {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const deleteSeed = (url: string) =>
  apiFetch<{ ok: true }>(`/seeds${qs({ url })}`, { method: 'DELETE' });

export const patchSeed = (url: string, body: { label: string | null }) =>
  apiFetch<{ ok: true; url: string; label: string | null }>(
    `/seeds${qs({ url })}`,
    { method: 'PATCH', body: JSON.stringify(body) },
  );

// ---------------- Schedules ----------------

export const listSchedules = () => apiFetch<{ schedules: Schedule[] }>('/schedules');

export const createSchedule = (body: CreateScheduleBody) =>
  apiFetch<{ ok: true; url: string }>('/schedules', {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const patchSchedule = (url: string, body: PatchScheduleBody) =>
  apiFetch<{ ok: true }>(`/schedules${qs({ url })}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });

export const deleteSchedule = (url: string) =>
  apiFetch<{ ok: true }>(`/schedules${qs({ url })}`, { method: 'DELETE' });

// ---------------- Crawl ----------------

export const stopCrawl = (crawl_id?: number) =>
  apiFetch<{ ok: true; stopped?: number; reaped?: number }>('/crawl/stop', {
    method: 'POST',
    body: JSON.stringify({ crawl_id: crawl_id ?? null }),
  });

export const getCrawlStatus = () => apiFetch<CrawlStatus>('/crawl/status');

export const getCrawlHistory = (limit = 50) =>
  apiFetch<{ crawls: CrawlHistoryRow[] }>(`/crawl/history${qs({ limit })}`);

// SSE paths — consumers pass these to sse.subscribe(), not apiFetch.
export const CRAWL_EVENTS_PATH = `${BASE}/crawl/events`;
export const CRAWL_LOG_PATH = `${BASE}/crawl/log`;
// Control-plane channel. NOT routed through sse.svelte.ts — the
// kill-switch poller opens its own EventSource so the recovery signal
// survives sse.pauseAll() when the switch trips.
export const KILL_SWITCH_EVENTS_PATH = `${BASE}/kill_switch/events`;
