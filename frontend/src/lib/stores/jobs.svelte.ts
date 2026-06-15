// SSE-backed view of the unified `jobs` table for the Activity tab.
//
// One subscription to /api/jobs/stream per page lifetime. The stream's
// `jobs.changed` envelope only carries a pointer — `{job_id, kind, status}`,
// not the full row (timestamps/result land server-side) — so rather than
// patch rows from partial data the store treats the list endpoint as the
// source of truth: every change event triggers a (coalesced) reload of the
// authoritative list + per-status counts. Job changes are low-frequency
// relative to crawl-log lines, so a refetch per event is cheap and keeps the
// counts (which span ALL rows, not just the fetched page) exact.
//
// Subscription is ref-counted: the first subscriber loads the list and opens
// the EventSource (via $lib/sse manager), subsequent subscribers reuse it,
// and the last unsubscribe tears it down. The store stays view-free so the
// parse helper and wiring are unit-testable.

import { sse } from '$lib/sse.svelte';
import { JOBS_STREAM_PATH, listJobs } from '$lib/api';
import type { Job, JobStatus } from '$lib/api';
import { parseJobsChange } from '../../views/bottom/activity';

interface JobsState {
  jobs: Job[];
  counts: Partial<Record<JobStatus, number>>;
  loaded: boolean;
  loading: boolean;
  error: string | null;
  unsub: (() => void) | null;
  refCount: number;
}

const state = $state<JobsState>({
  jobs: [],
  counts: {},
  loaded: false,
  loading: false,
  error: null,
  unsub: null,
  refCount: 0,
});

// Set when a change event lands mid-reload so we run exactly one more pass
// afterwards — collapses a burst of events into a single trailing fetch.
let reloadPending = false;

async function reload(): Promise<void> {
  if (state.loading) {
    reloadPending = true;
    return;
  }
  state.loading = true;
  try {
    const { jobs, counts } = await listJobs();
    state.jobs = jobs;
    state.counts = counts;
    state.loaded = true;
    state.error = null;
  } catch (e) {
    state.error = e instanceof Error ? e.message : String(e);
  } finally {
    state.loading = false;
    if (reloadPending) {
      reloadPending = false;
      void reload();
    }
  }
}

function onMessage(e: MessageEvent): void {
  if (parseJobsChange(e.data) === null) return;
  void reload();
}

export const jobsStore = {
  get jobs(): readonly Job[] {
    return state.jobs;
  },
  get counts(): Readonly<Partial<Record<JobStatus, number>>> {
    return state.counts;
  },
  get loaded(): boolean {
    return state.loaded;
  },
  get loading(): boolean {
    return state.loading;
  },
  get error(): string | null {
    return state.error;
  },
  get subscribed(): boolean {
    return state.unsub !== null;
  },

  /**
   * Open (or share) the /api/jobs/stream subscription. The first subscriber
   * kicks off the initial list load and opens the EventSource; the returned
   * callback MUST be invoked on teardown — the last call closes the stream.
   * The list survives unsubscribe so a tab switch away and back is instant.
   */
  subscribe(): () => void {
    state.refCount += 1;
    if (state.unsub === null) {
      void reload();
      state.unsub = sse.subscribe(JOBS_STREAM_PATH, { onMessage });
    }
    let released = false;
    return () => {
      if (released) return;
      released = true;
      state.refCount -= 1;
      if (state.refCount <= 0) {
        state.refCount = 0;
        state.unsub?.();
        state.unsub = null;
      }
    };
  },

  /** Force an authoritative reload — call after a row action (cancel/retry/
   *  pause/resume) so the list reflects the transition without waiting for
   *  the SSE round-trip. */
  refresh(): Promise<void> {
    return reload();
  },

  /** Test helper. */
  _reset(): void {
    state.unsub?.();
    state.jobs = [];
    state.counts = {};
    state.loaded = false;
    state.loading = false;
    state.error = null;
    state.unsub = null;
    state.refCount = 0;
    reloadPending = false;
  },
};
