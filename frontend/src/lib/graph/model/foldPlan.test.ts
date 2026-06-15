import { describe, it, expect } from 'vitest';
import type { GraphNode } from '$lib/api';
import { planFolds, type FoldOptions } from './foldPlan';
import { clusterKey } from './clusterDomain';
import { labelClusterKey } from './clusterLabel';

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

// Rank-ascending defs (top first): Scam outranks Market outranks Forum.
const SCAM = { id: 5, name: 'Scam', color: '#f00' };
const MARKET = { id: 6, name: 'Market', color: '#0f0' };
const FORUM = { id: 7, name: 'Forum', color: '#00f' };

function opts(over: Partial<FoldOptions> = {}): FoldOptions {
  return {
    groupByDomain: false,
    expandedDomains: new Set(),
    collapsedDomains: new Set(),
    collapsedLabels: [],
    ...over,
  };
}

describe('planFolds — domain collapse', () => {
  it('folds a multi-page domain under groupByDomain', () => {
    const nodes = [node({ id: 1 }), node({ id: 2 }), node({ id: 3, domain: 'y.onion' })];
    const plan = planFolds(nodes, opts({ groupByDomain: true }));
    expect(plan.memberToCluster.get(1)).toBe(clusterKey('x.onion'));
    expect(plan.memberToCluster.get(2)).toBe(clusterKey('x.onion'));
    // y.onion has a single member — never folds.
    expect(plan.memberToCluster.has(3)).toBe(false);
    expect(plan.clusters.get(clusterKey('x.onion'))?.members).toHaveLength(2);
  });

  it('selective collapse folds one domain without the global toggle', () => {
    const nodes = [
      node({ id: 1, domain: 'x.onion' }),
      node({ id: 2, domain: 'x.onion' }),
      node({ id: 3, domain: 'y.onion' }),
      node({ id: 4, domain: 'y.onion' }),
    ];
    const plan = planFolds(nodes, opts({ collapsedDomains: new Set(['x.onion']) }));
    expect(plan.memberToCluster.get(1)).toBe(clusterKey('x.onion'));
    expect(plan.memberToCluster.has(3)).toBe(false); // y.onion not selected
  });

  it('expandedDomains overrides both global and selective collapse', () => {
    const nodes = [node({ id: 1 }), node({ id: 2 })];
    const plan = planFolds(
      nodes,
      opts({ groupByDomain: true, collapsedDomains: new Set(['x.onion']), expandedDomains: new Set(['x.onion']) }),
    );
    expect(plan.clusters.size).toBe(0);
  });
});

describe('planFolds — label collapse', () => {
  it('folds pages carrying a collapsed label across domains', () => {
    const nodes = [
      node({ id: 1, domain: 'x.onion', label_ids: [SCAM.id] }),
      node({ id: 2, domain: 'y.onion', label_ids: [SCAM.id] }),
      node({ id: 3, domain: 'z.onion' }),
    ];
    const plan = planFolds(nodes, opts({ collapsedLabels: [SCAM] }));
    expect(plan.memberToCluster.get(1)).toBe(labelClusterKey(SCAM.id));
    expect(plan.memberToCluster.get(2)).toBe(labelClusterKey(SCAM.id));
    expect(plan.memberToCluster.has(3)).toBe(false);
    expect(plan.clusters.get(labelClusterKey(SCAM.id))?.members).toHaveLength(2);
  });

  it('counts a via-domain label as carried', () => {
    const nodes = [node({ id: 1, domain_label_ids: [MARKET.id] })];
    const plan = planFolds(nodes, opts({ collapsedLabels: [MARKET] }));
    expect(plan.memberToCluster.get(1)).toBe(labelClusterKey(MARKET.id));
  });

  it('a page in several collapsed labels folds into the highest-ranked (D5)', () => {
    // order is rank-ascending: Scam (top) before Market.
    const nodes = [node({ id: 1, label_ids: [MARKET.id, SCAM.id] })];
    const plan = planFolds(nodes, opts({ collapsedLabels: [SCAM, MARKET] }));
    expect(plan.memberToCluster.get(1)).toBe(labelClusterKey(SCAM.id));
  });
});

describe('planFolds — D6: domain is the floor', () => {
  it('a labeled page in a collapsed domain is pulled into the label fold', () => {
    const nodes = [
      node({ id: 1, domain: 'x.onion', label_ids: [SCAM.id] }),
      node({ id: 2, domain: 'x.onion' }), // plain — stays with the domain
      node({ id: 3, domain: 'x.onion' }),
    ];
    const plan = planFolds(
      nodes,
      opts({ collapsedDomains: new Set(['x.onion']), collapsedLabels: [SCAM] }),
    );
    expect(plan.memberToCluster.get(1)).toBe(labelClusterKey(SCAM.id));
    expect(plan.memberToCluster.get(2)).toBe(clusterKey('x.onion'));
    // The domain fold shows fewer pages (2 of 3).
    expect(plan.clusters.get(clusterKey('x.onion'))?.members).toHaveLength(2);
    expect(plan.clusters.get(labelClusterKey(SCAM.id))?.members).toHaveLength(1);
  });

  it('omits a domain fold whose every member was claimed by a label fold', () => {
    const nodes = [
      node({ id: 1, domain: 'x.onion', label_ids: [SCAM.id] }),
      node({ id: 2, domain: 'x.onion', label_ids: [SCAM.id] }),
    ];
    const plan = planFolds(
      nodes,
      opts({ collapsedDomains: new Set(['x.onion']), collapsedLabels: [SCAM] }),
    );
    expect(plan.clusters.has(clusterKey('x.onion'))).toBe(false);
    expect(plan.clusters.get(labelClusterKey(SCAM.id))?.members).toHaveLength(2);
  });
});

describe('planFolds — overlap counts (D5)', () => {
  it('surfaces lower-ranked collapsed labels the fold members also carry', () => {
    const nodes = [
      node({ id: 1, label_ids: [SCAM.id, MARKET.id] }),
      node({ id: 2, label_ids: [SCAM.id, MARKET.id] }),
      node({ id: 3, label_ids: [SCAM.id, FORUM.id] }),
      node({ id: 4, label_ids: [SCAM.id] }),
    ];
    const plan = planFolds(nodes, opts({ collapsedLabels: [SCAM, MARKET, FORUM] }));
    const scam = plan.clusters.get(labelClusterKey(SCAM.id))!;
    expect(scam.members).toHaveLength(4);
    // "Scam · 4 pages (2 also Market, 1 also Forum)"
    expect(scam.raw.title_text).toContain('2 also Market');
    expect(scam.raw.title_text).toContain('1 also Forum');
  });
});
