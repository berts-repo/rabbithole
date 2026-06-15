// 30 s Tor reachability poll. Powers the header Tor pill and the
// `tor.reachable` flag; kill-switch FSM transitions are driven by the
// SSE channel (pollers/killSwitch) and no longer by this poller.
// Refcounted start/stop so multiple mounts don't multiply timers.

import { getTorStatus } from '$lib/api';
import { servicesStore } from '$lib/stores/services.svelte';

const POLL_MS = 30_000;

let timer: ReturnType<typeof setInterval> | null = null;
let refs = 0;
let inFlight = false;

async function poll(): Promise<void> {
  if (inFlight) return;
  inFlight = true;
  try {
    const s = await getTorStatus();
    servicesStore.setTor({ reachable: s.ok, lastPoll: Date.now() });
  } catch {
    // Local API unreachable — flag Tor as unknown rather than stale.
    servicesStore.setTor({ reachable: false, lastPoll: Date.now() });
  } finally {
    inFlight = false;
  }
}

export const torStatusPoller = {
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
};
