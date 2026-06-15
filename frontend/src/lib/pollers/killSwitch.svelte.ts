// Kill-switch SSE subscriber. The backend publishes three kill_switch.*
// channels on a dedicated control-plane route /api/kill_switch/events
// (see backend/routes/sse.py). We dispatch them into the services
// store FSM:
//
//   kill_switch.engaged → trip (reason=tor_lost)
//   kill_switch.banner  → trip (reason=tor_lost) — enforcement off, but
//                         this is still a real Tor outage; the analyst
//                         needs to see the modal. KillSwitchAlert shows
//                         the softer enforcement-off copy in that case.
//   kill_switch.clear   → cleared_idle (waiting for explicit re-arm)
//
// On engaged/banner we also reconcile crawlStore: a Tor-loss trip ends
// any running crawl, but the trip closes /api/crawl/events before the
// backend's terminal `crawl.status: stopped` lands, so the crawl store
// would otherwise stay stuck on `running`.
//
// This poller deliberately bypasses sse.svelte.ts and owns its own
// EventSource. The shared manager's pauseAll() closes every stream it
// manages when the kill switch trips — and that used to include this
// one, which meant the recovery signal kill_switch.clear was being
// delivered to a closed stream. The modal would hang on "Waiting for
// monitor…" forever and the pill stayed red after Tor recovered. By
// holding our own EventSource, this stream is structurally outside the
// data-plane pause/resume mechanism and cannot be muted by it.
//
// Ref-counted start/stop so the app shell can mount/unmount safely.

import { KILL_SWITCH_EVENTS_PATH } from '$lib/api';
import { servicesStore } from '$lib/stores/services.svelte';
import { crawlStore } from '$lib/stores/crawl.svelte';

let source: EventSource | null = null;
let refs = 0;

function onMessage(e: MessageEvent): void {
  let envelope: { channel?: string };
  try {
    envelope = JSON.parse(e.data);
  } catch {
    return;
  }
  switch (envelope.channel) {
    case 'kill_switch.engaged':
    case 'kill_switch.banner':
      // A Tor-loss trip always ends any running crawl — the crawl loop
      // exits on the shared `engaged` flag in both enforcement modes
      // (warn-only just lets the in-flight request drain instead of
      // aborting it mid-stream). Reconcile the crawl store directly: the
      // trailing `crawl.status: stopped` is lost because tripKillSwitch()
      // → sse.pauseAll() closes /api/crawl/events before it arrives.
      if (crawlStore.running) crawlStore.markStopped();
      servicesStore.tripKillSwitch('tor_lost');
      break;
    case 'kill_switch.clear':
      servicesStore.clearKillSwitch();
      break;
  }
}

export const killSwitchPoller = {
  start(): void {
    refs += 1;
    if (source) return;
    // withCredentials so the crawl_token cookie travels on the SSE
    // handshake — matches sse.svelte.ts:#open().
    source = new EventSource(KILL_SWITCH_EVENTS_PATH, { withCredentials: true });
    source.addEventListener('message', onMessage);
  },
  stop(): void {
    refs = Math.max(0, refs - 1);
    if (refs > 0) return;
    if (source) {
      source.removeEventListener('message', onMessage);
      source.close();
      source = null;
    }
  },
};
