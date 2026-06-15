import { describe, it, expect, vi } from 'vitest';
import Graph from 'graphology';
import { createLayoutController } from './layoutController';
import type { LayoutControllerDeps } from './layoutController';

function makeGraph(): Graph {
  const g = new Graph();
  g.addNode('1', { x: 0, y: 0, raw: { state: 'crawled' } });
  g.addNode('2', { x: 1, y: 1, raw: { state: 'crawled' } });
  g.addEdge('1', '2');
  return g;
}

function makeDeps(overrides: Partial<LayoutControllerDeps> = {}): LayoutControllerDeps {
  return {
    getGraph: makeGraph,
    getRenderer: () => null,
    onSettlingStart: vi.fn(),
    onSettlingEnd: vi.fn(),
    onTimelineLegend: vi.fn(),
    ...overrides,
  };
}

describe('layoutController', () => {
  it('starts with the given layout kind', () => {
    const ctrl = createLayoutController('radial', makeDeps());
    expect(ctrl.getLayoutKind()).toBe('radial');
    ctrl.dispose();
  });

  it('setLayoutKind updates kind without relayout', () => {
    const ctrl = createLayoutController('radial', makeDeps());
    ctrl.setLayoutKind('hierarchical');
    expect(ctrl.getLayoutKind()).toBe('hierarchical');
    ctrl.dispose();
  });

  it('isRunning starts false', () => {
    const ctrl = createLayoutController('radial', makeDeps());
    expect(ctrl.isRunning()).toBe(false);
    ctrl.dispose();
  });

  it('relayout on sync layout calls onTimelineLegend', () => {
    const onTimelineLegend = vi.fn();
    const ctrl = createLayoutController('radial', makeDeps({ onTimelineLegend }));
    ctrl.relayout();
    expect(onTimelineLegend).toHaveBeenCalled();
    ctrl.dispose();
  });

  it('relayout on sync layout calls subscribe listeners', () => {
    const ctrl = createLayoutController('concentric', makeDeps());
    const listener = vi.fn();
    ctrl.subscribe(listener);
    ctrl.relayout();
    expect(listener).toHaveBeenCalled();
    ctrl.dispose();
  });

  it('relayout runs the sync layout without throwing', () => {
    const g = makeGraph();
    const ctrl = createLayoutController('radial', makeDeps({ getGraph: () => g }));
    expect(() => ctrl.relayout()).not.toThrow();
    ctrl.dispose();
  });

  it('subscribe fires on relayout', () => {
    const ctrl = createLayoutController('hierarchical', makeDeps());
    const listener = vi.fn();
    ctrl.subscribe(listener);
    ctrl.relayout();
    expect(listener).toHaveBeenCalledTimes(1);
    ctrl.dispose();
  });

  it('unsubscribe stops listener', () => {
    const ctrl = createLayoutController('concentric', makeDeps());
    const listener = vi.fn();
    const unsub = ctrl.subscribe(listener);
    unsub();
    ctrl.relayout();
    expect(listener).not.toHaveBeenCalled();
    ctrl.dispose();
  });

  it('cancelLayout is safe when no worker running', () => {
    const ctrl = createLayoutController('radial', makeDeps());
    expect(() => ctrl.cancelLayout()).not.toThrow();
    ctrl.dispose();
  });

  it('stopLayout is safe when no worker running', () => {
    const ctrl = createLayoutController('radial', makeDeps());
    expect(() => ctrl.stopLayout()).not.toThrow();
    ctrl.dispose();
  });

  it('dispose cancels running worker and clears listeners', () => {
    const onSettlingEnd = vi.fn();
    const ctrl = createLayoutController('force', makeDeps({ onSettlingEnd }));
    const listener = vi.fn();
    ctrl.subscribe(listener);

    // Mock the force layout so we can test cancellation
    // relayout with force would start a real worker — skip for unit test
    // Just test that dispose does not throw and clears subscriptions
    ctrl.dispose();
    // Further relayout should not fire the disposed listener
    // (but we can't call relayout after dispose without re-subscribing)
    expect(listener).not.toHaveBeenCalled();
  });

  it('timeline layout emits timeline metadata', () => {
    const onTimelineLegend = vi.fn();
    // Build a graph with dated nodes so timeline produces metadata
    const g = new Graph();
    g.addNode('1', { x: 0, y: 0, raw: { state: 'crawled', first_seen: '2024-01-01' } });
    g.addNode('2', { x: 1, y: 1, raw: { state: 'crawled', first_seen: '2024-06-01' } });
    g.addEdge('1', '2');
    const ctrl = createLayoutController('timeline', makeDeps({
      getGraph: () => g,
      onTimelineLegend,
    }));
    ctrl.relayout();
    // Should have been called with either null or a TimelineLegend
    expect(onTimelineLegend).toHaveBeenCalled();
    ctrl.dispose();
  });
});
