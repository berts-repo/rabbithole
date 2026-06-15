// Payload → graphology apply policy: the rebuild and diff paths.
//
// `rebuildInto` does a full clear + re-add — slow but always correct.
// `applyDiff` does an in-place add/remove/update against the graph's
// current shape — fast, and it preserves Sigma's WebGL state plus the
// x/y of nodes the user dragged or the layout already placed. `applyDiff`
// returns false to tell the caller to fall back to `rebuildInto` whenever
// it would have to perform a topology change it can't express cleanly
// (cluster set transitions, stub-visibility flips).
//
// Both take the graphology instance as a parameter and mutate it in
// place — they never construct or swap it, so the store's single stable
// instance survives every apply. They also take a `ClusterFilterOptions`
// snapshot rather than reading the filter store directly, which keeps
// this module pure (no runes) and unit-testable with plain fixtures.

import type Graph from 'graphology';
import type { GraphPayload, GraphEdge, GraphNode } from '$lib/api';
import { isClusterKey, clusterKey } from './clusterDomain';
import { labelClusterKey } from './clusterLabel';
import { planFolds, type FoldOptions, type LabelClusterDef } from './foldPlan';
import {
  nodeSize,
  haloOffset,
  sunflowerAround,
  positionOrphanStubsOutside,
  NODE_SPACING,
} from './geometry';
import { isUncrawled } from '$lib/nodeState';

// Filter inputs the apply paths need, snapshotted by the caller. The
// store builds this from `graphFiltersStore` + its own `expandedDomains`
// so the transforms here stay free of any rune dependency.
export interface ClusterFilterOptions {
  // "Show uncrawled" — render placeholder nodes for resources whose state
  // is not 'crawled' (unknown / known / dead) as a halo around their parent.
  showUncrawled: boolean;
  groupByDomain: boolean;
  expandedDomains: ReadonlySet<string>;
  // Analyst-pinned resource ids — kept on the canvas even when showUncrawled
  // is off. Lets "Add to Graph" reveal one node without un-hiding the whole
  // discovered-placeholder halo. See stores/graphPins.svelte.ts.
  pinnedIds: ReadonlySet<number>;
  // Phase 3d collapse axes, per workspace tab. Selective domain folds
  // (independent of groupByDomain) and rank-ordered collapse-by-label folds.
  // The unified D5/D6 resolution in foldPlan decides each page's single home.
  collapsedDomains: ReadonlySet<string>;
  collapsedLabels: readonly LabelClusterDef[];
}

// Project the apply-path options onto the fold resolver's input shape.
function foldOptions(opts: ClusterFilterOptions): FoldOptions {
  return {
    groupByDomain: opts.groupByDomain,
    expandedDomains: opts.expandedDomains,
    collapsedDomains: opts.collapsedDomains,
    collapsedLabels: opts.collapsedLabels,
  };
}

// An uncrawled placeholder is materialized when the global toggle is on, or
// when the analyst pinned this specific id. The single source of truth both
// apply paths share so rebuild and diff never disagree on what's shown.
function uncrawledShown(id: number, opts: ClusterFilterOptions): boolean {
  return opts.showUncrawled || opts.pinnedIds.has(id);
}

export function rebuildInto(
  g: Graph,
  payload: GraphPayload,
  opts: ClusterFilterOptions,
): void {
  const { showUncrawled, pinnedIds } = opts;
  // Snapshot positions before clearing so existing nodes keep their
  // laid-out coordinates across polls. Without this, every 15 s poll
  // would scramble the layout the analyst is working against. Also
  // snapshot userPositioned so a node the analyst dragged survives
  // a cluster-transition rebuild (the post-rebuild layout pass and
  // positionStubsAroundParents both consult this flag).
  const positions = new Map<string, { x: number; y: number }>();
  const dragged = new Set<string>();
  g.forEachNode((node, attrs) => {
    positions.set(node, { x: attrs.x as number, y: attrs.y as number });
    if (attrs.userPositioned === true) dragged.add(node);
  });
  g.clear();

  // ---- Cluster planning (Phase 3d) ----
  // One unified pass resolves every fetched page to its single fold home
  // (highest-ranked collapsed label, else collapsed domain; D5/D6). The plan
  // gives us the page→cluster-key reverse lookup edge/stub rewrites need, plus
  // the synthesized aggregate node per fold.
  const plan = planFolds(payload.nodes, foldOptions(opts));
  const memberToCluster = plan.memberToCluster;

  // ---- Re-emergence fan planning ----
  // When a fold disappears (the analyst expanded a domain, turned groupByDomain
  // off, or un-collapsed a label), its members aren't in the position snapshot —
  // they were folded into the cluster node, which is. Seed each re-emerging
  // member on a sunflower fan around its old fold's last position so they don't
  // scatter to Math.random() coords (which on an FA2-scale layout pile
  // invisibly near the origin). A member's candidate folds are its domain
  // cluster and any label cluster it carried; the source is whichever still has
  // a snapshot position but is no longer a fold in the current plan.
  const reemergePos = new Map<number, { x: number; y: number }>();
  {
    const groups = new Map<string, GraphNode[]>();
    for (const n of payload.nodes) {
      if (isUncrawled(n)) continue;
      if (memberToCluster.has(n.id)) continue; // still folded
      if (positions.has(String(n.id))) continue; // kept its own position
      let src: string | null = null;
      const candidates: string[] = [];
      if (n.domain) candidates.push(clusterKey(n.domain));
      for (const lid of n.label_ids) candidates.push(labelClusterKey(lid));
      for (const lid of n.domain_label_ids) candidates.push(labelClusterKey(lid));
      for (const c of candidates) {
        if (positions.has(c) && !plan.clusters.has(c)) {
          src = c;
          break;
        }
      }
      if (!src) continue;
      const bucket = groups.get(src);
      if (bucket) bucket.push(n);
      else groups.set(src, [n]);
    }
    for (const [src, members] of groups) {
      const p = positions.get(src)!;
      members.forEach((m, i) => reemergePos.set(m.id, sunflowerAround(p.x, p.y, i, members.length)));
    }
  }

  // Build the stub → parent map by scanning edges once. Stubs render as a
  // halo around their parent fetched node, so we need to know who linked
  // them. Prefer a non-stub parent (the analyst-visible discoverer); fall
  // back to any source if every link to this stub came from another stub
  // (very rare — only happens via analyst-drawn edges between stubs).
  const stubIds = new Set<number>();
  for (const n of payload.nodes) {
    if (isUncrawled(n)) stubIds.add(n.id);
  }
  const stubParent = new Map<number, number>();
  for (const e of payload.edges) {
    if (!stubIds.has(e.to)) continue;
    if (stubIds.has(e.from)) continue;
    if (!stubParent.has(e.to)) stubParent.set(e.to, e.from);
  }
  for (const e of payload.edges) {
    if (!stubIds.has(e.to)) continue;
    if (!stubParent.has(e.to)) stubParent.set(e.to, e.from);
  }

  // ---- Pass 1: fetched nodes (real + synthetic clusters) ----
  // Fetched pages folded into any cluster are skipped — they're represented by
  // their fold node instead.
  for (const n of payload.nodes) {
    if (isUncrawled(n)) continue;
    if (memberToCluster.has(n.id)) continue;
    const id = String(n.id);
    const saved = positions.get(id) ?? reemergePos.get(n.id);
    g.addNode(id, {
      label: n.label,
      x: saved?.x ?? Math.random(),
      y: saved?.y ?? Math.random(),
      size: nodeSize(n.in_degree_count, n.out_degree_count, n.is_cluster, false),
      color: n.color,
      raw: n,
      userPositioned: dragged.has(id),
    });
  }

  // Synthetic fold nodes (domain + label). Position seeds from the fold's prior
  // graphology position if it existed, else from the centroid of its members'
  // snapshot positions. The centroid path makes the collapse visually feel like
  // "pages pull together into one dot"; expand on the next cycle then fans them
  // back out from that point.
  for (const [key, cluster] of plan.clusters) {
    const saved = positions.get(key);
    let cx: number;
    let cy: number;
    if (saved) {
      cx = saved.x;
      cy = saved.y;
    } else {
      let sx = 0;
      let sy = 0;
      let n = 0;
      for (const m of cluster.members) {
        const p = positions.get(String(m.id));
        if (!p) continue;
        sx += p.x;
        sy += p.y;
        n++;
      }
      if (n > 0) {
        cx = sx / n;
        cy = sy / n;
      } else {
        cx = Math.random();
        cy = Math.random();
      }
    }
    const raw = cluster.raw;
    g.addNode(key, {
      label: raw.label,
      x: cx,
      y: cy,
      size: nodeSize(raw.in_degree_count, raw.out_degree_count, true, false),
      color: raw.color,
      raw,
      userPositioned: dragged.has(key),
    });
  }

  // ---- Pass 2: uncrawled placeholders (halo) ----
  // Shown when the global toggle is on OR there are pins to honour; each node
  // is then filtered by uncrawledShown so a pins-only rebuild materializes
  // exactly the pinned ids and nothing else.
  if (showUncrawled || pinnedIds.size > 0) {
    // Group stubs by parent for halo placement. Parent may now be a
    // synthetic cluster key — same lookup either way. Stable iteration
    // order (parent ascending, stub id ascending) so reloads see the
    // same fan.
    const stubsByParent = new Map<string, GraphNode[]>();
    const orphanStubs: GraphNode[] = [];
    for (const n of payload.nodes) {
      if (!isUncrawled(n)) continue;
      if (!uncrawledShown(n.id, opts)) continue;
      const parentNumeric = stubParent.get(n.id);
      if (parentNumeric === undefined) {
        orphanStubs.push(n);
        continue;
      }
      // Redirect to the cluster if the parent's domain is collapsed.
      const redirected = memberToCluster.get(parentNumeric);
      const pk = redirected ?? String(parentNumeric);
      if (!g.hasNode(pk)) {
        orphanStubs.push(n);
        continue;
      }
      const bucket = stubsByParent.get(pk);
      if (bucket) bucket.push(n);
      else stubsByParent.set(pk, [n]);
    }

    for (const [parentKey, stubs] of stubsByParent) {
      const px = g.getNodeAttribute(parentKey, 'x') as number;
      const py = g.getNodeAttribute(parentKey, 'y') as number;
      stubs.sort((a, b) => a.id - b.id);
      stubs.forEach((n, i) => {
        const id = String(n.id);
        const saved = positions.get(id);
        const pos = saved ?? haloOffset(px, py, i);
        g.addNode(id, {
          label: n.label,
          x: pos.x,
          y: pos.y,
          size: nodeSize(n.in_degree_count, n.out_degree_count, n.is_cluster, true),
          color: n.color,
          raw: n,
          parent_id: parentKey,
          userPositioned: dragged.has(id),
        });
      });
    }
    // Stubs with no parent (or whose parent isn't in the current graph)
    // get random positions — there's nothing to halo around.
    for (const n of orphanStubs) {
      const id = String(n.id);
      const saved = positions.get(id);
      g.addNode(id, {
        label: n.label,
        x: saved?.x ?? Math.random(),
        y: saved?.y ?? Math.random(),
        size: nodeSize(n.in_degree_count, n.out_degree_count, n.is_cluster, true),
        color: n.color,
        raw: n,
        parent_id: null,
        userPositioned: dragged.has(id),
      });
    }
  }

  // ---- Pass 3: edges (with cluster rewriting + dedup) ----
  // Edges to filtered-out stubs are dropped by the hasNode guard below,
  // so the toggle hides their connecting edges for free. Edges whose
  // endpoints have been collapsed into a cluster get their key rewritten
  // to the cluster key; same-cluster self-loops are dropped (sigma 3
  // doesn't render them well, and "domain links to itself" is implicit
  // in the cluster representation). graphology multi:false dedupes
  // parallel collapsed edges automatically.
  for (const e of payload.edges) {
    const fromMember = memberToCluster.get(e.from);
    const toMember = memberToCluster.get(e.to);
    const from = fromMember ?? String(e.from);
    const to = toMember ?? String(e.to);
    if (from === to) continue;
    if (!g.hasNode(from) || !g.hasNode(to)) continue;
    // If either endpoint was rewritten, derive a synthetic key that
    // doesn't collide with the raw-edge key (which encodes from/to/source).
    // Only the first collapsed-pair edge wins; subsequent parallels are
    // skipped via the hasEdge guard.
    const key =
      fromMember || toMember
        ? `${from}->${to}:cluster`
        : edgeKey(e);
    if (g.hasEdge(key)) continue;
    g.addEdgeWithKey(key, from, to, {
      size: 1,
      color: e.source === 'analyst' ? '#00d4aa' : '#1a3a2a',
      type: e.source === 'analyst' ? 'arrow' : 'arrow',
      raw: e,
    });
  }

  // Edgeless pinned placeholders have no parent to halo around — ring them
  // outside the crowd now that every other node is placed.
  positionOrphanStubsOutside(g);
}

function edgeKey(e: GraphEdge): string {
  return `${e.from}->${e.to}:${e.source}`;
}

// Diff-update apply path. Returns true if the diff successfully landed,
// false to signal the caller should fall back to rebuildInto. Bailing is
// the safe default any time we'd have to perform a topology change the
// diff can't express cleanly (cluster set transitions, large filter
// shifts) — false-then-rebuild is correct but slow; true-then-diff is
// fast but only when we're sure the graph's current shape matches what
// the previous payload + current filters would have produced.
//
// What diff preserves that rebuild doesn't:
//   - Sigma's WebGL state (no add/drop event storm for unchanged nodes)
//   - x/y on nodes the user dragged (userPositioned: true)
//   - x/y on nodes already laid out (no random scatter on update)
export function applyDiff(
  g: Graph,
  newPayload: GraphPayload,
  opts: ClusterFilterOptions,
): boolean {
  // ---- Compute the fold plan that *should* hold for the new payload.
  const plan = planFolds(newPayload.nodes, foldOptions(opts));
  const newMemberToCluster = plan.memberToCluster;

  // Bail if the fold topology in g doesn't match the new plan — rebuild is the
  // only safe way to add/remove fold nodes (members would need to be folded
  // in/out and their positions reseeded). Compares the full fold key set, so a
  // changed domain *or* label fold triggers the rebuild.
  const existingClusterKeys = new Set<string>();
  g.forEachNode((node) => {
    if (isClusterKey(node)) existingClusterKeys.add(node);
  });
  if (existingClusterKeys.size !== plan.clusters.size) return false;
  for (const k of plan.clusters.keys()) {
    if (!existingClusterKeys.has(k)) return false;
  }

  // ---- Build stub→parent map from new payload's edges (same logic as
  // rebuildInto: prefer non-stub parent, fall back to any source).
  const newStubIds = new Set<number>();
  for (const n of newPayload.nodes) {
    if (isUncrawled(n)) newStubIds.add(n.id);
  }
  const newStubParent = new Map<number, number>();
  for (const e of newPayload.edges) {
    if (!newStubIds.has(e.to)) continue;
    if (newStubIds.has(e.from)) continue;
    if (!newStubParent.has(e.to)) newStubParent.set(e.to, e.from);
  }
  for (const e of newPayload.edges) {
    if (!newStubIds.has(e.to)) continue;
    if (!newStubParent.has(e.to)) newStubParent.set(e.to, e.from);
  }

  // ---- Desired node-key set.
  // Fetched (non-stub, non-collapsed) → String(id)
  // Stub (if showStubs) → String(id)
  // Cluster → clusterKey(domain)
  const desiredKeys = new Set<string>();
  const newRawByKey = new Map<string, GraphNode>();
  for (const n of newPayload.nodes) {
    if (isUncrawled(n)) {
      if (!uncrawledShown(n.id, opts)) continue;
      const key = String(n.id);
      desiredKeys.add(key);
      newRawByKey.set(key, n);
      continue;
    }
    if (newMemberToCluster.has(n.id)) continue;
    const key = String(n.id);
    desiredKeys.add(key);
    newRawByKey.set(key, n);
  }
  for (const k of plan.clusters.keys()) {
    desiredKeys.add(k);
  }

  const existingKeys = new Set<string>(g.nodes());

  // ---- Topology change check 2: bail if stub visibility flipped.
  // Easy proxy: if g has no stubs but the new payload's filter says we
  // want stubs (or vice-versa), the existing positions are useless for
  // the missing side. Rebuild handles the fan placement properly.
  let gHasStubs = false;
  g.forEachNode((_node, attrs) => {
    if (gHasStubs) return;
    const r = attrs.raw as GraphNode | undefined;
    if (r && isUncrawled(r)) gHasStubs = true;
  });
  // "Want stubs" tracks whether *any* uncrawled placeholder should be present,
  // honouring pins as well as the global toggle. Crossing the none↔some
  // boundary needs a rebuild (fan placement); set changes within "some" are
  // handled by the add/remove diff below.
  let wantStubs = false;
  for (const id of newStubIds) {
    if (uncrawledShown(id, opts)) { wantStubs = true; break; }
  }
  if (gHasStubs !== wantStubs && (gHasStubs || wantStubs)) return false;

  // ---- Diff sets.
  const toAdd: string[] = [];
  const toRemove: string[] = [];
  const toUpdate: string[] = [];
  let orphanAdded = false;
  for (const k of desiredKeys) {
    if (existingKeys.has(k)) toUpdate.push(k);
    else toAdd.push(k);
  }
  for (const k of existingKeys) {
    if (!desiredKeys.has(k)) toRemove.push(k);
  }

  // ---- Remove.
  for (const k of toRemove) g.dropNode(k);

  // ---- Add. Position heuristic:
  //   • Fetched non-stub: place at a same-domain sibling's (x, y) plus
  //     small jitter, so it joins its cluster visually instead of
  //     teleporting to the origin. If no sibling exists, fall back to
  //     a small random offset around (0, 0) — the next first-paint
  //     would have placed it via radialLayoutByDomain, which we can't
  //     re-run mid-session without disturbing every existing position.
  //   • Stub: position via haloOffset around its parent, using the
  //     count of existing same-parent stubs as the index so it joins
  //     the next slot of the halo.
  for (const k of toAdd) {
    if (isClusterKey(k)) return false; // shouldn't happen — topology check above
    const raw = newRawByKey.get(k);
    if (!raw) return false;
    let pos: { x: number; y: number } | null = null;

    if (isUncrawled(raw)) {
      // Stub parent might itself be collapsed — redirect to the cluster.
      const parentNumeric = newStubParent.get(raw.id);
      let parentKey: string | null = null;
      if (parentNumeric !== undefined) {
        const redirected = newMemberToCluster.get(parentNumeric);
        const candidate = redirected ?? String(parentNumeric);
        if (g.hasNode(candidate)) parentKey = candidate;
      }
      if (parentKey !== null) {
        const px = g.getNodeAttribute(parentKey, 'x') as number;
        const py = g.getNodeAttribute(parentKey, 'y') as number;
        // Count existing stubs with this parent to pick the next halo slot.
        let siblingCount = 0;
        g.forEachNode((_id, attrs) => {
          if ((attrs.parent_id as string | null) === parentKey) siblingCount++;
        });
        pos = haloOffset(px, py, siblingCount);
        g.addNode(k, {
          label: raw.label,
          x: pos.x,
          y: pos.y,
          size: nodeSize(raw.in_degree_count, raw.out_degree_count, raw.is_cluster, true),
          color: raw.color,
          raw,
          parent_id: parentKey,
        });
        continue;
      }
      // Orphan stub — seed anywhere; positionOrphanStubsOutside rings it
      // outside the crowd once the add pass finishes.
      orphanAdded = true;
      g.addNode(k, {
        label: raw.label,
        x: Math.random(),
        y: Math.random(),
        size: nodeSize(raw.in_degree_count, raw.out_degree_count, raw.is_cluster, true),
        color: raw.color,
        raw,
        parent_id: null,
      });
      continue;
    }

    // Fetched non-stub — look for a same-domain sibling in g.
    if (raw.domain) {
      g.forEachNode((_id, attrs) => {
        if (pos) return;
        const r = attrs.raw as GraphNode | undefined;
        if (!r || isUncrawled(r) || r.is_cluster) return;
        if (r.domain !== raw.domain) return;
        pos = {
          x: (attrs.x as number) + (Math.random() - 0.5) * NODE_SPACING,
          y: (attrs.y as number) + (Math.random() - 0.5) * NODE_SPACING,
        };
      });
    }
    if (!pos) pos = { x: Math.random(), y: Math.random() };
    g.addNode(k, {
      label: raw.label,
      x: pos.x,
      y: pos.y,
      size: nodeSize(raw.in_degree_count, raw.out_degree_count, raw.is_cluster, false),
      color: raw.color,
      raw,
    });
  }

  // A diff that introduced an edgeless pinned placeholder re-rings the
  // orphan set so the newcomer lands outside the crowd (and the others
  // re-settle into their deterministic slots). Pins normally arrive via a
  // full rebuild, so this is a rare path.
  if (orphanAdded) positionOrphanStubsOutside(g);

  // ---- Update attributes. x/y is never overwritten here — preserve both
  // the user's drags AND the existing layout's auto-positions.
  for (const k of toUpdate) {
    if (isClusterKey(k)) {
      const cluster = plan.clusters.get(k);
      if (!cluster) continue;
      const raw = cluster.raw;
      g.setNodeAttribute(k, 'label', raw.label);
      g.setNodeAttribute(
        k,
        'size',
        nodeSize(raw.in_degree_count, raw.out_degree_count, true, false),
      );
      g.setNodeAttribute(k, 'color', raw.color);
      g.setNodeAttribute(k, 'raw', raw);
      continue;
    }
    const raw = newRawByKey.get(k);
    if (!raw) continue;
    g.setNodeAttribute(k, 'label', raw.label);
    g.setNodeAttribute(
      k,
      'size',
      nodeSize(raw.in_degree_count, raw.out_degree_count, raw.is_cluster, isUncrawled(raw)),
    );
    g.setNodeAttribute(k, 'color', raw.color);
    g.setNodeAttribute(k, 'raw', raw);
  }

  // ---- Edge diff (same key + cluster-rewrite logic as rebuildInto).
  const desiredEdges = new Map<string, { from: string; to: string; raw: GraphEdge }>();
  for (const e of newPayload.edges) {
    const fromMember = newMemberToCluster.get(e.from);
    const toMember = newMemberToCluster.get(e.to);
    const from = fromMember ?? String(e.from);
    const to = toMember ?? String(e.to);
    if (from === to) continue;
    if (!g.hasNode(from) || !g.hasNode(to)) continue;
    const key =
      fromMember || toMember ? `${from}->${to}:cluster` : edgeKey(e);
    if (desiredEdges.has(key)) continue; // first wins, mirrors rebuildInto
    desiredEdges.set(key, { from, to, raw: e });
  }

  const existingEdgeKeys = new Set<string>(g.edges());
  for (const k of existingEdgeKeys) {
    if (!desiredEdges.has(k)) g.dropEdge(k);
  }
  for (const [k, { from, to, raw }] of desiredEdges) {
    if (g.hasEdge(k)) {
      g.setEdgeAttribute(k, 'raw', raw);
      g.setEdgeAttribute(
        k,
        'color',
        raw.source === 'analyst' ? '#00d4aa' : '#1a3a2a',
      );
      continue;
    }
    g.addEdgeWithKey(k, from, to, {
      size: 1,
      color: raw.source === 'analyst' ? '#00d4aa' : '#1a3a2a',
      type: 'arrow',
      raw,
    });
  }

  return true;
}
