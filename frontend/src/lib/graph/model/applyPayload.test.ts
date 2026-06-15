import { describe, it, expect } from 'vitest';
import Graph from 'graphology';
import type { GraphNode, GraphEdge, GraphPayload } from '$lib/api';
import { rebuildInto, applyDiff, type ClusterFilterOptions } from './applyPayload';

// Minimal GraphNode fixture — overrides win over the fetched-page defaults.
function node(over: Partial<GraphNode> = {}): GraphNode {
  return {
    id: 1,
    label: 'page',
    alias: null,
    title_text: 'page',
    raw_url: 'http://x.onion/',
    color: '#abc',
    domain: 'x.onion',
    network: 'tor',
    depth: 0,
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

function edge(over: Partial<GraphEdge> = {}): GraphEdge {
  return { from: 1, to: 2, source: 'crawl', label: null, ...over };
}

function payload(nodes: GraphNode[], edges: GraphEdge[] = []): GraphPayload {
  return { nodes, edges };
}

// Default filter snapshot: uncrawled visible, no domain clustering, nothing
// expanded — the steady state the store hands the apply paths.
function opts(over: Partial<ClusterFilterOptions> = {}): ClusterFilterOptions {
  return {
    showUncrawled: true,
    groupByDomain: false,
    expandedDomains: new Set<string>(),
    pinnedIds: new Set<number>(),
    collapsedDomains: new Set<string>(),
    collapsedLabels: [],
    ...over,
  };
}

// Matches the store's single stable instance: directed, no parallel edges.
function newGraph(): Graph {
  return new Graph({ type: 'directed', multi: false });
}

describe('rebuildInto', () => {
  it('builds a node-and-edge graph from a flat payload', () => {
    const g = newGraph();
    rebuildInto(
      g,
      payload([node({ id: 1 }), node({ id: 2 })], [edge({ from: 1, to: 2 })]),
      opts(),
    );
    expect(g.order).toBe(2);
    expect(g.size).toBe(1);
    expect(g.hasNode('1')).toBe(true);
    expect(g.hasNode('2')).toBe(true);
  });

  it('collapses a multi-member domain into one cluster node', () => {
    const g = newGraph();
    rebuildInto(
      g,
      payload([
        node({ id: 1, domain: 'a.onion' }),
        node({ id: 2, domain: 'a.onion' }),
        node({ id: 3, domain: 'b.onion' }),
      ]),
      opts({ groupByDomain: true }),
    );
    // a.onion (2 members) folds into cluster:a.onion; b.onion (1) stays.
    expect(g.order).toBe(2);
    expect(g.hasNode('cluster:a.onion')).toBe(true);
    expect(g.hasNode('1')).toBe(false);
    expect(g.hasNode('2')).toBe(false);
    expect(g.hasNode('3')).toBe(true);
    expect((g.getNodeAttribute('cluster:a.onion', 'raw') as GraphNode).is_cluster).toBe(true);
  });

  it('halos an uncrawled node around its discovering parent when uncrawled shown', () => {
    const g = newGraph();
    rebuildInto(
      g,
      payload(
        [node({ id: 1 }), node({ id: 2, state: 'known' })],
        [edge({ from: 1, to: 2 })],
      ),
      opts(),
    );
    expect(g.hasNode('2')).toBe(true);
    expect(g.getNodeAttribute('2', 'parent_id')).toBe('1');
  });

  it('drops uncrawled nodes entirely when showUncrawled is off', () => {
    const g = newGraph();
    rebuildInto(
      g,
      payload(
        [node({ id: 1 }), node({ id: 2, state: 'known' })],
        [edge({ from: 1, to: 2 })],
      ),
      opts({ showUncrawled: false }),
    );
    expect(g.order).toBe(1);
    expect(g.hasNode('2')).toBe(false);
  });

  it('includes a pinned uncrawled node while showUncrawled is off, and only that one', () => {
    const g = newGraph();
    rebuildInto(
      g,
      payload([
        node({ id: 1 }),
        node({ id: 2, state: 'known' }), // pinned → shown
        node({ id: 3, state: 'known' }), // not pinned → stays hidden
      ]),
      opts({ showUncrawled: false, pinnedIds: new Set([2]) }),
    );
    expect(g.hasNode('1')).toBe(true);
    expect(g.hasNode('2')).toBe(true);
    expect(g.hasNode('3')).toBe(false);
  });

  it('applyDiff lands a newly-pinned uncrawled node without a rebuild', () => {
    const g = newGraph();
    // Start with the crawled node only — uncrawled hidden, none pinned.
    rebuildInto(
      g,
      payload([node({ id: 1 }), node({ id: 2, state: 'known' })]),
      opts({ showUncrawled: false }),
    );
    expect(g.hasNode('2')).toBe(false);
    // Pin id 2: still showUncrawled off, but the pin pulls it in. gHasStubs
    // was false and now one stub is wanted → crosses the boundary → rebuild.
    const landed = applyDiff(
      g,
      payload([node({ id: 1 }), node({ id: 2, state: 'known' })]),
      opts({ showUncrawled: false, pinnedIds: new Set([2]) }),
    );
    expect(landed).toBe(false); // boundary cross → caller rebuilds
  });

  it('rewrites cross-cluster edges and drops same-cluster self-loops', () => {
    const g = newGraph();
    rebuildInto(
      g,
      payload(
        [
          node({ id: 1, domain: 'a.onion' }),
          node({ id: 2, domain: 'a.onion' }),
          node({ id: 3, domain: 'b.onion' }),
        ],
        [
          edge({ from: 1, to: 2 }), // both in a.onion → self-loop, dropped
          edge({ from: 1, to: 3 }), // a.onion → b.onion → rewritten
        ],
      ),
      opts({ groupByDomain: true }),
    );
    expect(g.size).toBe(1);
    expect(g.hasEdge('cluster:a.onion->3:cluster')).toBe(true);
  });

  it('selective domain collapse folds one domain without the global toggle', () => {
    const g = newGraph();
    rebuildInto(
      g,
      payload([
        node({ id: 1, domain: 'a.onion' }),
        node({ id: 2, domain: 'a.onion' }),
        node({ id: 3, domain: 'b.onion' }),
        node({ id: 4, domain: 'b.onion' }),
      ]),
      opts({ collapsedDomains: new Set(['a.onion']) }),
    );
    expect(g.hasNode('cluster:a.onion')).toBe(true);
    expect(g.hasNode('1')).toBe(false); // folded
    expect(g.hasNode('3')).toBe(true); // b.onion not selected
    expect(g.hasNode('4')).toBe(true);
  });

  it('collapse-by-label folds carriers across domains into one node', () => {
    const g = newGraph();
    rebuildInto(
      g,
      payload([
        node({ id: 1, domain: 'a.onion', label_ids: [5] }),
        node({ id: 2, domain: 'b.onion', label_ids: [5] }),
        node({ id: 3, domain: 'c.onion' }),
      ]),
      opts({ collapsedLabels: [{ id: 5, name: 'Scam', color: '#f00' }] }),
    );
    expect(g.hasNode('cluster:label:5')).toBe(true);
    expect(g.hasNode('1')).toBe(false);
    expect(g.hasNode('2')).toBe(false);
    expect(g.hasNode('3')).toBe(true);
    expect(g.getNodeAttribute('cluster:label:5', 'color')).toBe('#f00');
  });

  it('a labeled page in a collapsed domain lands in the label fold (D6)', () => {
    const g = newGraph();
    rebuildInto(
      g,
      payload([
        node({ id: 1, domain: 'a.onion', label_ids: [5] }),
        node({ id: 2, domain: 'a.onion' }),
        node({ id: 3, domain: 'a.onion' }),
      ]),
      opts({ collapsedDomains: new Set(['a.onion']), collapsedLabels: [{ id: 5, name: 'Scam', color: '#f00' }] }),
    );
    expect(g.hasNode('cluster:label:5')).toBe(true);
    expect(g.hasNode('cluster:a.onion')).toBe(true);
    // node 1 → label fold; 2 & 3 → domain fold.
    expect(g.hasNode('1')).toBe(false);
    expect(g.hasNode('2')).toBe(false);
  });
});

describe('applyDiff', () => {
  it('adds a node that appeared in the new payload', () => {
    const g = newGraph();
    rebuildInto(g, payload([node({ id: 1 })]), opts());
    const landed = applyDiff(g, payload([node({ id: 1 }), node({ id: 2 })]), opts());
    expect(landed).toBe(true);
    expect(g.hasNode('2')).toBe(true);
  });

  it('removes a node that vanished from the new payload', () => {
    const g = newGraph();
    rebuildInto(g, payload([node({ id: 1 }), node({ id: 2 })]), opts());
    const landed = applyDiff(g, payload([node({ id: 1 })]), opts());
    expect(landed).toBe(true);
    expect(g.hasNode('2')).toBe(false);
  });

  it('updates attributes on a node that stayed', () => {
    const g = newGraph();
    rebuildInto(g, payload([node({ id: 1, label: 'old' })]), opts());
    const landed = applyDiff(g, payload([node({ id: 1, label: 'new' })]), opts());
    expect(landed).toBe(true);
    expect(g.getNodeAttribute('1', 'label')).toBe('new');
  });

  it('adds and removes edges to match the new payload', () => {
    const g = newGraph();
    rebuildInto(g, payload([node({ id: 1 }), node({ id: 2 })]), opts());
    expect(g.size).toBe(0);

    applyDiff(g, payload([node({ id: 1 }), node({ id: 2 })], [edge({ from: 1, to: 2 })]), opts());
    expect(g.size).toBe(1);

    applyDiff(g, payload([node({ id: 1 }), node({ id: 2 })]), opts());
    expect(g.size).toBe(0);
  });

  it('bails (false) when the cluster topology would change', () => {
    const g = newGraph();
    const nodes = [
      node({ id: 1, domain: 'a.onion' }),
      node({ id: 2, domain: 'a.onion' }),
    ];
    // Built with no clustering — g has no cluster node.
    rebuildInto(g, payload(nodes), opts({ groupByDomain: false }));
    // New filters would collapse a.onion → topology change → rebuild.
    const landed = applyDiff(g, payload(nodes), opts({ groupByDomain: true }));
    expect(landed).toBe(false);
  });

  it('bails (false) when uncrawled visibility flipped', () => {
    const g = newGraph();
    const p = payload(
      [node({ id: 1 }), node({ id: 2, state: 'known' })],
      [edge({ from: 1, to: 2 })],
    );
    // Built with uncrawled visible.
    rebuildInto(g, p, opts({ showUncrawled: true }));
    expect(g.hasNode('2')).toBe(true);
    // New filters hide uncrawled → existing positions useless → rebuild.
    const landed = applyDiff(g, p, opts({ showUncrawled: false }));
    expect(landed).toBe(false);
  });

  it('preserves x/y on a node across an attribute-only diff', () => {
    const g = newGraph();
    rebuildInto(g, payload([node({ id: 1 }), node({ id: 2 })]), opts());
    g.setNodeAttribute('1', 'x', 123);
    g.setNodeAttribute('1', 'y', 456);
    const landed = applyDiff(
      g,
      payload([node({ id: 1, label: 'moved-label' }), node({ id: 2 })]),
      opts(),
    );
    expect(landed).toBe(true);
    expect(g.getNodeAttribute('1', 'x')).toBe(123);
    expect(g.getNodeAttribute('1', 'y')).toBe(456);
    expect(g.getNodeAttribute('1', 'label')).toBe('moved-label');
  });
});
