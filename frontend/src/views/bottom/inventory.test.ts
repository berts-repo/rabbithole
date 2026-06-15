import { describe, it, expect } from 'vitest';
import { inducedSubgraph, summarize, domainsInGraph } from './inventory';
import type { GraphNode, GraphEdge, GraphPayload } from '$lib/api';

// Minimal GraphNode factory — only the fields the inventory helpers read.
function node(over: Partial<GraphNode>): GraphNode {
  return {
    id: 0,
    label: '',
    alias: null,
    title_text: '',
    raw_url: '',
    color: '#fff',
    domain: null,
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
    state: 'crawled',
    analysis_excluded: false,
    reviewed: false,
    category: null,
    in_degree_count: 0,
    out_degree_count: 0,
    label_ids: [],
    domain_label_ids: [],
    ...over,
  };
}

function edge(from: number, to: number): GraphEdge {
  return { from, to, source: 'link', label: null };
}

describe('summarize', () => {
  it('zeroes everything for an empty graph', () => {
    expect(summarize([], [])).toEqual({
      nodes: 0,
      edges: 0,
      crawled: 0,
      uncrawled: 0,
      flagged: 0,
      reviewed: 0,
      categorized: 0,
      bridges: 0,
    });
  });

  it('counts crawled/uncrawled, flags, reviewed, categorized, bridges', () => {
    const nodes = [
      node({ id: 1, state: 'crawled', flag_status: 'suspicious', reviewed: true }),
      node({ id: 2, state: 'known' }), // uncrawled stub
      node({ id: 3, state: 'crawled', category: 'market', is_bridge: true }),
      node({ id: 4, state: 'crawled', flag_status: 'none' }), // sentinel = not flagged
      node({ id: 5, state: 'crawled', category: '   ' }), // whitespace = not categorized
    ];
    const edges = [edge(1, 2), edge(2, 3)];
    expect(summarize(nodes, edges)).toEqual({
      nodes: 5,
      edges: 2,
      crawled: 4,
      uncrawled: 1,
      flagged: 1,
      reviewed: 1,
      categorized: 1,
      bridges: 1,
    });
  });

  it('excludes synthetic cluster nodes from node counts', () => {
    const nodes = [
      node({ id: 1, domain: 'a.onion' }),
      node({ id: 2, is_cluster: true, domain: 'a.onion', flag_status: 'x' }),
    ];
    const s = summarize(nodes, []);
    expect(s.nodes).toBe(1);
    expect(s.flagged).toBe(0);
  });
});

describe('inducedSubgraph', () => {
  it('keeps matching nodes and drops edges with an endpoint outside the set', () => {
    const payload: GraphPayload = {
      nodes: [
        node({ id: 1, domain: 'a.onion' }),
        node({ id: 2, domain: 'a.onion' }),
        node({ id: 3, domain: 'b.onion' }),
      ],
      edges: [edge(1, 2), edge(2, 3), edge(3, 1)],
    };
    const { nodes, edges } = inducedSubgraph(payload, (n) => n.domain === 'a.onion');
    expect(nodes.map((n) => n.id)).toEqual([1, 2]);
    // 1→2 survives; 2→3 and 3→1 cross out of the set and are dropped.
    expect(edges).toEqual([edge(1, 2)]);
  });
});

describe('domainsInGraph', () => {
  it('groups by host, sorts by count desc then host asc, skips null/cluster', () => {
    const nodes = [
      node({ id: 1, domain: 'b.onion', flag_status: 'x' }),
      node({ id: 2, domain: 'b.onion' }),
      node({ id: 3, domain: 'a.onion' }),
      node({ id: 4, domain: 'c.onion' }),
      node({ id: 5, domain: null }), // skipped
      node({ id: 6, is_cluster: true, domain: 'b.onion' }), // skipped
    ];
    expect(domainsInGraph(nodes)).toEqual([
      { host: 'b.onion', count: 2, flagged: 1 },
      { host: 'a.onion', count: 1, flagged: 0 },
      { host: 'c.onion', count: 1, flagged: 0 },
    ]);
  });
});
