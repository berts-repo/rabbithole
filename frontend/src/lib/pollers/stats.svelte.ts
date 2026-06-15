// 30 s poll for the bottom-pane Flags / Monitors tab count badges. These
// are project-wide totals; the graph tab bar derives its own
// workspace-scoped domain/page counts straight off the payload (see
// graphCounts.deriveScopeCounts), so /api/stats' domain/page columns go
// unused here. No constant pinned in PLAN.md; aligned with the Tor cadence
// so the lifecycle pollers fire on similar wakes.

import { getStats, type Stats } from '$lib/api';

const POLL_MS = 30_000;

interface StatsState {
  data: Stats | null;
  lastPoll: number | null;
  error: string | null;
}

const state = $state<StatsState>({
  data: null,
  lastPoll: null,
  error: null,
});

let timer: ReturnType<typeof setInterval> | null = null;
let refs = 0;
let inFlight = false;

async function poll(): Promise<void> {
  if (inFlight) return;
  inFlight = true;
  try {
    state.data = await getStats();
    state.error = null;
  } catch (e) {
    state.error = e instanceof Error ? e.message : String(e);
  } finally {
    state.lastPoll = Date.now();
    inFlight = false;
  }
}

export const statsPoller = {
  get data() {
    return state.data;
  },
  get error() {
    return state.error;
  },
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
  refresh() {
    void poll();
  },
};
