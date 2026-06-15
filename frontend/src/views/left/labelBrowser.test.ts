import { describe, it, expect } from 'vitest';
import type { GraphNode } from '$lib/api';
import { labelMemberNodeIds, sameIdSet } from './labelBrowser';

// Minimal GraphNode fixture — overrides win over the defaults.
const node = (over: Partial<GraphNode> = {}): GraphNode => ({
  id: 1,
  label: 'page',
  alias: null,
  title_text: 'page',
  raw_url: 'http://a.onion/',
  color: '#abc',
  domain: 'a.onion',
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
});

describe('labelMemberNodeIds', () => {
  it('unions direct and via-domain membership per label', () => {
    const map = labelMemberNodeIds([
      node({ id: 1, label_ids: [10], domain_label_ids: [20] }),
      node({ id: 2, label_ids: [10] }),
      node({ id: 3, domain_label_ids: [20] }),
    ]);
    expect([...(map.get(10) ?? [])].sort()).toEqual([1, 2]);
    expect([...(map.get(20) ?? [])].sort()).toEqual([1, 3]);
  });

  it('dedupes a node that lists the same id directly and via domain', () => {
    const map = labelMemberNodeIds([
      node({ id: 1, label_ids: [10], domain_label_ids: [10] }),
    ]);
    expect(map.get(10)?.size).toBe(1);
  });

  it('omits labels carried by no node', () => {
    const map = labelMemberNodeIds([node({ id: 1, label_ids: [10] })]);
    expect(map.has(99)).toBe(false);
  });
});

describe('sameIdSet', () => {
  it('is true for equal members regardless of insertion order', () => {
    expect(sameIdSet(new Set([1, 2, 3]), new Set([3, 2, 1]))).toBe(true);
  });

  it('is false on a size or member mismatch', () => {
    expect(sameIdSet(new Set([1, 2]), new Set([1, 2, 3]))).toBe(false);
    expect(sameIdSet(new Set([1, 2]), new Set([1, 9]))).toBe(false);
  });

  it('treats two empty sets as equal', () => {
    expect(sameIdSet(new Set(), new Set())).toBe(true);
  });
});
