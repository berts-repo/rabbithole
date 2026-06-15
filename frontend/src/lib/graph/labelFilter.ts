// Label visibility filter (item 11, Phase 3c) — a separate dimension from the
// server-side `graph_filters` term-hide. The analyst marks each label neutral,
// include, or exclude; the predicate composes those into a keep/drop decision
// over a node's labels (direct *and* via-domain — an Avoid inherited from the
// domain still excludes the node).
//
// Rules, in order:
//   - EXCLUDE wins: a node carrying any excluded label is dropped. (The
//     "Avoid" workflow is exactly this.)
//   - INCLUDE is an allowlist: when any label is included, a node must carry at
//     least one included label to pass. With no includes, all non-excluded
//     nodes pass.
//
// Pure TypeScript — no Svelte runtime — so vitest covers it directly. The
// store (`stores/labelFilter.svelte.ts`) holds the persisted sets; the
// visibility controller calls `passesLabelFilter` per node.

export interface LabelFilterState {
  include: number[];
  exclude: number[];
}

export type LabelFilterMode = 'neutral' | 'include' | 'exclude';

export const EMPTY_LABEL_FILTER: LabelFilterState = { include: [], exclude: [] };

export function isLabelFilterEmpty(state: LabelFilterState): boolean {
  return state.include.length === 0 && state.exclude.length === 0;
}

// Keep-decision for one node given its direct + via-domain label ids.
export function passesLabelFilter(
  state: LabelFilterState,
  directIds: readonly number[],
  domainIds: readonly number[],
): boolean {
  if (isLabelFilterEmpty(state)) return true;
  const ids = new Set<number>([...directIds, ...domainIds]);
  if (state.exclude.some((id) => ids.has(id))) return false;
  if (state.include.length > 0 && !state.include.some((id) => ids.has(id))) {
    return false;
  }
  return true;
}

export function labelMode(state: LabelFilterState, id: number): LabelFilterMode {
  if (state.exclude.includes(id)) return 'exclude';
  if (state.include.includes(id)) return 'include';
  return 'neutral';
}

// Tri-state cycle for a label chip: neutral → include → exclude → neutral. A
// label is only ever in one set, so each transition clears it from the other.
export function cycleLabel(
  state: LabelFilterState,
  id: number,
): LabelFilterState {
  const mode = labelMode(state, id);
  const without = {
    include: state.include.filter((x) => x !== id),
    exclude: state.exclude.filter((x) => x !== id),
  };
  if (mode === 'neutral') return { ...without, include: [...without.include, id] };
  if (mode === 'include') return { ...without, exclude: [...without.exclude, id] };
  return without; // exclude → neutral
}

// Drop ids the catalog no longer knows (a deleted label leaves a stale id in
// the persisted set). Keeps the filter honest after a label delete.
export function pruneLabelFilter(
  state: LabelFilterState,
  knownIds: ReadonlySet<number>,
): LabelFilterState {
  return {
    include: state.include.filter((id) => knownIds.has(id)),
    exclude: state.exclude.filter((id) => knownIds.has(id)),
  };
}
