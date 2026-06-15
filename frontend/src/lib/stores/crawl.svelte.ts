// Active crawl status. Two sources of truth that the F3 sub-tab needs:
//   * SSE `crawl.status` envelopes — give us lifecycle transitions
//     (running → stopped/completed/failed) without polling.
//   * `/api/crawl/status` polling — gives us the live counter trio
//     (pages_crawled / failed / queued) which the SSE channel does not
//     currently emit. Poller runs only while a crawl is active.
//
// Channel envelopes from /api/crawl/events carry a `channel` field
// (set by event_bus.publish). Anything that isn't `crawl.status` is
// ignored here — other consumers handle their own channels.
//
// TODO(B8): if `crawl.status` ever starts emitting the counters, drop
// `pollers/crawlStatus.svelte.ts` and read both from SSE.

import { sse } from '$lib/sse.svelte';
import { CRAWL_EVENTS_PATH, type CrawlActiveRow } from '$lib/api';

type LifecycleStatus =
  | 'running'
  | 'paused'
  | 'stopped'
  | 'completed'
  | 'failed';

interface CrawlState {
  /** Latest poll snapshot. Always reflects the DB row truth. */
  polledActiveRow: CrawlActiveRow | null;
  /** Latest lifecycle status seen on SSE. Cheaper than waiting for a poll. */
  lifecycleStatus: LifecycleStatus | null;
  unsub: (() => void) | null;
}

const state = $state<CrawlState>({
  polledActiveRow: null,
  lifecycleStatus: null,
  unsub: null,
});

const RUNNING_STATES = new Set<LifecycleStatus>(['running', 'paused']);

export const crawlStore = {
  get polledActiveRow() {
    return state.polledActiveRow;
  },
  get lifecycleStatus() {
    return state.lifecycleStatus;
  },
  /** True if either source thinks a crawl is in flight. The SSE flag
   *  flips first; the poller picks up shortly after for counter data. */
  get running() {
    if (state.lifecycleStatus !== null) {
      return RUNNING_STATES.has(state.lifecycleStatus);
    }
    return state.polledActiveRow !== null;
  },
  get subscribed() {
    return state.unsub !== null;
  },

  setPolledActiveRow(row: CrawlActiveRow | null) {
    state.polledActiveRow = row;
    // Poll authoritative when no SSE has arrived yet — also handles the
    // "page loaded mid-crawl" path so the UI doesn't show a stale gap.
    if (state.lifecycleStatus === null && row !== null) {
      state.lifecycleStatus = row.status as LifecycleStatus;
    }
  },

  subscribe() {
    if (state.unsub) return;
    state.unsub = sse.subscribe(CRAWL_EVENTS_PATH, {
      onMessage: (e) => {
        let envelope: { channel?: string; status?: string };
        try {
          envelope = JSON.parse(e.data);
        } catch {
          return;
        }
        if (envelope.channel !== 'crawl.status') return;
        const status = envelope.status as LifecycleStatus | undefined;
        if (!status) return;
        state.lifecycleStatus = status;
        // Terminal status — drop the poll snapshot so the UI clears.
        if (!RUNNING_STATES.has(status)) {
          state.polledActiveRow = null;
        }
      },
    });
  },

  unsubscribe() {
    state.unsub?.();
    state.unsub = null;
  },

  /** Force a terminal `stopped` state without an SSE `crawl.status` event.
   *  The kill-switch poller calls this on a Tor-loss trip: the backend
   *  tears the crawl down, but `sse.pauseAll()` has already closed
   *  `/api/crawl/events`, so the trailing `crawl.status: stopped` never
   *  arrives. Mirrors the terminal-status branch of the SSE handler. */
  markStopped() {
    state.lifecycleStatus = 'stopped';
    state.polledActiveRow = null;
  },

  /** Test helper. */
  reset() {
    state.polledActiveRow = null;
    state.lifecycleStatus = null;
  },
};
