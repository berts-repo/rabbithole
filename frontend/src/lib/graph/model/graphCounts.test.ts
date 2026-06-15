import { describe, it, expect } from 'vitest';
import Graph from 'graphology';
import type { GraphNode, GraphPayload, ResourceState } from '$lib/api';
import { deriveScopeCounts, deriveStructuralCounts } from './graphCounts';

// Build a directed graph with `nodes` nodes (keyed '0'..'n-1') and the
// given directed edges.
function graphWith(nodes: number, edges: [number, number][]): Graph {
  const g = new Graph({ type: 'directed', multi: false });
  for (let i = 0; i < nodes; i++) g.addNode(String(i));
  for (const [a, b] of edges) g.addEdge(String(a), String(b));
  return g;
}

describe('deriveStructuralCounts', () => {
  it('reports graphology order and size as the structural counts', () => {
    const c = deriveStructuralCounts(graphWith(3, [[0, 1], [1, 2]]));
    expect(c.nodeCount).toBe(3);
    expect(c.edgeCount).toBe(2);
  });

  it('defaults visible counts equal to the structural counts', () => {
    const c = deriveStructuralCounts(graphWith(4, [[0, 1]]));
    expect(c.visibleNodeCount).toBe(c.nodeCount);
    expect(c.visibleEdgeCount).toBe(c.edgeCount);
    expect(c.visibleNodeCount).toBe(4);
    expect(c.visibleEdgeCount).toBe(1);
  });

  it('reports zeros for an empty graph', () => {
    expect(deriveStructuralCounts(new Graph())).toEqual({
      nodeCount: 0,
      edgeCount: 0,
      visibleNodeCount: 0,
      visibleEdgeCount: 0,
    });
  });
});

// Minimal node factory — only the fields deriveScopeCounts reads matter;
// the rest are filled with inert defaults so the GraphNode type is satisfied.
function node(state: ResourceState, domain: string | null): GraphNode {
  return {
    id: 0,
    label: '',
    alias: null,
    title_text: '',
    raw_url: '',
    color: '',
    domain,
    network: 'tor',
    depth: null,
    flag_status: null,
    is_bridge: false,
    betweenness: 0,
    pagerank: 0,
    cluster_id: null,
    infra_cluster_id: null,
    first_seen: null,
    is_cluster: false,
    state,
    analysis_excluded: false,
    reviewed: false,
    category: null,
    in_degree_count: 0,
    out_degree_count: 0,
    label_ids: [],
    domain_label_ids: [],
  };
}

function payload(nodes: GraphNode[]): GraphPayload {
  return { nodes, edges: [] };
}

describe('deriveScopeCounts', () => {
  it('counts crawled nodes as pages and their distinct hosts as domains', () => {
    const c = deriveScopeCounts(
      payload([
        node('crawled', 'a.onion'),
        node('crawled', 'a.onion'),
        node('crawled', 'b.onion'),
      ]),
    );
    expect(c.pages).toBe(3);
    expect(c.domains).toBe(2);
  });

  it('ignores non-crawled nodes (known / unknown / dead)', () => {
    const c = deriveScopeCounts(
      payload([
        node('crawled', 'a.onion'),
        node('known', 'b.onion'),
        node('unknown', 'c.onion'),
        node('dead', 'd.onion'),
      ]),
    );
    expect(c.pages).toBe(1);
    expect(c.domains).toBe(1);
  });

  it('does not count a null host toward domains', () => {
    const c = deriveScopeCounts(
      payload([node('crawled', null), node('crawled', 'a.onion')]),
    );
    expect(c.pages).toBe(2);
    expect(c.domains).toBe(1);
  });

  it('returns zeros for a null payload', () => {
    expect(deriveScopeCounts(null)).toEqual({ domains: 0, pages: 0 });
  });
});
