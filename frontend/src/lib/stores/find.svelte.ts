// Find sub-tab session state: the query, the keyword/semantic mode, and the
// last result set. Module-level so it survives left sub-tab switches (spec:
// "Find state persists") — it is intentionally NOT persisted to settings, only
// for the session.
//
// The store owns the debounce and the actual search call, so every entry point
// (typing, mode switch, a drained "Send to Find") runs through one path and
// reveals the results in the bottom pane consistently.

import {
  keywordSearch,
  semanticSearch,
  EmbedUnavailableError,
  type KeywordResult,
  type SemanticResult,
} from '$lib/api';
import { findPendingStore } from './findPending.svelte';
import { workspaceStore } from './workspace.svelte';

export type FindMode = 'keyword' | 'semantic';

const MIN_QUERY = 2;
const DEBOUNCE_MS = 300;

interface FindState {
  query: string;
  mode: FindMode;
  keywordResults: KeywordResult[];
  semanticResults: SemanticResult[];
  loading: boolean;
  // Distinguishes "searched, found nothing" (show empty state) from "haven't
  // searched yet" (show nothing).
  ran: boolean;
  error: string | null;
  // Semantic-only: embedding worker not ready → spec's dedicated empty state.
  embedUnavailable: boolean;
}

const state = $state<FindState>({
  query: '',
  mode: 'keyword',
  keywordResults: [],
  semanticResults: [],
  loading: false,
  ran: false,
  error: null,
  embedUnavailable: false,
});

let timer: ReturnType<typeof setTimeout> | null = null;
// Monotonic guard so a slow earlier request can't overwrite a newer one.
let runId = 0;

function clearTimer(): void {
  if (timer !== null) {
    clearTimeout(timer);
    timer = null;
  }
}

function resetResults(): void {
  state.keywordResults = [];
  state.semanticResults = [];
  state.ran = false;
  state.error = null;
  state.embedUnavailable = false;
}

async function execute(): Promise<void> {
  const q = state.query.trim();
  if (q.length < MIN_QUERY) return;
  // Running a find surfaces its results in the bottom pane (auto-reveals +
  // focuses the `find` tab via the customizable-strip machinery).
  workspaceStore.setBottom('find');
  const id = ++runId;
  state.loading = true;
  state.error = null;
  state.embedUnavailable = false;
  try {
    if (state.mode === 'keyword') {
      const results = await keywordSearch(q);
      if (id !== runId) return;
      state.keywordResults = results;
    } else {
      const results = await semanticSearch(q);
      if (id !== runId) return;
      state.semanticResults = results;
    }
    state.ran = true;
  } catch (err) {
    if (id !== runId) return;
    if (err instanceof EmbedUnavailableError) {
      state.embedUnavailable = true;
      state.semanticResults = [];
      state.ran = true;
    } else {
      state.error = err instanceof Error ? err.message : String(err);
    }
  } finally {
    if (id === runId) state.loading = false;
  }
}

export const findStore = {
  get query() {
    return state.query;
  },
  get mode() {
    return state.mode;
  },
  get loading() {
    return state.loading;
  },
  get ran() {
    return state.ran;
  },
  get error() {
    return state.error;
  },
  get embedUnavailable() {
    return state.embedUnavailable;
  },
  get keywordResults() {
    return state.keywordResults;
  },
  get semanticResults() {
    return state.semanticResults;
  },

  // Update the query and schedule a debounced search. Below the min length we
  // cancel any in-flight run and clear results (nothing to search).
  setQuery(q: string): void {
    state.query = q;
    clearTimer();
    if (q.trim().length < MIN_QUERY) {
      runId++; // cancel any in-flight request
      state.loading = false;
      resetResults();
      return;
    }
    timer = setTimeout(() => {
      timer = null;
      void execute();
    }, DEBOUNCE_MS);
  },

  // Switch modes: clears results and re-runs immediately if the query is long
  // enough (spec). No-op when already in that mode.
  setMode(mode: FindMode): void {
    if (mode === state.mode) return;
    state.mode = mode;
    clearTimer();
    resetResults();
    if (state.query.trim().length >= MIN_QUERY) void execute();
  },

  // The ✕ clear button: wipe the query and all results.
  clear(): void {
    clearTimer();
    runId++;
    state.query = '';
    state.loading = false;
    resetResults();
  },

  // FindTab mount: drain a "Send to Find" query staged by another surface and
  // run it immediately (an explicit action, not debounced).
  drainPending(): void {
    const q = findPendingStore.consume();
    if (q && q.trim().length >= MIN_QUERY) {
      state.query = q;
      clearTimer();
      void execute();
    } else if (q) {
      state.query = q;
    }
  },
};
