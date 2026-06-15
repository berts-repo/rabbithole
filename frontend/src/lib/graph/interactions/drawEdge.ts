// Draw-edge interaction policy for the graph canvas.
//
// Two pure resolvers: resolveDrawEdgeRequest decides what the toolbar
// Draw-edge button does given the current selection size, and
// resolveDrawEdgeClick is the sequential canvas-pick state machine —
// the first pick sets the source, a second distinct pick opens the
// sequential edge modal. No store reads, no Sigma; GraphCanvas resolves
// the clicked node (cluster check + payload lookup) and dispatches the
// returned outcome.

import type { GraphNode } from '$lib/api';

// What the toolbar Draw-edge button does. With >= 2 nodes already
// selected the batch modal opens immediately; otherwise the canvas
// enters sequential pick mode (drawEdgeStore.begin()).
export type DrawEdgeRequestOutcome =
  | { kind: 'open-batch-modal' }
  | { kind: 'begin-pick' };

export function resolveDrawEdgeRequest(
  selectionCount: number,
): DrawEdgeRequestOutcome {
  return selectionCount >= 2
    ? { kind: 'open-batch-modal' }
    : { kind: 'begin-pick' };
}

// What a canvas click does while sequential pick mode is active.
export type DrawEdgeClickOutcome =
  // Cluster node, empty pick, or the current source re-clicked — no
  // state change.
  | { kind: 'ignore' }
  // First valid pick — becomes the edge source.
  | { kind: 'set-source'; node: GraphNode }
  // Second distinct pick — open the sequential edge modal.
  | { kind: 'open-sequential'; source: GraphNode; dest: GraphNode };

export function resolveDrawEdgeClick(
  clickedIsCluster: boolean,
  picked: GraphNode | undefined,
  currentSource: GraphNode | null,
): DrawEdgeClickOutcome {
  // Synthetic cluster nodes can't be an analyst-edge endpoint.
  if (clickedIsCluster) return { kind: 'ignore' };
  if (!picked) return { kind: 'ignore' };
  if (!currentSource) return { kind: 'set-source', node: picked };
  // Re-clicking the source is a no-op — an edge needs a distinct dest.
  if (currentSource.id === picked.id) return { kind: 'ignore' };
  return { kind: 'open-sequential', source: currentSource, dest: picked };
}
