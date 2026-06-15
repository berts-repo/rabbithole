// 15 s /api/graph poll for the Explore tab. Mirrors torStatus shape:
// ref-counted start/stop, in-flight + pending semaphore. Workspace-scoped:
// the active collection id is read at fetch start and the result is
// dropped if the active workspace changed by the time the response lands
// (a stale Global payload must not bleed into a Collection tab).
//
// Intentionally NOT gated on the kill-switch FSM: /api/graph is a local
// SQLite read with no Tor traffic, so pausing it on a Tor outage would
// only succeed in showing wrong-scope stale data after a workspace
// switch. Crawl + SSE pause-on-trip lives elsewhere; this poll stays alive.

import { getGraph, ApiError } from '$lib/api';
import { graphStore } from '$lib/stores/graph.svelte';
import { workspaceStore } from '$lib/stores/workspace.svelte';

const POLL_MS = 15_000;

let timer: ReturnType<typeof setInterval> | null = null;
let refs = 0;
let inFlight = false;
let pending = false;

async function poll(): Promise<void> {
  if (inFlight) {
    // Coalesce — exactly one follow-up after the current request lands.
    pending = true;
    return;
  }
  inFlight = true;
  graphStore.setLoading(true);
  const requestedFor = workspaceStore.activeWorkspaceId;
  const cid = workspaceStore.activeCollectionId();
  try {
    const payload = await getGraph(cid);
    if (workspaceStore.activeWorkspaceId !== requestedFor) {
      // Stale — user switched tabs mid-flight. Queue another tick so
      // the new scope still gets a fresh payload.
      pending = true;
      return;
    }
    graphStore.applyPayload(payload, requestedFor);
  } catch (err) {
    const msg =
      err instanceof ApiError
        ? `graph fetch ${err.status}`
        : err instanceof Error
          ? err.message
          : 'graph fetch failed';
    graphStore.setError(msg);
  } finally {
    graphStore.setLoading(false);
    inFlight = false;
    if (pending) {
      pending = false;
      void poll();
    }
  }
}

export const graphPoller = {
  start(): void {
    refs += 1;
    if (timer !== null) return;
    void poll();
    timer = setInterval(() => void poll(), POLL_MS);
  },
  stop(): void {
    refs = Math.max(0, refs - 1);
    if (refs > 0) return;
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  },
  // Manual refresh for the toolbar's "Reset" button and the workspace
  // bridge effect — re-runs immediately without resetting the cadence.
  // If a request is already in flight, this queues exactly one follow-up.
  refresh(): Promise<void> {
    return poll();
  },
};
