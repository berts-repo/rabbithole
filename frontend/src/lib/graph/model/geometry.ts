// Graph node geometry — render sizing and stub-halo placement.
//
// `nodeSize` maps degree/role to a Sigma render size. `haloOffset` and
// `sunflowerAround` are the two Vogel-spiral placements: `haloOffset`
// orbits one stub around its parent; `sunflowerAround` re-fans a whole
// domain's members when a cluster expands. `positionStubsAroundParents`
// re-places every halo after a layout pass moves the fetched nodes.
//
// Pure geometry — no runes, no Sigma. The only graphology dependency is
// the in-place node mutation inside `positionStubsAroundParents`.

import type Graph from 'graphology';
import type { GraphNode } from '$lib/api';
import { isUncrawled } from '$lib/nodeState';

// Minimum distance between adjacent page nodes. Shared with the radial
// layout — `lib/graph/layouts/radial.ts` imports this constant — so a
// cluster-expand fan re-emerges at the same density `radialLayout`
// would have produced. Single source of truth: change it here only.
export const NODE_SPACING = 6;

export function nodeSize(
  inDeg: number,
  outDeg: number,
  cluster: boolean,
  uncrawled: boolean,
): number {
  if (cluster) return 12;
  // Uncrawled placeholders render small so a parent + its halo reads as
  // "hub with uncrawled outlinks" rather than as a cluster of peers.
  if (uncrawled) return 1.0;
  const deg = inDeg + outDeg;
  // Light log scaling so a 100-edge hub doesn't dwarf everything else.
  return 4 + Math.min(8, Math.log2(1 + deg) * 1.5);
}

// Vogel's sunflower spiral — uniform density, deterministic given an index.
// Returns absolute coords for a stub indexed `i` orbiting (px, py).
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
export const HALO_BASE_R = 12;
export function haloOffset(
  px: number,
  py: number,
  i: number,
  hubRadius = 0,
): { x: number; y: number } {
  // Start the spiral past the hub's own radius so the innermost stubs never
  // tuck under (or touch) their parent node — the spiral then fans outward
  // from a clean ring one HALO_BASE_R step beyond the hub's edge.
  const r = hubRadius + HALO_BASE_R * Math.sqrt(i + 1);
  const theta = i * GOLDEN_ANGLE;
  return { x: px + Math.cos(theta) * r, y: py + Math.sin(theta) * r };
}

// Sunflower fan around (px, py) sized for `total` siblings — the shape
// `radialLayout` lays a single domain's members in. Reused on
// cluster-expand so members re-emerge into the same fan they'd have
// landed in on first paint, instead of scattering randomly around the
// cluster's last position.
export function sunflowerAround(
  px: number,
  py: number,
  i: number,
  total: number,
): { x: number; y: number } {
  if (total <= 1) return { x: px, y: py };
  const r0 = (total * NODE_SPACING) / (2 * Math.PI);
  const r = r0 * Math.sqrt(i + 1);
  const theta = i * GOLDEN_ANGLE;
  return { x: px + Math.cos(theta) * r, y: py + Math.sin(theta) * r };
}

// Clearance past the crowd's outermost node before the first orphan ring,
// and a floor so orphans still spread on an empty/pre-layout graph (where the
// crowd's radius is ~0) instead of stacking on the origin.
const ORPHAN_RING_GAP = NODE_SPACING * 3;
const ORPHAN_RING_MIN_RADIUS = 20;

/**
 * Rings edgeless uncrawled placeholders outside everything else.
 *
 * Search-discovered nodes the analyst pins to the graph have no link to any
 * fetched node, so there's nothing to halo around. Left at their random seed
 * coords they pile onto the origin, buried under the crawled graph. This
 * pushes them outward onto a golden-angle spiral starting just past the
 * bounding circle of every other node — the "gravity that shoves them away
 * from the crowd" effect — without dragging uncrawled nodes into ForceAtlas2
 * (they're deliberately kept out of the force sim; see layouts/force.ts).
 *
 * Deterministic: orphans are ordered by id, so a reload or re-layout
 * reproduces the same arrangement and pinning one more doesn't scramble the
 * rest. Orphans the analyst dragged (userPositioned) keep their spot and are
 * excluded from both the crowd and the ring.
 */
export function positionOrphanStubsOutside(g: Graph): void {
  const isOrphan = (attrs: Record<string, unknown>): boolean => {
    const raw = attrs.raw as GraphNode | undefined;
    return (
      !!raw &&
      isUncrawled(raw) &&
      (attrs.parent_id === null || attrs.parent_id === undefined)
    );
  };

  const orphans: string[] = [];
  let sumX = 0;
  let sumY = 0;
  let crowd = 0;
  g.forEachNode((node, attrs) => {
    if (isOrphan(attrs)) {
      if (attrs.userPositioned !== true) orphans.push(node);
      return;
    }
    sumX += attrs.x as number;
    sumY += attrs.y as number;
    crowd++;
  });
  if (orphans.length === 0) return;

  const cx = crowd > 0 ? sumX / crowd : 0;
  const cy = crowd > 0 ? sumY / crowd : 0;

  let maxR = 0;
  if (crowd > 0) {
    g.forEachNode((_node, attrs) => {
      if (isOrphan(attrs)) return;
      const dx = (attrs.x as number) - cx;
      const dy = (attrs.y as number) - cy;
      const r = Math.sqrt(dx * dx + dy * dy);
      if (r > maxR) maxR = r;
    });
  }
  const ringR = Math.max(maxR + ORPHAN_RING_GAP, ORPHAN_RING_MIN_RADIUS);

  orphans.sort((a, b) => Number(a) - Number(b));
  orphans.forEach((node, i) => {
    const theta = i * GOLDEN_ANGLE;
    const r = ringR + NODE_SPACING * Math.sqrt(i);
    g.setNodeAttribute(node, 'x', cx + Math.cos(theta) * r);
    g.setNodeAttribute(node, 'y', cy + Math.sin(theta) * r);
  });
}

/**
 * Re-places every stub around its parent's current position. Call after
 * FA2 moves the fetched-node layout — the halo needs to follow. Stubs
 * whose parent isn't in the graph (orphans) are left where they are.
 *
 * Stubs flagged with `userPositioned: true` (the analyst dragged them)
 * are skipped — they keep their dragged spot and don't claim a halo
 * slot, so subsequent siblings fan around the parent normally.
 */
export function positionStubsAroundParents(g: Graph): void {
  const byParent = new Map<string, string[]>();
  g.forEachNode((node, attrs) => {
    const raw = attrs.raw as GraphNode | undefined;
    if (!raw || !isUncrawled(raw)) return;
    if (attrs.userPositioned === true) return;
    const parent = attrs.parent_id as string | number | null | undefined;
    if (parent === null || parent === undefined) return;
    const pk = typeof parent === 'string' ? parent : String(parent);
    if (!g.hasNode(pk)) return;
    const bucket = byParent.get(pk);
    if (bucket) bucket.push(node);
    else byParent.set(pk, [node]);
  });
  for (const [parentKey, stubs] of byParent) {
    const px = g.getNodeAttribute(parentKey, 'x') as number;
    const py = g.getNodeAttribute(parentKey, 'y') as number;
    const hubRadius = (g.getNodeAttribute(parentKey, 'size') as number | undefined) ?? 0;
    stubs.sort();
    stubs.forEach((stubKey, i) => {
      const pos = haloOffset(px, py, i, hubRadius);
      g.setNodeAttribute(stubKey, 'x', pos.x);
      g.setNodeAttribute(stubKey, 'y', pos.y);
    });
  }
}
