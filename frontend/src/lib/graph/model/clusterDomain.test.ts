import { describe, it, expect } from 'vitest';
import type { GraphNode } from '$lib/api';
import {
  isClusterKey,
  clusterKey,
  clusterDomain,
  synthesizeClusterRaw,
} from './clusterDomain';

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

describe('cluster key scheme', () => {
  it('mints and decodes a cluster key', () => {
    expect(clusterKey('evil.onion')).toBe('cluster:evil.onion');
    expect(clusterDomain('cluster:evil.onion')).toBe('evil.onion');
  });

  it('round-trips a domain through key + decode', () => {
    for (const d of ['a.onion', 'with:colon.onion', '']) {
      expect(clusterDomain(clusterKey(d))).toBe(d);
    }
  });

  it('detects cluster keys and rejects everything else', () => {
    expect(isClusterKey('cluster:x.onion')).toBe(true);
    expect(isClusterKey('cluster:')).toBe(true);
    expect(isClusterKey('123')).toBe(false);
    expect(isClusterKey(123)).toBe(false);
    expect(isClusterKey(null)).toBe(false);
    expect(isClusterKey(undefined)).toBe(false);
  });
});

describe('synthesizeClusterRaw', () => {
  it('marks the result as a cluster with a stable negative id', () => {
    const raw = synthesizeClusterRaw('x.onion', [node()]);
    expect(raw.is_cluster).toBe(true);
    expect(raw.state).toBe('crawled');
    expect(raw.id).toBeLessThan(0);
    // Deterministic — the same domain hashes to the same id.
    expect(synthesizeClusterRaw('x.onion', [node()]).id).toBe(raw.id);
    expect(synthesizeClusterRaw('y.onion', [node()]).id).not.toBe(raw.id);
  });

  it('labels with the domain and counts the members', () => {
    const raw = synthesizeClusterRaw('x.onion', [node(), node(), node()]);
    expect(raw.label).toBe('x.onion');
    expect(raw.domain).toBe('x.onion');
    expect(raw.title_text).toContain('3 pages');
  });

  it('labels with the domain alias when set, host otherwise (D7)', () => {
    // The backend serves the domain alias on every member's `alias`.
    const aliased = synthesizeClusterRaw('x.onion', [
      node({ alias: 'NightMarket' }),
      node({ alias: 'NightMarket' }),
    ]);
    expect(aliased.label).toBe('NightMarket');
    expect(aliased.alias).toBe('NightMarket');
    expect(aliased.domain).toBe('x.onion'); // host is still the identity
    expect(aliased.title_text).toContain('NightMarket — 2 pages');

    const bare = synthesizeClusterRaw('x.onion', [node({ alias: null })]);
    expect(bare.label).toBe('x.onion');
    expect(bare.alias).toBeNull();
  });

  it('sums member degrees', () => {
    const raw = synthesizeClusterRaw('x.onion', [
      node({ in_degree_count: 2, out_degree_count: 5 }),
      node({ in_degree_count: 3, out_degree_count: 1 }),
    ]);
    expect(raw.in_degree_count).toBe(5);
    expect(raw.out_degree_count).toBe(6);
  });

  it('lets investigating outrank pending for the overlay flag', () => {
    expect(
      synthesizeClusterRaw('x.onion', [
        node({ flag_status: 'pending' }),
        node({ flag_status: 'investigating' }),
      ]).flag_status,
    ).toBe('investigating');
  });

  it('falls back to pending and treats done/dismissed as no overlay', () => {
    expect(
      synthesizeClusterRaw('x.onion', [
        node({ flag_status: 'done' }),
        node({ flag_status: 'pending' }),
      ]).flag_status,
    ).toBe('pending');
    expect(
      synthesizeClusterRaw('x.onion', [
        node({ flag_status: 'done' }),
        node({ flag_status: 'dismissed' }),
      ]).flag_status,
    ).toBeNull();
  });

  it('takes color and category from the first member', () => {
    const raw = synthesizeClusterRaw('x.onion', [
      node({ color: '#111', category: 'market' }),
      node({ color: '#222', category: 'forum' }),
    ]);
    expect(raw.color).toBe('#111');
    expect(raw.category).toBe('market');
  });
});
