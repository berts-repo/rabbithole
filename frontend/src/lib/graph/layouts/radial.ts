// Radial-by-domain layout — pure geometry, no physics. Each domain gets a
// hub placed on a ring; that domain's pages fan out in a sunflower spiral
// around the hub. Nodes with no domain land in their own group at the
// centre. Moved verbatim from GraphCanvas's original radialLayoutByDomain.

import type Graph from 'graphology';
import type { GraphNode } from '$lib/api';
import { NODE_SPACING } from '$lib/graph/model/geometry';
import { isUncrawled } from '$lib/nodeState';

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

export function radialLayout(g: Graph): void {
  const HUB_RING_SCALE = 3; // hub ring radius = max-group-radius × this

  // Group fetched nodes by domain.
  const groups = new Map<string, string[]>();
  g.forEachNode((node, attrs) => {
    const raw = attrs.raw as GraphNode | undefined;
    if (!raw || isUncrawled(raw)) return;
    const domain = raw.domain ?? '__none__';
    const bucket = groups.get(domain);
    if (bucket) bucket.push(node);
    else groups.set(domain, [node]);
  });
  if (groups.size === 0) return;

  // Arc radius needed to spread N nodes with NODE_SPACING gap; N=1 → 0.
  const arcRadius = (n: number) =>
    n <= 1 ? 0 : (n * NODE_SPACING) / (2 * Math.PI);

  // Largest single group drives the hub ring so no group overlaps its
  // neighbour's personal space.
  const maxR = Math.max(
    ...[...groups.values()].map((v) => arcRadius(v.length)),
  );
  const hubRingR = groups.size > 1 ? maxR * HUB_RING_SCALE : 0;

  let gi = 0;
  for (const [, nodes] of groups) {
    const hubAngle = groups.size > 1 ? (2 * Math.PI * gi) / groups.size : 0;
    const hx = Math.cos(hubAngle) * hubRingR;
    const hy = Math.sin(hubAngle) * hubRingR;

    // The hub is the cluster node if one exists, else node 0.
    const hubIdx = nodes.findIndex((n) => {
      const raw = g.getNodeAttribute(n, 'raw') as GraphNode | undefined;
      return raw?.is_cluster;
    });
    const pivot = hubIdx >= 0 ? hubIdx : 0;
    const hubKey = nodes[pivot];
    g.setNodeAttribute(hubKey, 'x', hx);
    g.setNodeAttribute(hubKey, 'y', hy);

    // Remaining nodes fan around the hub in a sunflower spiral.
    const rest = nodes.filter((_, i) => i !== pivot);
    const r0 = arcRadius(rest.length + 1);
    rest.forEach((node, i) => {
      const theta = i * GOLDEN_ANGLE;
      const r = r0 * Math.sqrt(i + 1);
      g.setNodeAttribute(node, 'x', hx + Math.cos(theta) * r);
      g.setNodeAttribute(node, 'y', hy + Math.sin(theta) * r);
    });

    gi++;
  }
}
