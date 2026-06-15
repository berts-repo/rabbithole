// Draw-analyst-edge interaction mode.
//
// The graph toolbar's Spline button calls request(); GraphCanvas decides:
//   ≥ 2 nodes selected → open the Draw Edge modal directly in batch mode
//   0-1 selected       → enter sequential mode (begin()) — the analyst
//                        clicks a source node, then a destination node.
// GraphToolbar reads `active` / `source` to swap its status line for the
// "Click source / destination node" instruction; GraphCanvas drives the
// state from canvas clicks and opens the modal once both ends are picked.

import type { GraphNode } from '$lib/api';

interface DrawEdgeState {
  active: boolean;
  source: GraphNode | null;
  requestToken: number;
}

const state = $state<DrawEdgeState>({
  active: false,
  source: null,
  requestToken: 0,
});

export const drawEdgeStore = {
  get active() {
    return state.active;
  },
  get source() {
    return state.source;
  },
  get requestToken() {
    return state.requestToken;
  },

  /** Toolbar Spline button — GraphCanvas resolves batch vs sequential. */
  request(): void {
    state.requestToken++;
  },
  /** GraphCanvas — enter sequential pick mode. */
  begin(): void {
    state.active = true;
    state.source = null;
  },
  /** GraphCanvas — first (source) node picked. */
  setSource(node: GraphNode): void {
    state.source = node;
  },
  /** Exit sequential mode (both ends picked, or cancelled). */
  cancel(): void {
    state.active = false;
    state.source = null;
  },
};
