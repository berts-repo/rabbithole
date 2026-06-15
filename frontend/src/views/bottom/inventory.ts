// Pure helpers for the Inventory tab — a read-only survey of what's loaded
// into the current workspace (item 5, inventory-tab.md). Kept runtime-free so
// vitest covers it without the Svelte runtime: the component resolves the
// active scope (global / collection payload, or a NodeSet tab's induced
// subgraph) and hands these functions plain node/edge arrays.

import type { GraphNode, GraphEdge, GraphPayload } from '$lib/api';
import { isUncrawled } from '$lib/nodeState';

export interface InventorySummary {
  nodes: number;
  edges: number;
  // crawled = real fetched pages; uncrawled = stub link-targets not yet
  // crawled. The three-way split with `dead` waits on the schema reset (item
  // 6); see decisions.md.
  crawled: number;
  uncrawled: number;
  flagged: number;
  reviewed: number;
  // LLM analysis category present — the available proxy for "analysis
  // completed". Distinct from analyst labels (item 11).
  categorized: number;
  bridges: number;
}

export interface DomainCount {
  host: string;
  count: number;
  flagged: number;
}

// A node carries an *active* flag when flag_status is a non-empty string other
// than the sentinel 'none'. Mirrors how the Domains/Flags surfaces read it.
function isFlagged(n: GraphNode): boolean {
  const s = n.flag_status;
  return !!s && s !== 'none';
}

/**
 * Induced subgraph: the nodes passing `keep`, plus only the edges whose *both*
 * endpoints survive — the same rule NodeSet tabs use (list-to-graph-tabs.md).
 * Used to make the inventory reflect the active NodeSet tab's rendered scope.
 */
export function inducedSubgraph(
  payload: GraphPayload,
  keep: (n: GraphNode) => boolean,
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes = payload.nodes.filter(keep);
  const kept = new Set(nodes.map((n) => n.id));
  const edges = payload.edges.filter((e) => kept.has(e.from) && kept.has(e.to));
  return { nodes, edges };
}

/** Aggregate counts over the scoped node/edge arrays. */
export function summarize(nodes: GraphNode[], edges: GraphEdge[]): InventorySummary {
  const summary: InventorySummary = {
    nodes: 0,
    edges: edges.length,
    crawled: 0,
    uncrawled: 0,
    flagged: 0,
    reviewed: 0,
    categorized: 0,
    bridges: 0,
  };
  for (const n of nodes) {
    // Synthetic cluster nodes are a client-side render concern, not real
    // resources — exclude them from every count.
    if (n.is_cluster) continue;
    summary.nodes++;
    if (isUncrawled(n)) summary.uncrawled++;
    else summary.crawled++;
    if (isFlagged(n)) summary.flagged++;
    if (n.reviewed) summary.reviewed++;
    if (n.category && n.category.trim()) summary.categorized++;
    if (n.is_bridge) summary.bridges++;
  }
  return summary;
}

/**
 * Distinct hosts in the scoped graph, sorted by node count desc then host asc.
 * Skips null-domain and synthetic cluster nodes. `flagged` is the per-host
 * count of nodes carrying an active flag.
 */
export function domainsInGraph(nodes: GraphNode[]): DomainCount[] {
  const map = new Map<string, DomainCount>();
  for (const n of nodes) {
    if (n.is_cluster) continue;
    const host = n.domain;
    if (!host) continue;
    let row = map.get(host);
    if (!row) {
      row = { host, count: 0, flagged: 0 };
      map.set(host, row);
    }
    row.count++;
    if (isFlagged(n)) row.flagged++;
  }
  return [...map.values()].sort((a, b) =>
    a.count === b.count ? (a.host < b.host ? -1 : a.host > b.host ? 1 : 0) : b.count - a.count,
  );
}
