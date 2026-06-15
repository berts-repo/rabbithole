// Hop-expansion for the graph toolbar's "Expand to collection" control.
//
// Pure BFS over the in-memory graphology instance — no backend round-trip,
// because the graph payload is already loaded. Returns the node ids within
// `hops` of any seed (seeds included). Synthetic domain-cluster nodes are
// dropped: they aren't real, collectable nodes.

import type Graph from 'graphology';
import { isClusterKey } from '$lib/graph/model/clusterDomain';

export function expandByHops(
  g: Graph,
  seedIds: number[],
  hops: number,
): number[] {
  const seen = new Set<string>();
  let frontier: string[] = [];
  for (const id of seedIds) {
    const key = String(id);
    if (g.hasNode(key) && !seen.has(key)) {
      seen.add(key);
      frontier.push(key);
    }
  }
  for (let h = 0; h < hops; h++) {
    const next: string[] = [];
    for (const node of frontier) {
      g.forEachNeighbor(node, (nb: string) => {
        if (!seen.has(nb)) {
          seen.add(nb);
          next.push(nb);
        }
      });
    }
    if (next.length === 0) break;
    frontier = next;
  }
  const out: number[] = [];
  for (const key of seen) {
    if (!isClusterKey(key)) out.push(Number(key));
  }
  return out;
}
