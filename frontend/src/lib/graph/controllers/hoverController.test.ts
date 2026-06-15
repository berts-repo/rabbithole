import { describe, it, expect, vi, beforeEach } from 'vitest';
import Graph from 'graphology';
import { createHoverController } from './hoverController';

function makeGraph(): Graph {
  const g = new Graph();
  g.addNode('1', { label: 'Node 1', raw: { title_text: 'Title 1' } });
  g.addNode('2', { label: 'Node 2', raw: { title_text: 'Title 2' } });
  g.addNode('3', { label: 'Node 3', raw: {} });
  g.addEdge('1', '2');
  g.addEdge('2', '3');
  return g;
}

// No-op timer/rAF stubs for node test environment.
let timerIdCounter = 0;
const pendingTimers = new Map<number, () => void>();
function mockSetTimeout(fn: () => void, _ms: number): number {
  const id = ++timerIdCounter;
  pendingTimers.set(id, fn);
  return id;
}
function mockClearTimeout(id: number): void {
  pendingTimers.delete(id);
}
function mockRaf(_cb: FrameRequestCallback): number { return 0; }
function mockCaf(_id: number): void {}

describe('hoverController', () => {
  let graph: Graph;
  let onRefresh: ReturnType<typeof vi.fn>;
  let onTooltipChange: ReturnType<typeof vi.fn>;
  let onTooltipPos: ReturnType<typeof vi.fn>;
  let getNodeDisplayData: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    graph = makeGraph();
    onRefresh = vi.fn();
    onTooltipChange = vi.fn();
    onTooltipPos = vi.fn();
    getNodeDisplayData = vi.fn().mockReturnValue({ x: 100, y: 200 });
    timerIdCounter = 0;
    pendingTimers.clear();
  });

  function makeController() {
    return createHoverController({
      getGraph: () => graph,
      onRefresh,
      onTooltipChange,
      onTooltipPos,
      getNodeDisplayData,
      requestAnimationFrame: mockRaf,
      cancelAnimationFrame: mockCaf,
      setTimeout: mockSetTimeout,
      clearTimeout: mockClearTimeout,
    });
  }

  it('starts with no hover', () => {
    const ctrl = makeController();
    expect(ctrl.getHoveredNode()).toBeNull();
    expect(ctrl.getHoverNeighbours().size).toBe(0);
    ctrl.dispose();
  });

  it('sets hover to a node and populates neighbours', () => {
    const ctrl = makeController();
    ctrl.setHover('1');
    expect(ctrl.getHoveredNode()).toBe('1');
    // Node 1 is connected to Node 2
    expect(ctrl.getHoverNeighbours().has('2')).toBe(true);
    expect(ctrl.getHoverNeighbours().has('3')).toBe(false);
    ctrl.dispose();
  });

  it('calls onRefresh on hover enter', () => {
    const ctrl = makeController();
    ctrl.setHover('1');
    expect(onRefresh).toHaveBeenCalled();
    ctrl.dispose();
  });

  it('calls onTooltipChange with node title_text on hover enter', () => {
    const ctrl = makeController();
    ctrl.setHover('1');
    expect(onTooltipChange).toHaveBeenCalledWith('Title 1');
    ctrl.dispose();
  });

  it('uses label when title_text is missing', () => {
    const ctrl = makeController();
    ctrl.setHover('3');
    expect(onTooltipChange).toHaveBeenCalledWith('Node 3');
    ctrl.dispose();
  });

  it('clears hover on setHover(null)', () => {
    const ctrl = makeController();
    ctrl.setHover('1');
    ctrl.setHover(null);
    expect(ctrl.getHoveredNode()).toBeNull();
    expect(ctrl.getHoverNeighbours().size).toBe(0);
    ctrl.dispose();
  });

  it('clears tooltip on setHover(null)', () => {
    const ctrl = makeController();
    ctrl.setHover('1');
    ctrl.setHover(null);
    expect(onTooltipChange).toHaveBeenLastCalledWith('');
    expect(onTooltipPos).toHaveBeenLastCalledWith(null);
    ctrl.dispose();
  });

  it('sets heldFrom on leave', () => {
    const ctrl = makeController();
    ctrl.setHover('1');
    ctrl.setHover(null);
    // heldFrom should be set (hold the dim briefly)
    expect(ctrl.getHeldFrom()).not.toBeNull();
    expect(ctrl.getHeldFrom()?.node).toBe('1');
    ctrl.dispose();
  });

  it('cancels hold when re-entering a node', () => {
    const ctrl = makeController();
    ctrl.setHover('1');
    ctrl.setHover(null);
    expect(ctrl.getHeldFrom()).not.toBeNull();
    ctrl.setHover('2');
    // After re-entering, heldFrom should be cleared
    expect(ctrl.getHeldFrom()).toBeNull();
    ctrl.dispose();
  });

  it('subscribe fires listener on hover change', () => {
    const ctrl = makeController();
    const listener = vi.fn();
    ctrl.subscribe(listener);
    ctrl.setHover('1');
    expect(listener).toHaveBeenCalledTimes(1);
    ctrl.dispose();
  });

  it('unsubscribe stops listener from firing', () => {
    const ctrl = makeController();
    const listener = vi.fn();
    const unsub = ctrl.subscribe(listener);
    unsub();
    ctrl.setHover('1');
    expect(listener).not.toHaveBeenCalled();
    ctrl.dispose();
  });

  it('lerpHex interpolates colours correctly', () => {
    const ctrl = makeController();
    // Full black to full white at t=0.5 — Math.round(0 + 127.5) = 128 = 0x80
    const result = ctrl.lerpHex('#000000', '#ffffff', 0.5);
    expect(result).toBe('#808080');
    ctrl.dispose();
  });

  it('lerpHex returns from-colour at t=0', () => {
    const ctrl = makeController();
    expect(ctrl.lerpHex('#ff0000', '#0000ff', 0)).toBe('#ff0000');
    ctrl.dispose();
  });

  it('lerpHex returns to-colour at t=1', () => {
    const ctrl = makeController();
    expect(ctrl.lerpHex('#ff0000', '#0000ff', 1)).toBe('#0000ff');
    ctrl.dispose();
  });

  it('getFadeInProgress returns 1 when no fade active', () => {
    const ctrl = makeController();
    expect(ctrl.getFadeInProgress()).toBe(1);
    ctrl.dispose();
  });

  it('getFadeOutProgress returns 1 when no fade-out active', () => {
    const ctrl = makeController();
    expect(ctrl.getFadeOutProgress()).toBe(1);
    ctrl.dispose();
  });

  it('dispose clears all state', () => {
    const ctrl = makeController();
    ctrl.setHover('1');
    ctrl.dispose();
    expect(ctrl.getHoveredNode()).toBeNull();
    expect(ctrl.getHoverNeighbours().size).toBe(0);
    expect(ctrl.getHeldFrom()).toBeNull();
    expect(ctrl.getFadeFrom()).toBeNull();
  });

  it('node 2 neighbours include 1 and 3', () => {
    const ctrl = makeController();
    ctrl.setHover('2');
    expect(ctrl.getHoverNeighbours().has('1')).toBe(true);
    expect(ctrl.getHoverNeighbours().has('3')).toBe(true);
    ctrl.dispose();
  });
});
