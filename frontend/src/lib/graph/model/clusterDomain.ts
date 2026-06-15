// Domain-cluster identity and synthesis.
//
// When `graphFiltersStore.groupByDomain` is on, every domain with > 1
// fetched member that isn't expanded is collapsed into a single synthetic
// cluster node keyed `cluster:<domain>`. This module owns the cluster key
// scheme (mint / detect / decode) and `synthesizeClusterRaw`, the
// aggregate `GraphNode` the collapsed view renders. Clustering is purely
// client-side — the backend always serves `is_cluster: false` (see
// backend/backend/db/graph.py:232).

import type { GraphNode } from '$lib/api';

const CLUSTER_PREFIX = 'cluster:';

export function isClusterKey(k: string | number | null | undefined): boolean {
  return typeof k === 'string' && k.startsWith(CLUSTER_PREFIX);
}

export function clusterKey(domain: string): string {
  return `${CLUSTER_PREFIX}${domain}`;
}

export function clusterDomain(k: string): string {
  return k.slice(CLUSTER_PREFIX.length);
}

// Deterministic 31-bit positive hash from a domain string. Used to mint
// a stable synthetic numeric id for cluster nodes; the negative of this
// hash is what `raw.id` exposes downstream so clusters never collide
// with real DB ids (positive integers).
function hashDomain(domain: string): number {
  let h = 0;
  for (let i = 0; i < domain.length; i++) {
    h = (h * 31 + domain.charCodeAt(i)) | 0;
  }
  // Force a stable positive 31-bit range, then flip sign so downstream
  // `Number(node)` callers see a recognisably-invalid id.
  return -(Math.abs(h) % 0x7fffffff || 1);
}

export function synthesizeClusterRaw(
  domain: string,
  members: GraphNode[],
): GraphNode {
  // Highest-priority active flag wins for the overlay — same precedence
  // backend uses for join. Order: investigating > pending > done > null.
  // 'dismissed' is treated as no overlay so it doesn't bleed visible on
  // an aggregate.
  let flag: string | null = null;
  for (const m of members) {
    if (m.flag_status === 'investigating') {
      flag = 'investigating';
      break;
    }
    if (m.flag_status === 'pending' && flag !== 'investigating') flag = 'pending';
  }
  // Sum degrees so the cluster's tooltip and any downstream metric reads
  // line up with "this represents the aggregate of N pages". The reducer
  // size for `is_cluster: true` is fixed at 12 (see nodeSize) so degrees
  // do not feed the visual.
  let inDeg = 0;
  let outDeg = 0;
  for (const m of members) {
    inDeg += m.in_degree_count;
    outDeg += m.out_degree_count;
  }
  // Use the first member's color for the cluster — in 'domain' colour
  // mode the backend already serves one canonical tone per domain so all
  // members carry the same value. Other colour modes derive at reducer
  // time from raw fields below.
  const head = members[0];
  // Alias-aware fold (D7): the backend serves the *domain* alias on every
  // node's `alias` (graph.py builds `alias = alias_by_domain.get(domain)`), so
  // all members of one domain carry the same value. Show the alias when set —
  // collapsing under a rename is half of what "collapse by a rename" means —
  // and fall back to the bare host otherwise.
  const alias = head?.alias ?? null;
  const display = alias ?? domain;
  return {
    id: hashDomain(domain),
    label: display,
    alias,
    title_text: `${display} — ${members.length} pages (double-click to expand)`,
    raw_url: '',
    color: head.color,
    domain,
    // All members of one domain share a network (the .onion/.i2p suffix is
    // uniform within a host), so the head's value is the domain's network —
    // this keeps a folded domain coloured correctly in 'network' mode.
    network: head.network,
    depth: null,
    flag_status: flag,
    is_bridge: false,
    betweenness: 0,
    pagerank: 0,
    cluster_id: head.cluster_id,
    infra_cluster_id: head.infra_cluster_id,
    first_seen: null,
    is_cluster: true,
    state: 'crawled',
    analysis_excluded: false,
    reviewed: false,
    category: head.category,
    in_degree_count: inDeg,
    out_degree_count: outDeg,
    // A synthetic fold node carries no labels of its own; collapse-by-label
    // (Phase 3) is a separate cluster kind. Members keep their own labels.
    label_ids: [],
    domain_label_ids: [],
  };
}
