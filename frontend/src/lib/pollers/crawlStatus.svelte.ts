// 2 s poll of /api/crawl/status — only runs while a crawl is in flight.
// Drives the live counter trio in the F3 status row.
//
// Lifecycle is reactive on crawlStore.running: a $effect in
// CrawlSidebar.svelte starts the poller when running flips true and
// stops it when running flips false. The poller itself is refcount-aware
// so calling start() while already polling is a no-op.

import { getCrawlStatus } from '$lib/api';
import { crawlStore } from '$lib/stores/crawl.svelte';

const POLL_MS = 2_000;

let timer: ReturnType<typeof setInterval> | null = null;
let refs = 0;
let inFlight = false;

async function poll(): Promise<void> {
  if (inFlight) return;
  inFlight = true;
  try {
    const s = await getCrawlStatus();
    crawlStore.setPolledActiveRow(s.active_row);
  } catch {
    // Fetch hiccup — leave the last snapshot in place. The next tick
    // will retry. Surfacing a toast here would spam during transient
    // network blips.
  } finally {
    inFlight = false;
  }
}

export const crawlStatusPoller = {
  start() {
    refs += 1;
    if (timer !== null) return;
    void poll();
    timer = setInterval(() => void poll(), POLL_MS);
  },
  stop() {
    refs = Math.max(0, refs - 1);
    if (refs > 0) return;
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  },
  /** Force a one-shot poll outside the timer cadence — used after Start
   *  to populate the status row before the next 2 s tick. */
  pokeOnce() {
    void poll();
  },
};
