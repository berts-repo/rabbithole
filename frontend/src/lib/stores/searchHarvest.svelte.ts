// Session store for the outbound Search tab (engine harvest).
//
// Owns: the enabled-engine list + per-session source selection, the passive
// toggle, and one optional in-flight SSE stream. Results upsert by URL as
// engine rows arrive, then patch in place when a probe lands. The store is a
// singleton (one Search tab) and outlives the component, so results persist
// across a tab switch; the stream itself is stopped on unmount for privacy —
// no background Tor fan-out once the analyst has navigated away.
//
// Untrusted content: engine anchor text and probe titles/descriptions are
// attacker-controlled onion-page text. They are stored verbatim and rendered
// as auto-escaped text by the view — never via Svelte's raw-HTML directive.

import { sse } from '$lib/sse.svelte';
import {
  getEngineEnabled,
  getSetting,
  harvestSearchPath,
  listEngines,
  putSetting,
  type HarvestEvent,
  type SearchEngine,
} from '$lib/api';
import {
  applyProbe,
  classifyEmpty,
  resultFromUrlEvent,
  type SearchEmptyState,
  type SearchResult,
  type SourceStatus,
} from './searchHarvestModel';

export type {
  SearchEmptyState,
  SearchResult,
  SourceStatus,
} from './searchHarvestModel';
export { sourceBadge } from './searchHarvestModel';

interface HarvestState {
  engines: SearchEngine[];
  // Engine ids selected for the next search (per-session override).
  selectedIds: Set<number>;
  passive: boolean;
  loaded: boolean;
  loadError: string | null;

  query: string;
  searching: boolean;
  // A search has completed at least once this session — gates the
  // before-first-search vs. no-results empty states.
  ran: boolean;

  results: SearchResult[];
  // Per-source status keyed by engine *label* (the SSE events carry label).
  sourceStatus: Record<string, SourceStatus>;
  // The engines actually queried by the in-flight/last search — empty-state
  // classification reads their statuses, not the (mutable) current selection.
  lastSearched: SearchEngine[];
}

const state = $state<HarvestState>({
  engines: [],
  selectedIds: new Set(),
  passive: false,
  loaded: false,
  loadError: null,
  query: '',
  searching: false,
  ran: false,
  results: [],
  sourceStatus: {},
  lastSearched: [],
});

// url → index into state.results, for O(1) upsert/probe-patch. Non-reactive:
// it's pure bookkeeping behind the reactive array.
let resultIndex = new Map<string, number>();
let unsub: (() => void) | null = null;

async function loadEngines(): Promise<void> {
  state.loadError = null;
  try {
    const list = (await listEngines()).engines;
    // Enabled flag is a separate templated setting per engine (mirrors the
    // Settings → Engines tab). Missing/null defaults to enabled.
    const flags = await Promise.all(
      list.map((e) => getEngineEnabled(e.id).catch(() => null)),
    );
    const enabled = list.filter((_, i) => flags[i]?.value !== 'false');
    state.engines = enabled;
    state.selectedIds = new Set(enabled.map((e) => e.id));
    const passive = await getSetting<string>('search.passive_mode').catch(
      () => null,
    );
    state.passive = passive?.value === 'true';
    state.loaded = true;
  } catch (err) {
    state.loadError = err instanceof Error ? err.message : String(err);
  }
}

function reset(): void {
  state.results = [];
  resultIndex = new Map();
  state.sourceStatus = {};
}

function upsertUrl(ev: Extract<HarvestEvent, { type?: undefined }>): void {
  if (resultIndex.has(ev.url)) return; // first source to surface a URL wins
  resultIndex.set(ev.url, state.results.length);
  state.results.push(resultFromUrlEvent(ev));
}

function patchProbe(url: string, title: string | null, description: string | null): void {
  const idx = resultIndex.get(url);
  if (idx === undefined) return;
  state.results[idx] = applyProbe(state.results[idx], title, description);
}

function handle(ev: HarvestEvent): void {
  switch (ev.type) {
    case undefined:
      upsertUrl(ev);
      break;
    case 'probe':
      patchProbe(ev.url, ev.title, ev.description);
      break;
    case 'status':
      state.sourceStatus[ev.engine] = { kind: 'searching' };
      break;
    case 'done':
      state.sourceStatus[ev.engine] = { kind: 'done', count: ev.count };
      break;
    case 'error':
      state.sourceStatus[ev.engine] = { kind: 'error', reason: ev.reason };
      break;
    case 'all_done':
      finish();
      break;
  }
}

function onMessage(e: MessageEvent): void {
  let ev: HarvestEvent;
  try {
    ev = JSON.parse(e.data) as HarvestEvent;
  } catch {
    return;
  }
  handle(ev);
}

// A transport drop mid-search. EventSource would auto-reconnect and silently
// re-run the whole query, so close it and surface the failure on any source
// still marked searching.
function onError(): void {
  if (!state.searching) return;
  for (const e of state.lastSearched) {
    if (state.sourceStatus[e.label]?.kind !== 'done') {
      state.sourceStatus[e.label] = { kind: 'error', reason: 'connection' };
    }
  }
  finish();
}

function finish(): void {
  unsub?.();
  unsub = null;
  state.searching = false;
  state.ran = true;
}

export const searchHarvest = {
  get engines(): readonly SearchEngine[] {
    return state.engines;
  },
  get selectedIds(): ReadonlySet<number> {
    return state.selectedIds;
  },
  get passive(): boolean {
    return state.passive;
  },
  get loaded(): boolean {
    return state.loaded;
  },
  get loadError(): string | null {
    return state.loadError;
  },
  get query(): string {
    return state.query;
  },
  set query(v: string) {
    state.query = v;
  },
  get searching(): boolean {
    return state.searching;
  },
  get results(): readonly SearchResult[] {
    return state.results;
  },
  statusFor(label: string): SourceStatus | undefined {
    return state.sourceStatus[label];
  },

  /** Load engines + passive setting once (idempotent). */
  init(): void {
    if (!state.loaded) void loadEngines();
  },

  toggleEngine(id: number): void {
    const next = new Set(state.selectedIds);
    if (next.has(id)) {
      if (next.size === 1) return; // keep at least one source selected
      next.delete(id);
    } else {
      next.add(id);
    }
    state.selectedIds = next;
  },

  async setPassive(value: boolean): Promise<void> {
    state.passive = value;
    try {
      await putSetting('search.passive_mode', value);
    } catch {
      state.passive = !value; // revert on failure
    }
  },

  start(): void {
    const q = state.query.trim();
    if (!q || state.searching) return;
    const selected = state.engines.filter((e) => state.selectedIds.has(e.id));
    if (selected.length === 0) return;

    this.stop();
    reset();
    state.lastSearched = selected;
    for (const e of selected) {
      state.sourceStatus[e.label] = { kind: 'searching' };
    }
    state.searching = true;
    state.ran = false;
    unsub = sse.subscribe(harvestSearchPath(q, selected.map((e) => e.id)), {
      onMessage,
      onError,
    });
  },

  stop(): void {
    unsub?.();
    unsub = null;
    state.searching = false;
  },

  /** Which empty state (if any) the results pane should show. */
  emptyState(): SearchEmptyState | null {
    return classifyEmpty({
      loaded: state.loaded,
      engineCount: state.engines.length,
      resultCount: state.results.length,
      searching: state.searching,
      ran: state.ran,
      searchedStatuses: state.lastSearched.map(
        (e) => state.sourceStatus[e.label],
      ),
    });
  },

  /** Test/teardown helper — drops any stream and clears state. */
  _reset(): void {
    this.stop();
    reset();
    state.engines = [];
    state.selectedIds = new Set();
    state.loaded = false;
    state.query = '';
    state.ran = false;
    state.lastSearched = [];
  },
};
