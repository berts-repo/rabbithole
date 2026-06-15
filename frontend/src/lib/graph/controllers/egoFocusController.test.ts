import { describe, it, expect, vi } from 'vitest';
import Graph from 'graphology';
import { createEgoFocusController } from './egoFocusController';

// Linear chain: 1 - 2 - 3 - 4 - 5
function makeLinearGraph(): Graph {
  const g = new Graph();
  for (let i = 1; i <= 5; i++) g.addNode(String(i), { raw: {} });
  for (let i = 1; i < 5; i++) g.addEdge(String(i), String(i + 1));
  return g;
}

// Branch: 1 - 2 - 3, 2 - 4, 4 - 5
function makeBranchGraph(): Graph {
  const g = new Graph();
  ['1', '2', '3', '4', '5'].forEach((n) => g.addNode(n, { raw: {} }));
  g.addEdge('1', '2');
  g.addEdge('2', '3');
  g.addEdge('2', '4');
  g.addEdge('4', '5');
  return g;
}

// Disconnected: 1 - 2 - 3, 4 - 5
function makeDisconnectedGraph(): Graph {
  const g = new Graph();
  ['1', '2', '3', '4', '5'].forEach((n) => g.addNode(n, { raw: {} }));
  g.addEdge('1', '2');
  g.addEdge('2', '3');
  g.addEdge('4', '5');
  return g;
}

describe('egoFocusController', () => {
  it('starts with no focus', () => {
    const ctrl = createEgoFocusController({ getGraph: makeLinearGraph });
    expect(ctrl.getFocusedNodeId()).toBeNull();
    expect(ctrl.getReachable()).toBeNull();
    expect(ctrl.getDepth()).toBe(2);
  });

  it('focusOn sets the focused node', () => {
    const ctrl = createEgoFocusController({ getGraph: makeLinearGraph });
    ctrl.focusOn(1);
    expect(ctrl.getFocusedNodeId()).toBe(1);
  });

  it('unfocus clears the focused node', () => {
    const ctrl = createEgoFocusController({ getGraph: makeLinearGraph });
    ctrl.focusOn(1);
    ctrl.unfocus();
    expect(ctrl.getFocusedNodeId()).toBeNull();
    expect(ctrl.getReachable()).toBeNull();
  });

  it('linear graph: depth 1 from node 3 reaches 2 and 4', () => {
    const g = makeLinearGraph();
    const ctrl = createEgoFocusController({ getGraph: () => g });
    ctrl.focusOn(3, 1);
    const r = ctrl.getReachable()!;
    expect(r.has('3')).toBe(true);
    expect(r.has('2')).toBe(true);
    expect(r.has('4')).toBe(true);
    expect(r.has('1')).toBe(false);
    expect(r.has('5')).toBe(false);
  });

  it('linear graph: depth 2 from node 3 reaches all', () => {
    const g = makeLinearGraph();
    const ctrl = createEgoFocusController({ getGraph: () => g });
    ctrl.focusOn(3, 2);
    const r = ctrl.getReachable()!;
    expect(r.size).toBe(5);
  });

  it('branch graph: depth 2 from node 1 reaches 1,2,3,4 but not 5', () => {
    const g = makeBranchGraph();
    const ctrl = createEgoFocusController({ getGraph: () => g });
    ctrl.focusOn(1, 2);
    const r = ctrl.getReachable()!;
    expect(r.has('1')).toBe(true);
    expect(r.has('2')).toBe(true);
    expect(r.has('3')).toBe(true);
    expect(r.has('4')).toBe(true);
    expect(r.has('5')).toBe(false);
  });

  it('disconnected graph: focus on 1 at depth 5 does not reach 4 or 5', () => {
    const g = makeDisconnectedGraph();
    const ctrl = createEgoFocusController({ getGraph: () => g });
    ctrl.focusOn(1, 5);
    const r = ctrl.getReachable()!;
    expect(r.has('1')).toBe(true);
    expect(r.has('2')).toBe(true);
    expect(r.has('3')).toBe(true);
    expect(r.has('4')).toBe(false);
    expect(r.has('5')).toBe(false);
  });

  it('isReachable returns true for nodes in reachable set', () => {
    const g = makeLinearGraph();
    const ctrl = createEgoFocusController({ getGraph: () => g });
    ctrl.focusOn(1, 2);
    expect(ctrl.isReachable('1')).toBe(true);
    expect(ctrl.isReachable('2')).toBe(true);
    expect(ctrl.isReachable('3')).toBe(true);
    expect(ctrl.isReachable('4')).toBe(false);
  });

  it('isReachable returns false when no focus', () => {
    const g = makeLinearGraph();
    const ctrl = createEgoFocusController({ getGraph: () => g });
    expect(ctrl.isReachable('1')).toBe(false);
  });

  it('cache invalidation on payload swap', () => {
    let g = makeLinearGraph();
    const ctrl = createEgoFocusController({ getGraph: () => g });
    ctrl.focusOn(1, 1);
    const r1 = ctrl.getReachable();
    expect(r1?.has('2')).toBe(true);

    // Swap graph to a disconnected version and invalidate cache
    g = makeDisconnectedGraph();
    ctrl.invalidateCache();
    // Node 1 depth 1 in disconnected graph only reaches 2
    const r2 = ctrl.getReachable()!;
    expect(r2.has('1')).toBe(true);
    expect(r2.has('2')).toBe(true);
    // r1 was stale; r2 recomputed after invalidation
    expect(r2).not.toBe(r1);
  });

  it('cache is reused when key is unchanged', () => {
    const g = makeLinearGraph();
    const getGraph = vi.fn(() => g);
    const ctrl = createEgoFocusController({ getGraph });
    ctrl.focusOn(1, 2);
    ctrl.getReachable();
    ctrl.getReachable();
    // getGraph called once for the first computation, then cache hits
    expect(getGraph).toHaveBeenCalledTimes(1);
  });

  it('setDepth invalidates cache and updates depth', () => {
    const g = makeLinearGraph();
    const ctrl = createEgoFocusController({ getGraph: () => g });
    ctrl.focusOn(1, 1);
    const r1 = ctrl.getReachable();
    ctrl.setDepth(3);
    expect(ctrl.getDepth()).toBe(3);
    const r2 = ctrl.getReachable();
    // r1 had depth 1 (reaches 1,2); r2 has depth 3 (reaches 1,2,3,4)
    expect(r1?.size).toBeLessThan(r2!.size);
  });

  it('subscribe fires on focusOn', () => {
    const ctrl = createEgoFocusController({ getGraph: makeLinearGraph });
    const listener = vi.fn();
    ctrl.subscribe(listener);
    ctrl.focusOn(2);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('subscribe fires on unfocus', () => {
    const ctrl = createEgoFocusController({ getGraph: makeLinearGraph });
    ctrl.focusOn(2);
    const listener = vi.fn();
    ctrl.subscribe(listener);
    ctrl.unfocus();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('unsubscribe stops listener', () => {
    const ctrl = createEgoFocusController({ getGraph: makeLinearGraph });
    const listener = vi.fn();
    const unsub = ctrl.subscribe(listener);
    unsub();
    ctrl.focusOn(1);
    expect(listener).not.toHaveBeenCalled();
  });

  it('missing focus node returns empty set', () => {
    const g = makeLinearGraph();
    const ctrl = createEgoFocusController({ getGraph: () => g });
    ctrl.focusOn(99); // node 99 not in graph
    const r = ctrl.getReachable();
    expect(r).not.toBeNull();
    expect(r!.size).toBe(0);
  });

  it('focusOn with explicit depth overrides previous depth', () => {
    const g = makeLinearGraph();
    const ctrl = createEgoFocusController({ getGraph: () => g });
    ctrl.focusOn(3, 1);
    expect(ctrl.getDepth()).toBe(1);
    ctrl.focusOn(3, 3);
    expect(ctrl.getDepth()).toBe(3);
  });
});
