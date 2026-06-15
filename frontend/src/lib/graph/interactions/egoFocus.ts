// Graph traversal backing the ego-focus and path-overlay interactions.
//
// computeEgoReachable is the depth-bounded BFS that produces the focus
// subgraph. shortestPathEdges finds the edge set on the shortest path
// between two nodes within a reachable set — it backs both the
// focus->hover path highlight and the multi-select hover-path overlay.
// Both are pure: GraphCanvas owns the egoFocus state and the
// reachable-set cache; this module owns the traversal only.

import type Graph from 'graphology';

// BFS over the undirected neighbourhood of `root`, bounded to `depth`
// hops. The returned set always contains `root`; it is empty when
// `root` is not a node of `g`.
export function computeEgoReachable(
  g: Graph,
  root: string,
  depth: number,
): Set<string> {
  if (!g.hasNode(root)) return new Set();
  const reachable = new Set<string>([root]);
  let frontier: string[] = [root];
  for (let d = 0; d < depth; d++) {
    const next: string[] = [];
    for (const u of frontier) {
      g.forEachNeighbor(u, (v) => {
        if (!reachable.has(v)) {
          reachable.add(v);
          next.push(v);
        }
      });
    }
    frontier = next;
  }
  return reachable;
}

// BFS from `source` to `target`, returning the set of edge keys on the
// shortest path, or null when `target` is unreachable. Traversal is
// confined to `reachable` — pass the ego-reachable set to bound it to
// the focus subgraph, or the full visible-node set for an unbounded
// "is there ANY path" search. A source equal to the target yields an
// empty set (zero-length path). O(V + E) within `reachable`; callers
// only run this on hover-enter, not per frame, so the cost is bounded.
export function shortestPathEdges(
  g: Graph,
  source: string,
  target: string,
  reachable: Set<string>,
): Set<string> | null {
  if (source === target) return new Set();
  if (!reachable.has(source) || !reachable.has(target)) return null;
  const parentEdge = new Map<string, { parent: string; edge: string }>();
  const visited = new Set<string>([source]);
  let frontier: string[] = [source];
  let found = false;
  while (frontier.length > 0 && !found) {
    const next: string[] = [];
    for (const u of frontier) {
      g.forEachEdge(u, (edge, _attrs, eSrc, eTgt) => {
        if (found) return;
        const v = eSrc === u ? eTgt : eSrc;
        if (visited.has(v) || !reachable.has(v)) return;
        visited.add(v);
        parentEdge.set(v, { parent: u, edge });
        if (v === target) found = true;
        else next.push(v);
      });
      if (found) break;
    }
    frontier = next;
  }
  if (!found) return null;
  const edges = new Set<string>();
  let cur = target;
  while (cur !== source) {
    const step = parentEdge.get(cur);
    if (!step) break;
    edges.add(step.edge);
    cur = step.parent;
  }
  return edges;
}
