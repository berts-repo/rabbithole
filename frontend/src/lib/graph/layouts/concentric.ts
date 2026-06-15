// Concentric layout — rings by crawl depth. Depth 0 (the seed) sits at the
// centre; each deeper level is a wider ring. Null-depth nodes land on the
// outermost ring. Pure geometry, no physics.

import type Graph from 'graphology';
import type { GraphNode } from '$lib/api';
import { isUncrawled } from '$lib/nodeState';

export function concentricLayout(g: Graph): void {
  const RING_GAP = 56;

  const rings = new Map<number, string[]>();
  let maxDepth = 0;
  g.forEachNode((node, attrs) => {
    const raw = attrs.raw as GraphNode | undefined;
    if (!raw || isUncrawled(raw)) return;
    const d = typeof raw.depth === 'number' ? raw.depth : -1;
    if (d > maxDepth) maxDepth = d;
    const bucket = rings.get(d);
    if (bucket) bucket.push(node);
    else rings.set(d, [node]);
  });
  if (rings.size === 0) return;

  const ringFor = (d: number) => (d < 0 ? maxDepth + 1 : d);

  for (const [d, nodes] of rings) {
    const ring = ringFor(d);
    // Ring 0 collapses to the origin for a lone node, else a small inner
    // radius so multiple depth-0 nodes don't stack on one point.
    let radius = ring * RING_GAP;
    if (ring === 0) radius = nodes.length > 1 ? RING_GAP * 0.4 : 0;
    if (radius === 0) {
      g.setNodeAttribute(nodes[0], 'x', 0);
      g.setNodeAttribute(nodes[0], 'y', 0);
      continue;
    }
    nodes.forEach((node, i) => {
      const a = (2 * Math.PI * i) / nodes.length;
      g.setNodeAttribute(node, 'x', Math.cos(a) * radius);
      g.setNodeAttribute(node, 'y', Math.sin(a) * radius);
    });
  }
}
