// Label visibility filter store (item 11, Phase 3c) — the persisted
// include/exclude sets backing the graph's label filter dimension. Held apart
// from `graphFiltersStore` because it's a distinct dimension (decision: it
// composes with the server-side term-hide, neither rewritten in terms of the
// other) and its values are id lists, not scalars.
//
// Persists each set as a CSV scalar to `graph.label_include` /
// `graph.label_exclude` (the backend `_id_csv_validator` keys), mirroring
// `graph.pinned_ids`. Load is fire-and-forget like the other graph filters;
// the canvas renders on defaults (filter off) until it lands.

import { getSetting, putSetting } from '$lib/api';
import { toastStore } from './toast.svelte';
import {
  cycleLabel,
  isLabelFilterEmpty,
  labelMode,
  passesLabelFilter,
  pruneLabelFilter,
  type LabelFilterMode,
  type LabelFilterState,
} from '$lib/graph/labelFilter';

const state = $state<LabelFilterState & { loaded: boolean }>({
  include: [],
  exclude: [],
  loaded: false,
});

function parseIds(raw: unknown): number[] {
  if (typeof raw !== 'string') return [];
  return raw
    .split(',')
    .map((s) => parseInt(s.trim(), 10))
    .filter((n) => Number.isFinite(n) && n > 0);
}

async function readSetting(key: string): Promise<string | null> {
  try {
    return (await getSetting<string>(key)).value;
  } catch {
    return null;
  }
}

async function writeSetting(key: string, ids: number[]): Promise<void> {
  try {
    await putSetting(key, ids);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    toastStore.show(`Settings save failed (${key}): ${msg}`, 'warn');
  }
}

export const labelFilterStore = {
  get include() {
    return state.include;
  },
  get exclude() {
    return state.exclude;
  },
  get loaded() {
    return state.loaded;
  },
  get active(): boolean {
    return !isLabelFilterEmpty(state);
  },

  // Snapshot for the visibility controller's per-node predicate.
  get snapshot(): LabelFilterState {
    return { include: state.include, exclude: state.exclude };
  },

  modeOf(id: number): LabelFilterMode {
    return labelMode(state, id);
  },

  passes(directIds: readonly number[], domainIds: readonly number[]): boolean {
    return passesLabelFilter(state, directIds, domainIds);
  },

  async load(): Promise<void> {
    const [inc, exc] = await Promise.all([
      readSetting('graph.label_include'),
      readSetting('graph.label_exclude'),
    ]);
    state.include = parseIds(inc);
    state.exclude = parseIds(exc);
    state.loaded = true;
  },

  // Tri-state cycle for one label chip; persists whichever set changed.
  cycle(id: number): void {
    const next = cycleLabel(state, id);
    state.include = next.include;
    state.exclude = next.exclude;
    void writeSetting('graph.label_include', state.include);
    void writeSetting('graph.label_exclude', state.exclude);
  },

  clear(): void {
    if (isLabelFilterEmpty(state)) return;
    state.include = [];
    state.exclude = [];
    void writeSetting('graph.label_include', []);
    void writeSetting('graph.label_exclude', []);
  },

  // Drop ids the catalog no longer knows (after a label delete). Persists only
  // when something actually changed.
  prune(knownIds: ReadonlySet<number>): void {
    const next = pruneLabelFilter(state, knownIds);
    if (
      next.include.length === state.include.length &&
      next.exclude.length === state.exclude.length
    ) {
      return;
    }
    state.include = next.include;
    state.exclude = next.exclude;
    void writeSetting('graph.label_include', state.include);
    void writeSetting('graph.label_exclude', state.exclude);
  },
};
