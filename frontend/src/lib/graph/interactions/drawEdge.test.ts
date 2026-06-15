import { describe, it, expect } from 'vitest';
import type { GraphNode } from '$lib/api';
import { resolveDrawEdgeRequest, resolveDrawEdgeClick } from './drawEdge';

// Minimal GraphNode factory — resolveDrawEdgeClick only reads `id`.
function makeNode(over: Partial<GraphNode> = {}): GraphNode {
  return {
    id: 1,
    label: 'node',
    alias: null,
    title_text: '',
    raw_url: 'http://example.onion',
    color: '#2eb89a',
    domain: 'example.onion',
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

describe('resolveDrawEdgeRequest', () => {
  it('opens the batch modal when 2 or more nodes are selected', () => {
    expect(resolveDrawEdgeRequest(2)).toEqual({ kind: 'open-batch-modal' });
    expect(resolveDrawEdgeRequest(5)).toEqual({ kind: 'open-batch-modal' });
  });

  it('begins sequential pick mode below 2 selected', () => {
    expect(resolveDrawEdgeRequest(0)).toEqual({ kind: 'begin-pick' });
    expect(resolveDrawEdgeRequest(1)).toEqual({ kind: 'begin-pick' });
  });
});

describe('resolveDrawEdgeClick', () => {
  it('ignores a click on a cluster node, even with a source set', () => {
    expect(resolveDrawEdgeClick(true, makeNode(), null)).toEqual({
      kind: 'ignore',
    });
    expect(
      resolveDrawEdgeClick(true, makeNode({ id: 2 }), makeNode({ id: 1 })),
    ).toEqual({ kind: 'ignore' });
  });

  it('ignores a click that resolves to no payload node', () => {
    expect(resolveDrawEdgeClick(false, undefined, null)).toEqual({
      kind: 'ignore',
    });
  });

  it('sets the source on the first valid pick', () => {
    const node = makeNode({ id: 7 });
    expect(resolveDrawEdgeClick(false, node, null)).toEqual({
      kind: 'set-source',
      node,
    });
  });

  it('ignores re-clicking the current source (matched by id)', () => {
    const source = makeNode({ id: 7 });
    // `picked` is a distinct object from `source` — as it is at runtime,
    // where it comes from a fresh payload lookup — but the same node id.
    expect(
      resolveDrawEdgeClick(false, makeNode({ id: 7 }), source),
    ).toEqual({ kind: 'ignore' });
  });

  it('opens the sequential modal on a second distinct pick', () => {
    const source = makeNode({ id: 1 });
    const dest = makeNode({ id: 2 });
    expect(resolveDrawEdgeClick(false, dest, source)).toEqual({
      kind: 'open-sequential',
      source,
      dest,
    });
  });
});
