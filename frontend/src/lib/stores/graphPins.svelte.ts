// Analyst-pinned graph nodes — the set of resource ids kept visible on the
// canvas regardless of the global "Show uncrawled" toggle.
//
// Why this exists: an uncrawled resource is hidden by default (a link-directory
// crawl discovers thousands of them — `graph.show_uncrawled` defaults off so the
// canvas isn't a haystack). But "Add to Graph" on a Search result is a deliberate
// "keep THIS one on the graph" intent. Flipping the global toggle to honour it
// would un-hide every discovered placeholder at once. Pinning instead forces only
// the chosen ids into the rebuild, leaving the rest hidden.
//
// Render seam: `rebuildInto` / `applyDiff` include an uncrawled node when
// `showUncrawled || pinnedIds.has(id)` (see graph/model/applyPayload.ts). The
// canvas rebuilds when this set changes, mirroring the showUncrawled effect.
//
// Persistence: the whole set round-trips through the `graph.pinned_ids` setting
// (a CSV scalar, per-project) so pins survive reload. Mutations replace the Set
// reference so runes consumers re-run.

import { getSetting, putSetting } from '$lib/api';
import { toastStore } from './toast.svelte';

interface PinsState {
  ids: Set<number>;
  loaded: boolean;
}

const state = $state<PinsState>({ ids: new Set(), loaded: false });

function parseCsv(value: unknown): Set<number> {
  const out = new Set<number>();
  if (typeof value === 'string') {
    for (const tok of value.split(',')) {
      const n = parseInt(tok.trim(), 10);
      if (Number.isInteger(n) && n > 0) out.add(n);
    }
  } else if (Array.isArray(value)) {
    for (const v of value) {
      const n = typeof v === 'number' ? v : parseInt(String(v), 10);
      if (Number.isInteger(n) && n > 0) out.add(n);
    }
  }
  return out;
}

async function persist(ids: Set<number>): Promise<void> {
  try {
    await putSetting('graph.pinned_ids', [...ids]);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    toastStore.show(`Pin save failed: ${msg}`, 'warn');
  }
}

export const graphPinsStore = {
  // Returns the live set; reading it in a rune tracks the reference, which
  // every mutation below replaces so dependents re-run.
  get pinned(): ReadonlySet<number> {
    return state.ids;
  },
  get loaded() {
    return state.loaded;
  },
  get size() {
    return state.ids.size;
  },
  has(id: number): boolean {
    return state.ids.has(id);
  },

  /** Load the persisted set. Called from app.svelte after projects.load(). */
  async load(): Promise<void> {
    try {
      const s = await getSetting<string>('graph.pinned_ids');
      state.ids = parseCsv(s.value);
    } catch {
      // Missing key / read failure → empty set; the canvas renders fine.
      state.ids = new Set();
    }
    state.loaded = true;
  },

  /** Pin one id. No-op (no write) if already pinned. */
  pin(id: number): void {
    if (state.ids.has(id)) return;
    const next = new Set(state.ids);
    next.add(id);
    state.ids = next;
    void persist(next);
  },

  /** Pin many ids in one write. No-op if all are already pinned. */
  pinMany(ids: Iterable<number>): void {
    const next = new Set(state.ids);
    let added = false;
    for (const id of ids) {
      if (!next.has(id)) {
        next.add(id);
        added = true;
      }
    }
    if (!added) return;
    state.ids = next;
    void persist(next);
  },

  /** Unpin one id. No-op (no write) if not pinned. */
  unpin(id: number): void {
    if (!state.ids.has(id)) return;
    const next = new Set(state.ids);
    next.delete(id);
    state.ids = next;
    void persist(next);
  },
};
