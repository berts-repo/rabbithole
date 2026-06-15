// Three-mode selection model (CLAUDE.md "Selection model" + F6 spec):
//   - full      → bottom-pane row click; drives bottom-pane active row,
//                 right panel, and graph highlight.
//   - highlight → graph-node single click, left-pane search result, or
//                 bottom-pane Domains row (multi-highlight). Drives the
//                 right panel + graph highlight only, not bottom row.
//                 NEVER trips the cluster workspace, regardless of
//                 selection count.
//   - cluster   → explicit multi-select gesture from the graph canvas
//                 (Ctrl/Cmd-click, Shift-click, Ctrl+A). When set size
//                 is ≥ 2, the right panel switches to cluster workspace
//                 (Nodes / Q&A / Common).
//
// The cluster trigger is mode + count, NOT count alone — the bottom-
// pane Domains row click highlights every node of a host but stays in
// 'highlight' mode so it doesn't pull the analyst into a workspace they
// didn't ask for.
//
// INVARIANT — selection is *intent*, not a visual state. A
// `selectedNodeId` means "the analyst is currently thinking about this
// node"; whether the node happens to be rendered in the graph right
// now is a separate concern. Selection must only be cleared by:
//   1. explicit user action (clickStage, Escape, X on right pane,
//      replaceMulti from a search/list selector),
//   2. true node deletion from the database.
// It must NOT be cleared by graph topology changes — rebuilds, diff
// updates, filter toggles, hide-from-graph, tab switches, or cluster
// transitions. The right pane (F6) is responsible for fetching node
// data from the API by id, not from graphology, so selection survives
// any view change that doesn't actually delete the node.

export type SelectMode = 'full' | 'highlight' | 'cluster';

interface SelectionState {
  // Single "focus" node — drives right panel and bottom-pane active row.
  selectedNodeId: number | null;
  selectMode: SelectMode;
  // Multi-select set; always includes selectedNodeId when non-null.
  selectedIds: Set<number>;
}

const state = $state<SelectionState>({
  selectedNodeId: null,
  selectMode: 'full',
  selectedIds: new Set(),
});

function copyAnd(mutate: (s: Set<number>) => void): Set<number> {
  // Svelte 5 rune diffing on Set is by reference — return a fresh Set so
  // consumers re-render.
  const next = new Set(state.selectedIds);
  mutate(next);
  return next;
}

export const selectionStore = {
  get selectedNodeId() {
    return state.selectedNodeId;
  },
  get selectMode() {
    return state.selectMode;
  },
  get selectedIds() {
    return state.selectedIds;
  },
  get multiCount() {
    return state.selectedIds.size;
  },
  isSelected(id: number): boolean {
    return state.selectedIds.has(id);
  },

  fullSelect(id: number) {
    state.selectedNodeId = id;
    state.selectMode = 'full';
    state.selectedIds = new Set([id]);
  },
  highlight(id: number) {
    state.selectedNodeId = id;
    state.selectMode = 'highlight';
    state.selectedIds = new Set([id]);
  },
  clear() {
    state.selectedNodeId = null;
    state.selectMode = 'full';
    state.selectedIds = new Set();
  },

  // Multi-select primitives.
  //
  // `replaceMulti` is the HIGHLIGHT-ONLY multi-select primitive (used by
  // the bottom-pane Domains row click). Mode stays 'highlight' no matter
  // how many ids end up in the set — never trips the cluster workspace.
  replaceMulti(ids: Iterable<number>): void {
    const next = new Set<number>();
    for (const id of ids) next.add(id);
    state.selectedIds = next;
    state.selectMode = 'highlight';
    if (next.size === 0) {
      state.selectedNodeId = null;
    } else if (state.selectedNodeId === null || !next.has(state.selectedNodeId)) {
      const first = next.values().next();
      state.selectedNodeId = first.done ? null : first.value;
    }
  },
  // `replaceCluster` is the CLUSTER multi-select primitive (Ctrl+A on
  // the graph, future cluster-mode entrypoints). Mode becomes 'cluster'
  // when ≥ 2 ids land in the set; drops back to 'highlight' at 1 and
  // 'full' (null focus) at 0 so the right panel branches correctly.
  replaceCluster(ids: Iterable<number>): void {
    const next = new Set<number>();
    for (const id of ids) next.add(id);
    state.selectedIds = next;
    if (next.size === 0) {
      state.selectedNodeId = null;
      state.selectMode = 'full';
    } else {
      if (state.selectedNodeId === null || !next.has(state.selectedNodeId)) {
        const first = next.values().next();
        state.selectedNodeId = first.done ? null : first.value;
      }
      state.selectMode = next.size >= 2 ? 'cluster' : 'highlight';
    }
  },
  // `toggleCluster` is the per-click cluster toggle (Ctrl/Shift-click on
  // a graph node). Same mode rules as `replaceCluster`. The first
  // Ctrl-click on a focused-but-single node lifts the selection into
  // cluster mode the moment the count crosses 2.
  toggleCluster(id: number): void {
    const next = copyAnd((s) => {
      if (s.has(id)) s.delete(id);
      else s.add(id);
    });
    state.selectedIds = next;
    if (next.size === 0) {
      state.selectedNodeId = null;
      state.selectMode = 'full';
      return;
    }
    if (next.has(id)) {
      state.selectedNodeId = id;
    } else if (state.selectedNodeId === null || !next.has(state.selectedNodeId)) {
      const first = next.values().next();
      state.selectedNodeId = first.done ? null : first.value;
    }
    state.selectMode = next.size >= 2 ? 'cluster' : 'highlight';
  },
  // Per-id removal from the cluster set (cluster workspace ✕ button).
  // Mirrors the toggleCluster removal branch so the panel snaps back to
  // single-node view automatically once the count drops to 1.
  deselect(id: number): void {
    if (!state.selectedIds.has(id)) return;
    const next = copyAnd((s) => s.delete(id));
    state.selectedIds = next;
    if (next.size === 0) {
      state.selectedNodeId = null;
      state.selectMode = 'full';
      return;
    }
    if (state.selectedNodeId === id) {
      const first = next.values().next();
      state.selectedNodeId = first.done ? null : first.value;
    }
    state.selectMode = next.size >= 2 ? 'cluster' : 'highlight';
  },
  // Atomic setter that honours an exact captured focus id —
  // workspaceSnapshots calls this on tab restore so a `null`-current
  // focus doesn't get rewritten by replaceMulti's "pick arbitrary".
  restoreSet(ids: Set<number>, focusId: number | null): void {
    state.selectedIds = new Set(ids);
    state.selectedNodeId = focusId;
    state.selectMode = 'highlight';
  },
};
