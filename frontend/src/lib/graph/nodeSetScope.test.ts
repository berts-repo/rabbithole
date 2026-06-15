import { describe, it, expect } from 'vitest';
import {
  buildNodeSetPredicate,
  nodeSetSignature,
  type HiddenDeps,
  type NodeSetSource,
} from './nodeSetScope';
import type { GraphNode } from '$lib/api';

// Minimal GraphNode factory — only the fields the predicates read.
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

const noHidden: HiddenDeps = { isHidden: () => false, isNodeHidden: () => false };

describe('buildNodeSetPredicate', () => {
  it('domain — keeps only nodes of the host, re-derives from attrs', () => {
    const { predicate, includeHidden } = buildNodeSetPredicate(
      { kind: 'domain', host: 'a.onion' },
      noHidden,
    );
    expect(includeHidden).toBe(false);
    expect(predicate('1', node({ id: 1, domain: 'a.onion' }))).toBe(true);
    expect(predicate('2', node({ id: 2, domain: 'b.onion' }))).toBe(false);
    expect(predicate('3', node({ id: 3, domain: null }))).toBe(false);
  });

  it('bookmarks — matches node domain against the bookmarked host set', () => {
    const { predicate } = buildNodeSetPredicate(
      { kind: 'bookmarks', hosts: ['x.onion', 'y.onion'] },
      noHidden,
    );
    expect(predicate('1', node({ domain: 'x.onion' }))).toBe(true);
    expect(predicate('2', node({ domain: 'z.onion' }))).toBe(false);
    expect(predicate('3', node({ domain: null }))).toBe(false);
  });

  it('hidden — keeps hidden nodes and asks the controller to include them', () => {
    const hiddenDeps: HiddenDeps = {
      isHidden: (d) => d === 'h.onion',
      isNodeHidden: (id) => id === 9,
    };
    const { predicate, includeHidden } = buildNodeSetPredicate({ kind: 'hidden' }, hiddenDeps);
    expect(includeHidden).toBe(true);
    expect(predicate('1', node({ id: 1, domain: 'h.onion' }))).toBe(true);
    expect(predicate('9', node({ id: 9, domain: 'visible.onion' }))).toBe(true);
    expect(predicate('2', node({ id: 2, domain: 'visible.onion' }))).toBe(false);
  });

  it('captured sources — membership by frozen node-id set', () => {
    for (const kind of ['flag', 'fingerprint', 'selection'] as const) {
      const source = { kind, nodeIds: [2, 4], summary: 's' } as NodeSetSource;
      const { predicate, includeHidden } = buildNodeSetPredicate(source, noHidden);
      expect(includeHidden).toBe(false);
      expect(predicate('2', node({ id: 2 }))).toBe(true);
      expect(predicate('4', node({ id: 4 }))).toBe(true);
      expect(predicate('3', node({ id: 3 }))).toBe(false);
    }
  });

  it('predicate is false for missing raw', () => {
    const { predicate } = buildNodeSetPredicate({ kind: 'domain', host: 'a.onion' }, noHidden);
    expect(predicate('1', undefined)).toBe(false);
  });
});

describe('nodeSetSignature', () => {
  it('singleton sources collapse to one signature', () => {
    expect(nodeSetSignature({ kind: 'hidden' })).toBe('hidden');
    expect(nodeSetSignature({ kind: 'bookmarks', hosts: ['a', 'b'] })).toBe('bookmarks');
  });

  it('domain / fingerprint / flag key off their identity', () => {
    expect(nodeSetSignature({ kind: 'domain', host: 'a.onion' })).toBe('domain:a.onion');
    expect(
      nodeSetSignature({ kind: 'fingerprint', nodeIds: [1], summary: 'Server:nginx' }),
    ).toBe('fingerprint:Server:nginx');
    expect(nodeSetSignature({ kind: 'flag', nodeIds: [1], summary: 'investigating' })).toBe(
      'flag:investigating',
    );
  });

  it('selection signature is order-independent', () => {
    const a = nodeSetSignature({ kind: 'selection', nodeIds: [3, 1, 2] });
    const b = nodeSetSignature({ kind: 'selection', nodeIds: [1, 2, 3] });
    expect(a).toBe(b);
    expect(a).toBe('selection:1,2,3');
  });
});
