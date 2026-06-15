// Label-cluster identity and synthesis (item 11, Phase 3d — collapse-by-label).
//
// Parallel to `clusterDomain.ts`, but the fold axis is a *label* rather than a
// domain: when a label is collapsed, every fetched page carrying that label —
// across domains — folds into one synthetic node keyed `cluster:label:<id>`,
// named by the label and coloured by its swatch. Which page lands in which
// fold when it carries several collapsed labels is decided upstream by the
// unified D5/D6 resolution in `foldPlan.ts`; this module only owns the key
// scheme and the aggregate `GraphNode` the collapsed view renders.
//
// Key-scheme note: a label-cluster key starts with `cluster:` too, so it also
// satisfies `clusterDomain.isClusterKey`. Any decode path must therefore test
// `isLabelClusterKey` *first* and only treat the remainder as a host when it is
// not a label key.

import type { GraphNode } from '$lib/api';

const LABEL_CLUSTER_PREFIX = 'cluster:label:';

// A collapsed label's display identity — the subset of the catalog `Label`
// the fold node needs. Keeps this module decoupled from the full API shape.
export interface LabelClusterDef {
  id: number;
  name: string;
  color: string | null;
}

// An overlap line for the fold's tooltip: N members of this fold *also* carry
// a lower-ranked collapsed group (another label, or their collapsed domain).
export interface FoldOverlap {
  name: string;
  count: number;
}

export function isLabelClusterKey(k: string | number | null | undefined): boolean {
  return typeof k === 'string' && k.startsWith(LABEL_CLUSTER_PREFIX);
}

export function labelClusterKey(labelId: number): string {
  return `${LABEL_CLUSTER_PREFIX}${labelId}`;
}

export function labelClusterId(k: string): number {
  return Number(k.slice(LABEL_CLUSTER_PREFIX.length));
}

// Deterministic negative synthetic id for a label fold, mirroring the domain
// scheme so a label cluster never collides with a real DB id (positive). The
// graphology *key* is the real identity downstream; this id only feeds display
// and the `Number(node)` "is this a real node?" checks, which want it invalid.
function hashLabelKey(labelId: number): number {
  const key = labelClusterKey(labelId);
  let h = 0;
  for (let i = 0; i < key.length; i++) {
    h = (h * 31 + key.charCodeAt(i)) | 0;
  }
  return -(Math.abs(h) % 0x7fffffff || 1);
}

export function synthesizeLabelClusterRaw(
  label: LabelClusterDef,
  members: GraphNode[],
  overlaps: FoldOverlap[] = [],
): GraphNode {
  // Highest-priority active flag wins for the overlay — same precedence as the
  // domain fold (investigating > pending > done/dismissed = no overlay).
  let flag: string | null = null;
  for (const m of members) {
    if (m.flag_status === 'investigating') {
      flag = 'investigating';
      break;
    }
    if (m.flag_status === 'pending' && flag !== 'investigating') flag = 'pending';
  }
  let inDeg = 0;
  let outDeg = 0;
  for (const m of members) {
    inDeg += m.in_degree_count;
    outDeg += m.out_degree_count;
  }
  // Overlap suffix keeps nothing silently swallowed (D5): "Scam · 12 pages
  // (4 also Market)". Empty when no member doubles into a lower-ranked fold.
  const overlapText =
    overlaps.length > 0
      ? ` (${overlaps.map((o) => `${o.count} also ${o.name}`).join(', ')})`
      : '';
  return {
    id: hashLabelKey(label.id),
    label: label.name,
    alias: null,
    title_text: `${label.name} — ${members.length} pages${overlapText} (double-click to expand)`,
    raw_url: '',
    // The label swatch is the cluster's tone in every non-derived colour mode;
    // colour-by-label resolves the same swatch via `label_ids` below.
    color: label.color ?? members[0]?.color ?? '#3a5a4d',
    // Cross-domain by construction — a label fold has no single host.
    domain: null,
    // A label fold can span networks; take the representative member's network
    // (as with colour above). 'network' colour mode is not the natural view for
    // a label fold, so a representative value is sufficient.
    network: members[0]?.network ?? 'tor',
    depth: null,
    flag_status: flag,
    is_bridge: false,
    betweenness: 0,
    pagerank: 0,
    cluster_id: null,
    infra_cluster_id: null,
    first_seen: null,
    is_cluster: true,
    state: 'crawled',
    analysis_excluded: false,
    reviewed: false,
    category: null,
    in_degree_count: inDeg,
    out_degree_count: outDeg,
    // Carry the fold's own label so colour-by-label paints it with the label's
    // swatch (dominantLabelColor resolves [label.id] → its colour). Members
    // keep their own labels; this is the aggregate's identity, not theirs.
    label_ids: [label.id],
    domain_label_ids: [],
  };
}
