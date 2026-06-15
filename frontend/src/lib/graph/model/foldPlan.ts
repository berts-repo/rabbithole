// Unified fold resolution (item 11, Phase 3d — D5/D6).
//
// One pass decides where every fetched page lands when several collapse axes
// are active at once. Two kinds of fold can claim a page: its domain
// (`clusterDomain`) or a label it carries (`clusterLabel`). A page can only sit
// in one folded node, so a single rule resolves the conflict:
//
//   Fold a page into the **highest-ranked collapsed label it carries**; if it
//   carries none and its domain is collapsed, fold it into the domain.
//
// `domain` is therefore the *floor* of one analyst-ranked list (D6): a `Scam`
// page inside a collapsed `NightMarket` is pulled into the `Scam` fold, and the
// domain fold just shows fewer pages. Label folds stay analytically complete,
// the safer default for OSINT. Overlap counts keep the loss visible (D5):
// `Scam · 12 pages (4 also Market)`.
//
// Pure — no runes, no graphology. Both `rebuildInto` and `applyDiff` build a
// plan from a payload + an options snapshot and route their node/edge/stub
// rewrites through it, so the two paths can never disagree on the fold shape.

import type { GraphNode } from '$lib/api';
import { isUncrawled } from '$lib/nodeState';
import { clusterKey, synthesizeClusterRaw } from './clusterDomain';
import {
  labelClusterKey,
  synthesizeLabelClusterRaw,
  type LabelClusterDef,
  type FoldOverlap,
} from './clusterLabel';

export type { LabelClusterDef };

export interface FoldOptions {
  // Global "group every multi-page site" toggle.
  groupByDomain: boolean;
  // Domains the analyst double-clicked open — an exception to *both* the global
  // toggle and a selective domain collapse.
  expandedDomains: ReadonlySet<string>;
  // Selective per-domain collapse (D7) — folds the chosen domain independent of
  // the global toggle.
  collapsedDomains: ReadonlySet<string>;
  // Collapse-by-label (D5), rank-ordered top-first (lowest `rank` number first).
  // The first entry a page carries is its fold home.
  collapsedLabels: readonly LabelClusterDef[];
}

export interface FoldCluster {
  // graphology node key — `cluster:<domain>` or `cluster:label:<id>`.
  key: string;
  kind: 'domain' | 'label';
  // The fetched pages resolved into this fold (after ranking — a domain fold
  // excludes members a higher-ranked label fold claimed).
  members: GraphNode[];
  // The aggregate node the collapsed view renders.
  raw: GraphNode;
}

export interface FoldPlan {
  // Folded page id → its fold's graphology key. Pages absent from this map
  // render as their own node.
  memberToCluster: Map<number, string>;
  // Fold key → its cluster entry. Empty folds (every member stolen by a
  // higher-ranked fold) are omitted.
  clusters: Map<string, FoldCluster>;
}

function push<K>(m: Map<K, GraphNode[]>, k: K, n: GraphNode): void {
  const b = m.get(k);
  if (b) b.push(n);
  else m.set(k, [n]);
}

// Members of a label fold that *also* carry a lower-ranked collapsed label —
// the overlap the fold's tooltip surfaces (D5). Ordered by rank, counts only.
function overlapsFor(
  homeLabelId: number,
  members: GraphNode[],
  order: readonly LabelClusterDef[],
): FoldOverlap[] {
  const counts = new Map<number, number>();
  for (const m of members) {
    const carried = new Set<number>([...m.label_ids, ...m.domain_label_ids]);
    for (const def of order) {
      if (def.id === homeLabelId) continue;
      if (carried.has(def.id)) counts.set(def.id, (counts.get(def.id) ?? 0) + 1);
    }
  }
  const out: FoldOverlap[] = [];
  for (const def of order) {
    if (def.id === homeLabelId) continue;
    const c = counts.get(def.id);
    if (c) out.push({ name: def.name, count: c });
  }
  return out;
}

export function planFolds(nodes: readonly GraphNode[], opts: FoldOptions): FoldPlan {
  const memberToCluster = new Map<number, string>();
  const clusters = new Map<string, FoldCluster>();

  // ---- Fetched pages, grouped by domain for the member-count test.
  const fetched: GraphNode[] = [];
  const byDomain = new Map<string, GraphNode[]>();
  for (const n of nodes) {
    if (isUncrawled(n)) continue;
    fetched.push(n);
    if (n.domain) push(byDomain, n.domain, n);
  }

  // ---- Which domains are collapsed. A domain folds iff it has > 1 fetched
  // member, the analyst hasn't expanded it, and either the global toggle is on
  // or it was selectively collapsed. A single-page "fold" is never useful.
  const collapsedDomains = new Set<string>();
  for (const [domain, members] of byDomain) {
    if (opts.expandedDomains.has(domain)) continue;
    if (members.length < 2) continue;
    if (opts.groupByDomain || opts.collapsedDomains.has(domain)) {
      collapsedDomains.add(domain);
    }
  }

  // ---- Collapsed-label lookup. `order` is rank-ascending, so the first entry
  // a page carries is the highest-ranked → its fold home.
  const order = opts.collapsedLabels;
  const defById = new Map<number, LabelClusterDef>(order.map((l) => [l.id, l]));

  // ---- Assign every fetched page to its fold home (label wins; domain floor).
  const labelMembers = new Map<number, GraphNode[]>();
  const domainMembers = new Map<string, GraphNode[]>();
  for (const n of fetched) {
    let homeLabel = -1;
    if (order.length > 0) {
      const carried = new Set<number>([...n.label_ids, ...n.domain_label_ids]);
      for (const def of order) {
        if (carried.has(def.id)) {
          homeLabel = def.id;
          break;
        }
      }
    }
    if (homeLabel !== -1) {
      memberToCluster.set(n.id, labelClusterKey(homeLabel));
      push(labelMembers, homeLabel, n);
      continue;
    }
    if (n.domain && collapsedDomains.has(n.domain)) {
      memberToCluster.set(n.id, clusterKey(n.domain));
      push(domainMembers, n.domain, n);
    }
  }

  // ---- Materialise folds. A collapsed domain whose every member was claimed
  // by a label fold yields no entry (nothing left to show).
  for (const [domain, members] of domainMembers) {
    const key = clusterKey(domain);
    clusters.set(key, { key, kind: 'domain', members, raw: synthesizeClusterRaw(domain, members) });
  }
  for (const [labelId, members] of labelMembers) {
    const def = defById.get(labelId);
    if (!def) continue;
    const key = labelClusterKey(labelId);
    const raw = synthesizeLabelClusterRaw(def, members, overlapsFor(labelId, members, order));
    clusters.set(key, { key, kind: 'label', members, raw });
  }

  return { memberToCluster, clusters };
}
