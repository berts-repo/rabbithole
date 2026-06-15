// Structural count derivation for the toolbar status line.
//
// `deriveStructuralCounts` reads the graphology instance's order/size —
// the counts that hold after structural filtering (stub toggle, domain
// clustering), before F4b's reducer-time visual filters run. `visible*`
// default equal to the structural counts; the canvas overwrites them a
// tick later via `graphStore.setVisibleCounts` once reducer-time
// visibility is computed. The store calls this instead of reading
// `graphInstance.order` / `.size` inline so the derivation lives in one
// pure, testable place.

import type Graph from 'graphology';
import type { GraphPayload } from '$lib/api';

export interface StructuralCounts {
  nodeCount: number;
  edgeCount: number;
  visibleNodeCount: number;
  visibleEdgeCount: number;
}

export function deriveStructuralCounts(g: Graph): StructuralCounts {
  const nodeCount = g.order;
  const edgeCount = g.size;
  return {
    nodeCount,
    edgeCount,
    visibleNodeCount: nodeCount,
    visibleEdgeCount: edgeCount,
  };
}

export interface ScopeCounts {
  domains: number;
  pages: number;
}

// Workspace-scoped domain/page totals for the tab-bar status line. Mirrors
// the backend's /api/stats semantics (backend/db/stats.py): a "page" is a
// crawled resource; "domains" is the distinct host count over those crawled
// resources. Derived from the raw payload — independent of the client-side
// view filters (stub toggle, domain clustering) — so the number reflects the
// active workspace's true scale, not the current visualisation.
export function deriveScopeCounts(payload: GraphPayload | null): ScopeCounts {
  if (!payload) return { domains: 0, pages: 0 };
  let pages = 0;
  const hosts = new Set<string>();
  for (const node of payload.nodes) {
    if (node.state !== 'crawled') continue;
    pages += 1;
    if (node.domain) hosts.add(node.domain);
  }
  return { domains: hosts.size, pages };
}
