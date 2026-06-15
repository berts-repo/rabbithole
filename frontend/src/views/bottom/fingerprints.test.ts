import { describe, it, expect } from 'vitest';
import type { FingerprintCluster, FingerprintMember } from '$lib/api';
import {
  clusterKey,
  clampMinSites,
  filterClusters,
  filterMembers,
  formatIdf,
} from './fingerprints';

const C = (key: string, value: string, sites = 2, idf = 1.5): FingerprintCluster => ({
  key,
  value,
  sites,
  idf,
});

const M = (
  id: number,
  url: string,
  title: string | null = null,
): FingerprintMember => ({ id, url, title, category: null, risk_score: null });

describe('fingerprints helpers', () => {
  it('builds a stable cluster key', () => {
    expect(clusterKey(C('Server', 'nginx/1.21.0'))).toBe('Server nginx/1.21.0');
    expect(clusterKey(C('X-Custom', ''))).toBe('X-Custom ');
  });

  it('clamps min-sites threshold', () => {
    expect(clampMinSites(0)).toBe(1);
    expect(clampMinSites(-5)).toBe(1);
    expect(clampMinSites(3)).toBe(3);
    expect(clampMinSites(3.7)).toBe(3);
    expect(clampMinSites(5000)).toBe(1000);
    expect(clampMinSites(Number.NaN)).toBe(2);
  });

  it('filters clusters by key + value (case-insensitive)', () => {
    const clusters = [C('Server', 'nginx'), C('X-Powered-By', 'Express')];
    expect(filterClusters(clusters, '').length).toBe(2);
    expect(filterClusters(clusters, '   ').length).toBe(2);
    expect(filterClusters(clusters, 'SERVER')).toEqual([C('Server', 'nginx')]);
    expect(filterClusters(clusters, 'express')).toEqual([
      C('X-Powered-By', 'Express'),
    ]);
    expect(filterClusters(clusters, 'nope')).toEqual([]);
  });

  it('filters members by URL + title', () => {
    const members = [
      M(1, 'http://a.onion/login', 'Login'),
      M(2, 'http://b.onion/index', null),
    ];
    // 'login' matches row 1 (URL + title) but not row 2.
    expect(filterMembers(members, 'login').length).toBe(1);
    expect(filterMembers(members, 'b.onion').length).toBe(1);
    expect(filterMembers(members, 'xyz')).toEqual([]);
  });

  it('formats IDF to two decimals, with em-dash for non-finite', () => {
    expect(formatIdf(0)).toBe('0.00');
    expect(formatIdf(1.234)).toBe('1.23');
    expect(formatIdf(Number.POSITIVE_INFINITY)).toBe('—');
    expect(formatIdf(Number.NaN)).toBe('—');
  });
});
