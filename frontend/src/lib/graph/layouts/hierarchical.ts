// Hierarchical layout — top-down tiers by crawl depth. Depth 0 (the seed)
// sits in the top row; each deeper level is a row below. Within a row,
// nodes spread evenly along x and are sorted by domain so same-site pages
// cluster together. Null-depth nodes drop to a row beneath the deepest
// real tier. Pure geometry, no physics.

import type Graph from 'graphology';
import type { GraphNode } from '$lib/api';
import { isUncrawled } from '$lib/nodeState';

export function hierarchicalLayout(g: Graph): void {
  const ROW_GAP = 70;
  const COL_GAP = 26;

  const tiers = new Map<number, string[]>();
  let maxDepth = 0;
  g.forEachNode((node, attrs) => {
    const raw = attrs.raw as GraphNode | undefined;
    if (!raw || isUncrawled(raw)) return;
    const d = typeof raw.depth === 'number' ? raw.depth : -1;
    if (d > maxDepth) maxDepth = d;
    const bucket = tiers.get(d);
    if (bucket) bucket.push(node);
    else tiers.set(d, [node]);
  });
  if (tiers.size === 0) return;

  // Null-depth nodes (-1) sit one row below the deepest real tier.
  const rowFor = (d: number) => (d < 0 ? maxDepth + 1 : d);

  for (const [d, nodes] of tiers) {
    nodes.sort((a, b) => {
      const da = (g.getNodeAttribute(a, 'raw') as GraphNode).domain ?? '';
      const db = (g.getNodeAttribute(b, 'raw') as GraphNode).domain ?? '';
      return da < db ? -1 : da > db ? 1 : 0;
    });
    const width = (nodes.length - 1) * COL_GAP;
    const y = rowFor(d) * ROW_GAP;
    nodes.forEach((node, i) => {
      g.setNodeAttribute(node, 'x', i * COL_GAP - width / 2);
      g.setNodeAttribute(node, 'y', y);
    });
  }
}
