// Shared staging surface for the Crawl sub-tab's batch-confirm strip.
//
// Multi-row intake surfaces (Bulk Import paste, "send all uncrawled in this
// collection", graph multi-select, right-pane cluster workspace) stage URLs
// here rather than enqueueing silently. The strip in the Crawl sub-tab reads
// `staged` and exposes the analyst-side mode / collection / depth choice
// before rows enter the durable queue.
//
// Single-URL intake surfaces call `loadIntoControls(url)` which forwards to
// the existing seed-input lift wired up by CrawlSidebar. Keeping both paths
// behind one store gives every intake site a single import target — and
// matches the spec's "single verb" promise (`source-spec.md` Option B,
// 2026-05-26).
//
// State is captured at stage time: the strip works off a snapshot of
// CrawlControls' values so the analyst can still tweak the controls above
// without retroactively mutating the staged batch.

import type { CrawlQueueMode, CrawlQueueSource } from '$lib/api';
import { toastStore } from './toast.svelte';

export interface BatchDefaults {
  mode: CrawlQueueMode;
  stayOnDomain: boolean;
  // `null` is the explicit "unlimited" opt-in — matches the queue API.
  maxDepth: number | null;
  collectionId: number | null;
  // For the "+ New collection" path: send the name; the backend resolves
  // (or creates) on claim.
  collectionNamePending: string | null;
}

export interface StagedBatch {
  source: CrawlQueueSource;
  // Short human label rendered in the strip's "Batch from {…}" header.
  sourceLabel: string;
  urls: string[];
  defaults: BatchDefaults;
}

interface State {
  staged: StagedBatch | null;
  // Buffers a single-URL load when no CrawlSidebar instance is currently
  // mounted (e.g. the analyst triggered "Send to Crawl" from the graph
  // while the Crawl sub-tab was hidden). CrawlSidebar consumes this on
  // mount so the URL still lands in the seed input.
  pendingLoad: string | null;
}

const state = $state<State>({ staged: null, pendingLoad: null });

type ControlsSnapshotGetter = () => BatchDefaults;
type LoadIntoControlsHandler = (url: string) => void;

let controlsSnapshot: ControlsSnapshotGetter | null = null;
let loadHandler: LoadIntoControlsHandler | null = null;

// Used only when no CrawlControls instance has registered a snapshot
// getter (e.g. tests, or staging before the Crawl tab has ever mounted).
// Mirrors the initial values in CrawlControls.svelte.
const FALLBACK_DEFAULTS: BatchDefaults = {
  mode: 'Cross-site',
  stayOnDomain: false,
  maxDepth: 3,
  collectionId: null,
  collectionNamePending: null,
};

function dedupeUrls(urls: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of urls) {
    const trimmed = raw.trim();
    if (!trimmed) continue;
    if (seen.has(trimmed)) continue;
    seen.add(trimmed);
    out.push(trimmed);
  }
  return out;
}

export const batchConfirmStore = {
  get staged() {
    return state.staged;
  },

  // CrawlControls registers a getter on mount so `stage()` can snapshot the
  // analyst's current mode / collection / depth choice. Passing `null`
  // unregisters.
  setControlsSnapshot(getter: ControlsSnapshotGetter | null): void {
    controlsSnapshot = getter;
  },

  // CrawlSidebar (or any future host) registers a single-URL handler.
  // `loadIntoControls(url)` calls into it; if nothing is wired, the call
  // is a no-op so callers never have to null-check.
  setLoadIntoControls(handler: LoadIntoControlsHandler | null): void {
    loadHandler = handler;
  },

  stage(batch: {
    source: CrawlQueueSource;
    sourceLabel: string;
    urls: string[];
    // Pin specific defaults on top of the CrawlControls snapshot. The
    // Collection sub-tab's "Send to Crawl (all uncrawled)" uses this to
    // force collectionId to the active collection so the strip opens
    // with the right target pre-selected.
    defaultsOverride?: Partial<BatchDefaults>;
  }): void {
    const cleaned = dedupeUrls(batch.urls);
    if (cleaned.length === 0) return;
    const prior = state.staged;
    if (prior) {
      toastStore.show(
        `Replaced previous batch — ${prior.urls.length} URLs`,
        'info',
      );
    }
    const snapshot = controlsSnapshot
      ? controlsSnapshot()
      : { ...FALLBACK_DEFAULTS };
    const defaults = batch.defaultsOverride
      ? { ...snapshot, ...batch.defaultsOverride }
      : snapshot;
    state.staged = {
      source: batch.source,
      sourceLabel: batch.sourceLabel,
      urls: cleaned,
      defaults,
    };
  },

  // Discard the current batch without enqueueing. Bound to the strip's ✕.
  discard(): void {
    state.staged = null;
  },

  // Called by the strip after `Queue N` succeeds. Functionally identical
  // to `discard` today but keeping the verbs distinct documents intent at
  // the call site.
  clear(): void {
    state.staged = null;
  },

  loadIntoControls(url: string): void {
    if (loadHandler) {
      loadHandler(url);
    } else {
      state.pendingLoad = url;
    }
  },

  // Called by CrawlSidebar on mount after it registers a load handler.
  // Returns the buffered URL (if any) and clears it.
  consumePendingLoad(): string | null {
    const url = state.pendingLoad;
    state.pendingLoad = null;
    return url;
  },
};
