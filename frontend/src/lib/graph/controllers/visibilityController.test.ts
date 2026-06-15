import { describe, it, expect, vi } from 'vitest';
import Graph from 'graphology';
import { createVisibilityController } from './visibilityController';
import type { FilterDeps, DomainVisibilityDeps } from './visibilityController';

// Helper: build a directed graph with raw node attributes
function makeGraph(): Graph {
  const g = new Graph({ type: 'directed' });
  g.addNode('1', { raw: { id: 1, domain: 'a.onion', depth: 0 } });
  g.addNode('2', { raw: { id: 2, domain: 'b.onion', depth: 1 } });
  g.addNode('3', { raw: { id: 3, domain: 'a.onion', depth: 2 } });
  g.addNode('4', { raw: { id: 4, domain: 'c.onion', depth: 1 } });
  // 1->2, 2->3, 1->4
  g.addEdge('1', '2');
  g.addEdge('2', '3');
  g.addEdge('1', '4');
  return g;
}

function makeFilters(overrides: Partial<FilterDeps> = {}): FilterDeps {
  return {
    maxHops: 0,
    hideOrphans: false,
    mutualOnly: false,
    showAllEdges: true,
    edgeMode: 'all',
    ...overrides,
  };
}

function makeVisibility(
  hidden: Set<string> = new Set(),
  hiddenNodes: Set<number> = new Set(),
): DomainVisibilityDeps {
  return {
    isHidden: (d) => (d ? hidden.has(d) : false),
    isNodeHidden: (id) => (id != null ? hiddenNodes.has(id as number) : false),
  };
}

describe('visibilityController', () => {
  it('with no filters all nodes and edges are visible', () => {
    const g = makeGraph();
    const ctrl = createVisibilityController({
      getGraph: () => g,
      getReachable: () => null,
      filters: makeFilters(),
      domainVisibility: makeVisibility(),
    });
    ctrl.compute();
    expect(ctrl.getVisibleNodeCount()).toBe(4);
    expect(ctrl.getVisibleEdgeCount()).toBe(3);
  });

  it('isVisible returns true for visible nodes', () => {
    const g = makeGraph();
    const ctrl = createVisibilityController({
      getGraph: () => g,
      getReachable: () => null,
      filters: makeFilters(),
      domainVisibility: makeVisibility(),
    });
    ctrl.compute();
    expect(ctrl.isVisible('1')).toBe(true);
    expect(ctrl.isVisible('2')).toBe(true);
  });

  it('maxHops filter hides nodes beyond depth', () => {
    const g = makeGraph();
    const ctrl = createVisibilityController({
      getGraph: () => g,
      getReachable: () => null,
      filters: makeFilters({ maxHops: 1 }),
      domainVisibility: makeVisibility(),
    });
    ctrl.compute();
    // nodes at depth 0 and 1 visible; depth 2 hidden
    expect(ctrl.isVisible('1')).toBe(true); // depth 0
    expect(ctrl.isVisible('2')).toBe(true); // depth 1
    expect(ctrl.isVisible('4')).toBe(true); // depth 1
    expect(ctrl.isVisible('3')).toBe(false); // depth 2
  });

  it('domain hide hides all nodes of a domain', () => {
    const g = makeGraph();
    const ctrl = createVisibilityController({
      getGraph: () => g,
      getReachable: () => null,
      filters: makeFilters(),
      domainVisibility: makeVisibility(new Set(['a.onion'])),
    });
    ctrl.compute();
    expect(ctrl.isVisible('1')).toBe(false); // a.onion
    expect(ctrl.isVisible('3')).toBe(false); // a.onion
    expect(ctrl.isVisible('2')).toBe(true);  // b.onion
    expect(ctrl.isVisible('4')).toBe(true);  // c.onion
  });

  it('node id hide hides a specific node', () => {
    const g = makeGraph();
    const ctrl = createVisibilityController({
      getGraph: () => g,
      getReachable: () => null,
      filters: makeFilters(),
      domainVisibility: makeVisibility(new Set(), new Set([2])),
    });
    ctrl.compute();
    expect(ctrl.isVisible('2')).toBe(false);
    expect(ctrl.isVisible('1')).toBe(true);
  });

  it('ego reachability filter limits visible nodes', () => {
    const g = makeGraph();
    // Only nodes 1 and 2 are reachable
    const reachable = new Set(['1', '2']);
    const ctrl = createVisibilityController({
      getGraph: () => g,
      getReachable: () => reachable,
      filters: makeFilters(),
      domainVisibility: makeVisibility(),
    });
    ctrl.compute();
    expect(ctrl.isVisible('1')).toBe(true);
    expect(ctrl.isVisible('2')).toBe(true);
    expect(ctrl.isVisible('3')).toBe(false);
    expect(ctrl.isVisible('4')).toBe(false);
  });

  it('cross-site edge mode hides same-domain edges', () => {
    // Add same-domain edge 1->3 (both a.onion)
    const g = makeGraph();
    g.addEdge('1', '3');
    const ctrl = createVisibilityController({
      getGraph: () => g,
      getReachable: () => null,
      filters: makeFilters({ edgeMode: 'cross-site' }),
      domainVisibility: makeVisibility(),
    });
    ctrl.compute();
    // 1->2 (a->b) and 1->4 (a->c) are cross-site; 2->3 (b->a) is cross-site
    // 1->3 (a->a) is same-site — hidden
    expect(ctrl.isEdgeVisible('1->3')).toBe(false);
  });

  it('same-site edge mode hides cross-domain edges', () => {
    const g = makeGraph();
    g.addEdge('1', '3'); // a.onion -> a.onion (same site)
    const ctrl = createVisibilityController({
      getGraph: () => g,
      getReachable: () => null,
      filters: makeFilters({ edgeMode: 'same-site' }),
      domainVisibility: makeVisibility(),
    });
    ctrl.compute();
    // 1->2 is cross-site, so hidden; 1->3 is same-site, visible
    expect(ctrl.isEdgeVisible(g.edges('1', '3')[0])).toBe(true);
    // All edges from 1 to b.onion/c.onion are hidden
    const crossEdge = g.edges('1', '2')[0];
    expect(ctrl.isEdgeVisible(crossEdge)).toBe(false);
  });

  it('hideOrphans removes nodes with no edges', () => {
    const g = new Graph({ type: 'directed' });
    g.addNode('1', { raw: { id: 1, domain: 'a.onion', depth: 0 } });
    g.addNode('2', { raw: { id: 2, domain: 'b.onion', depth: 1 } });
    g.addNode('3', { raw: { id: 3, domain: 'c.onion', depth: 2 } });
    g.addEdge('1', '2');
    // Node 3 is an orphan
    const ctrl = createVisibilityController({
      getGraph: () => g,
      getReachable: () => null,
      filters: makeFilters({ hideOrphans: true }),
      domainVisibility: makeVisibility(),
    });
    ctrl.compute();
    expect(ctrl.isVisible('3')).toBe(false);
    expect(ctrl.isVisible('1')).toBe(true);
    expect(ctrl.isVisible('2')).toBe(true);
  });

  it('visible count matches predicate count', () => {
    const g = makeGraph();
    const ctrl = createVisibilityController({
      getGraph: () => g,
      getReachable: () => null,
      filters: makeFilters({ maxHops: 1 }),
      domainVisibility: makeVisibility(),
    });
    ctrl.compute();
    let counted = 0;
    g.forEachNode((node) => {
      if (ctrl.isVisible(node)) counted++;
    });
    expect(ctrl.getVisibleNodeCount()).toBe(counted);
  });

  it('scope predicate restricts visible nodes', () => {
    const g = makeGraph();
    const ctrl = createVisibilityController({
      getGraph: () => g,
      getReachable: () => null,
      filters: makeFilters(),
      domainVisibility: makeVisibility(),
    });
    // Only allow nodes in scope set {1, 2}
    ctrl.setScope((nodeId) => nodeId === '1' || nodeId === '2');
    ctrl.compute();
    expect(ctrl.isVisible('1')).toBe(true);
    expect(ctrl.isVisible('2')).toBe(true);
    expect(ctrl.isVisible('3')).toBe(false);
    expect(ctrl.isVisible('4')).toBe(false);
  });

  it('clearing scope restores all-visible behaviour', () => {
    const g = makeGraph();
    const ctrl = createVisibilityController({
      getGraph: () => g,
      getReachable: () => null,
      filters: makeFilters(),
      domainVisibility: makeVisibility(),
    });
    ctrl.setScope((nodeId) => nodeId === '1');
    ctrl.compute();
    expect(ctrl.getVisibleNodeCount()).toBe(1);
    ctrl.setScope(null);
    ctrl.compute();
    expect(ctrl.getVisibleNodeCount()).toBe(4);
  });

  it('scope with includeHidden shows nodes the hide list would drop', () => {
    const g = makeGraph();
    const ctrl = createVisibilityController({
      getGraph: () => g,
      getReachable: () => null,
      filters: makeFilters(),
      // a.onion is hidden — nodes 1 and 3
      domainVisibility: makeVisibility(new Set(['a.onion'])),
    });
    // hidden-source scope: keep exactly the hidden nodes, include them.
    ctrl.setScope((_n, raw) => raw?.domain === 'a.onion', { includeHidden: true });
    ctrl.compute();
    expect(ctrl.isVisible('1')).toBe(true); // a.onion, hidden — now shown
    expect(ctrl.isVisible('3')).toBe(true); // a.onion, hidden — now shown
    expect(ctrl.isVisible('2')).toBe(false); // b.onion, out of scope
    expect(ctrl.isVisible('4')).toBe(false); // c.onion, out of scope
  });

  it('scope without includeHidden still honours the hide list', () => {
    const g = makeGraph();
    const ctrl = createVisibilityController({
      getGraph: () => g,
      getReachable: () => null,
      filters: makeFilters(),
      domainVisibility: makeVisibility(new Set(['a.onion'])),
    });
    // scope allows all a.onion, but hide still drops them (no includeHidden).
    ctrl.setScope((_n, raw) => raw?.domain === 'a.onion');
    ctrl.compute();
    expect(ctrl.getVisibleNodeCount()).toBe(0);
  });

  it('clearing scope also clears includeHidden', () => {
    const g = makeGraph();
    const ctrl = createVisibilityController({
      getGraph: () => g,
      getReachable: () => null,
      filters: makeFilters(),
      domainVisibility: makeVisibility(new Set(['a.onion'])),
    });
    ctrl.setScope((_n, raw) => raw?.domain === 'a.onion', { includeHidden: true });
    ctrl.compute();
    expect(ctrl.getVisibleNodeCount()).toBe(2);
    ctrl.setScope(null);
    ctrl.compute();
    // hide list back in force: a.onion dropped, only b/c visible
    expect(ctrl.isVisible('1')).toBe(false);
    expect(ctrl.getVisibleNodeCount()).toBe(2);
  });

  it('subscribe fires after compute()', () => {
    const g = makeGraph();
    const ctrl = createVisibilityController({
      getGraph: () => g,
      getReachable: () => null,
      filters: makeFilters(),
      domainVisibility: makeVisibility(),
    });
    const listener = vi.fn();
    ctrl.subscribe(listener);
    ctrl.compute();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('unsubscribe stops listener', () => {
    const g = makeGraph();
    const ctrl = createVisibilityController({
      getGraph: () => g,
      getReachable: () => null,
      filters: makeFilters(),
      domainVisibility: makeVisibility(),
    });
    const listener = vi.fn();
    const unsub = ctrl.subscribe(listener);
    unsub();
    ctrl.compute();
    expect(listener).not.toHaveBeenCalled();
  });

  it('mutualOnly removes nodes without both incoming and outgoing edges', () => {
    // Graph: 1->2->3, 2->1 (mutual between 1 and 2), 3 has only incoming
    const g = new Graph({ type: 'directed' });
    g.addNode('1', { raw: { id: 1, domain: 'a.onion', depth: 0 } });
    g.addNode('2', { raw: { id: 2, domain: 'b.onion', depth: 1 } });
    g.addNode('3', { raw: { id: 3, domain: 'c.onion', depth: 2 } });
    g.addEdge('1', '2');
    g.addEdge('2', '1');
    g.addEdge('2', '3');
    const ctrl = createVisibilityController({
      getGraph: () => g,
      getReachable: () => null,
      filters: makeFilters({ mutualOnly: true }),
      domainVisibility: makeVisibility(),
    });
    ctrl.compute();
    // Node 3 only has in-edges, no out-edges — hidden
    expect(ctrl.isVisible('3')).toBe(false);
    // Nodes 1 and 2 have both in and out — visible
    expect(ctrl.isVisible('1')).toBe(true);
    expect(ctrl.isVisible('2')).toBe(true);
  });
});
