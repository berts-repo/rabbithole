import { describe, it, expect } from 'vitest';
import type { GraphNode } from '$lib/api';
import { isClusterKey } from './clusterDomain';
import {
  isLabelClusterKey,
  labelClusterKey,
  labelClusterId,
  synthesizeLabelClusterRaw,
} from './clusterLabel';

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

describe('label-cluster key scheme', () => {
  it('mints and decodes a label-cluster key', () => {
    expect(labelClusterKey(7)).toBe('cluster:label:7');
    expect(labelClusterId('cluster:label:7')).toBe(7);
  });

  it('round-trips an id through key + decode', () => {
    for (const id of [1, 42, 9999]) {
      expect(labelClusterId(labelClusterKey(id))).toBe(id);
    }
  });

  it('is detected by both isLabelClusterKey and the shared isClusterKey', () => {
    const k = labelClusterKey(3);
    expect(isLabelClusterKey(k)).toBe(true);
    expect(isClusterKey(k)).toBe(true); // shares the `cluster:` prefix
  });

  it('rejects domain-cluster keys and non-cluster keys as label keys', () => {
    expect(isLabelClusterKey('cluster:evil.onion')).toBe(false);
    expect(isLabelClusterKey('123')).toBe(false);
    expect(isLabelClusterKey(123)).toBe(false);
    expect(isLabelClusterKey(null)).toBe(false);
    expect(isLabelClusterKey(undefined)).toBe(false);
  });
});

describe('synthesizeLabelClusterRaw', () => {
  const scam = { id: 5, name: 'Scam', color: '#f00' };

  it('marks the result a cluster with a stable negative id, named by the label', () => {
    const raw = synthesizeLabelClusterRaw(scam, [node()]);
    expect(raw.is_cluster).toBe(true);
    expect(raw.id).toBeLessThan(0);
    expect(raw.label).toBe('Scam');
    expect(raw.domain).toBeNull();
    // Deterministic — same label id hashes to the same node id.
    expect(synthesizeLabelClusterRaw(scam, [node()]).id).toBe(raw.id);
    expect(synthesizeLabelClusterRaw({ ...scam, id: 6 }, [node()]).id).not.toBe(raw.id);
  });

  it('paints with the label swatch and carries the label for colour-by-label', () => {
    const raw = synthesizeLabelClusterRaw(scam, [node({ color: '#abc' })]);
    expect(raw.color).toBe('#f00');
    expect(raw.label_ids).toEqual([5]);
    expect(raw.domain_label_ids).toEqual([]);
  });

  it('falls back to a member colour when the label has no swatch', () => {
    const raw = synthesizeLabelClusterRaw({ ...scam, color: null }, [node({ color: '#abc' })]);
    expect(raw.color).toBe('#abc');
  });

  it('sums member degrees and counts members', () => {
    const raw = synthesizeLabelClusterRaw(scam, [
      node({ in_degree_count: 2, out_degree_count: 5 }),
      node({ in_degree_count: 3, out_degree_count: 1 }),
    ]);
    expect(raw.in_degree_count).toBe(5);
    expect(raw.out_degree_count).toBe(6);
    expect(raw.title_text).toContain('2 pages');
  });

  it('renders overlap lines so nothing is silently swallowed', () => {
    const raw = synthesizeLabelClusterRaw(scam, [node(), node()], [
      { name: 'Market', count: 4 },
      { name: 'Forum', count: 1 },
    ]);
    expect(raw.title_text).toContain('4 also Market');
    expect(raw.title_text).toContain('1 also Forum');
  });

  it('lets investigating outrank pending for the overlay flag', () => {
    expect(
      synthesizeLabelClusterRaw(scam, [
        node({ flag_status: 'pending' }),
        node({ flag_status: 'investigating' }),
      ]).flag_status,
    ).toBe('investigating');
  });
});
