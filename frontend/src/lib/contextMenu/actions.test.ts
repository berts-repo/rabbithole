// Tests for the multi-target Selection helpers.
//
// The actions module imports Svelte stores (.svelte.ts) that use $state
// rune syntax, which can't run in plain node/vitest without the Svelte
// compiler. We test:
//   1. The explainError helper from $lib/api/errors (pure, importable)
//   2. Selection shape builders via inlined pure logic mirrors (same
//      pattern as the analysisStatus.test.ts precedent in this repo)
//   3. Target-shaping derivations (stub filtering, flag filtering)
//
// The actual verb functions (sendToCrawl, addToCollection, etc.) dispatch
// to fetch + stores; those are integration-level and are covered by the
// browser smoke test after merge.

import { describe, expect, it } from 'vitest';
import { explainError } from '$lib/api/errors';
import { isUncrawled } from '$lib/nodeState';
import type { GraphNode } from '$lib/api';

// ---- Inline mirrors of the pure Selection builders ----
// (Duplicated from actions.ts to avoid importing the Svelte-store-heavy
// module. If the interface changes, both must be updated.)

interface Selection {
  nodes: GraphNode[];
  urls: string[];
}

function selectionFromNode(node: GraphNode): Selection {
  return { nodes: [node], urls: [node.raw_url] };
}

function selectionFromNodes(nodes: GraphNode[]): Selection {
  return { nodes, urls: nodes.map((n) => n.raw_url) };
}

// Minimal GraphNode fixture.
function makeNode(overrides: Partial<GraphNode> = {}): GraphNode {
  return {
    id: 1,
    label: 'test',
    alias: null,
    title_text: '',
    raw_url: 'http://example.onion/',
    color: '#000',
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
    ...overrides,
  };
}

describe('explainError', () => {
  it('passes through Error.message with fallback prefix', () => {
    const result = explainError(new Error('network timeout'), 'Load failed');
    expect(result).toBe('Load failed: network timeout');
  });

  it('returns fallback for unknown error type', () => {
    const result = explainError('unexpected string', 'Load failed');
    expect(result).toBe('Load failed');
  });

  it('returns fallback for null', () => {
    const result = explainError(null, 'Op failed');
    expect(result).toBe('Op failed');
  });
});

describe('selectionFromNode', () => {
  it('builds a Selection with one node and one URL', () => {
    const node = makeNode({ id: 42, raw_url: 'http://abc.onion/' });
    const sel = selectionFromNode(node);
    expect(sel.nodes).toHaveLength(1);
    expect(sel.nodes[0].id).toBe(42);
    expect(sel.urls).toEqual(['http://abc.onion/']);
  });
});

describe('selectionFromNodes', () => {
  it('builds a Selection with multiple nodes', () => {
    const nodes = [
      makeNode({ id: 1, raw_url: 'http://a.onion/' }),
      makeNode({ id: 2, raw_url: 'http://b.onion/' }),
    ];
    const sel = selectionFromNodes(nodes);
    expect(sel.nodes).toHaveLength(2);
    expect(sel.urls).toEqual(['http://a.onion/', 'http://b.onion/']);
  });

  it('returns empty arrays for empty input', () => {
    const sel = selectionFromNodes([]);
    expect(sel.nodes).toHaveLength(0);
    expect(sel.urls).toHaveLength(0);
  });
});

describe('Selection shape invariants', () => {
  it('nodes and urls have the same length', () => {
    const nodes = [
      makeNode({ id: 1, raw_url: 'http://a.onion/' }),
      makeNode({ id: 2, raw_url: 'http://b.onion/' }),
      makeNode({ id: 3, raw_url: 'http://c.onion/' }),
    ];
    const sel: Selection = selectionFromNodes(nodes);
    expect(sel.nodes.length).toBe(sel.urls.length);
  });

  it('stub filtering: only non-stub nodes count as crawled', () => {
    const nodes = [
      makeNode({ id: 1, state: 'crawled' }),
      makeNode({ id: 2, state: 'known' }),
      makeNode({ id: 3, state: 'crawled' }),
    ];
    const crawled = nodes.filter((n) => !isUncrawled(n));
    expect(crawled).toHaveLength(2);
    expect(crawled.map((n) => n.id)).toEqual([1, 3]);
  });

  it('already-flagged filtering: excludes nodes with non-null flag_status', () => {
    const nodes = [
      makeNode({ id: 1, flag_status: null }),
      makeNode({ id: 2, flag_status: 'flagged' }),
      makeNode({ id: 3, flag_status: null }),
    ];
    const toFlag = nodes.filter((n) => !n.flag_status);
    expect(toFlag).toHaveLength(2);
    expect(toFlag.map((n) => n.id)).toEqual([1, 3]);
  });

  it('url dedup: each url corresponds 1:1 with raw_url of its node', () => {
    const nodes = [
      makeNode({ id: 10, raw_url: 'http://x.onion/' }),
      makeNode({ id: 11, raw_url: 'http://y.onion/' }),
    ];
    const sel = selectionFromNodes(nodes);
    for (let i = 0; i < sel.nodes.length; i++) {
      expect(sel.urls[i]).toBe(sel.nodes[i].raw_url);
    }
  });
});

describe('sendToCrawl routing logic', () => {
  // Tests the routing rule (single URL → actQueueCrawl, multi → actCrawlSelected)
  // without calling the actual functions that touch stores.
  it('routes single URL differently from multi-URL', () => {
    function routingMode(sel: Selection): 'single' | 'multi' | 'none' {
      if (sel.urls.length === 0) return 'none';
      if (sel.urls.length === 1) return 'single';
      return 'multi';
    }

    expect(routingMode({ nodes: [], urls: [] })).toBe('none');
    expect(routingMode(selectionFromNode(makeNode()))).toBe('single');
    expect(
      routingMode(
        selectionFromNodes([makeNode({ id: 1 }), makeNode({ id: 2, raw_url: 'http://b.onion/' })]),
      ),
    ).toBe('multi');
  });
});
