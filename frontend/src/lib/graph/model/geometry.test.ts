import { describe, it, expect } from 'vitest';
import Graph from 'graphology';
import {
  NODE_SPACING,
  nodeSize,
  haloOffset,
  sunflowerAround,
  positionStubsAroundParents,
  positionOrphanStubsOutside,
} from './geometry';

describe('nodeSize', () => {
  it('fixes clusters at 12, even when also flagged stub', () => {
    expect(nodeSize(0, 0, true, false)).toBe(12);
    expect(nodeSize(99, 99, true, true)).toBe(12);
  });

  it('renders stubs small', () => {
    expect(nodeSize(50, 50, false, true)).toBe(1.0);
  });

  it('log-scales fetched nodes from a degree-0 floor of 4, capped at 12', () => {
    expect(nodeSize(0, 0, false, false)).toBe(4);
    expect(nodeSize(2, 1, false, false)).toBe(7); // deg 3 → 4 + log2(4)*1.5
    expect(nodeSize(5000, 5000, false, false)).toBe(12); // 4 + min(8, …)
  });
});

describe('haloOffset', () => {
  it('places slot 0 at radius HALO_BASE_R on the +x axis', () => {
    const p = haloOffset(10, 20, 0);
    expect(p.x).toBeCloseTo(22); // 10 + 12*sqrt(1), hubRadius default 0
    expect(p.y).toBeCloseTo(20);
  });

  it('is deterministic and pushes later slots further out', () => {
    const a = haloOffset(0, 0, 1);
    const b = haloOffset(0, 0, 1);
    expect(a).toEqual(b);
    expect(Math.hypot(a.x, a.y)).toBeGreaterThan(
      Math.hypot(haloOffset(0, 0, 0).x, haloOffset(0, 0, 0).y),
    );
  });
});

describe('sunflowerAround', () => {
  it('collapses a lone member onto the centre', () => {
    expect(sunflowerAround(5, 7, 0, 1)).toEqual({ x: 5, y: 7 });
  });

  it('fans members out using NODE_SPACING for the ring scale', () => {
    const p = sunflowerAround(0, 0, 0, 4);
    expect(p.x).toBeCloseTo((4 * NODE_SPACING) / (2 * Math.PI)); // r0 at theta 0
    expect(p.y).toBeCloseTo(0);
  });
});

// Build a graph: parent `p` at (px,py) plus the given stubs. Each stub
// entry is [key, parentId, userPositioned]; stubs start at (0,0).
function haloGraph(
  px: number,
  py: number,
  stubs: [string, string | null, boolean][],
): Graph {
  const g = new Graph();
  g.addNode('p', { x: px, y: py, raw: { state: 'crawled' } });
  for (const [key, parent, userPositioned] of stubs) {
    g.addNode(key, {
      x: 0,
      y: 0,
      raw: { state: 'known' },
      parent_id: parent,
      userPositioned,
    });
  }
  return g;
}

describe('positionStubsAroundParents', () => {
  it('fans a parent\'s stubs into consecutive halo slots, id-sorted', () => {
    const g = haloGraph(100, 200, [
      ['s2', 'p', false],
      ['s1', 'p', false],
    ]);
    positionStubsAroundParents(g);
    const slot0 = haloOffset(100, 200, 0);
    const slot1 = haloOffset(100, 200, 1);
    expect(g.getNodeAttribute('s1', 'x')).toBeCloseTo(slot0.x);
    expect(g.getNodeAttribute('s1', 'y')).toBeCloseTo(slot0.y);
    expect(g.getNodeAttribute('s2', 'x')).toBeCloseTo(slot1.x);
    expect(g.getNodeAttribute('s2', 'y')).toBeCloseTo(slot1.y);
  });

  it('leaves dragged stubs put and does not let them claim a slot', () => {
    const g = haloGraph(100, 200, [
      ['s1', 'p', true], // dragged — skipped entirely
      ['s2', 'p', false],
    ]);
    positionStubsAroundParents(g);
    expect(g.getNodeAttribute('s1', 'x')).toBe(0);
    expect(g.getNodeAttribute('s1', 'y')).toBe(0);
    // s2 still takes slot 0 — the dragged stub freed it.
    const slot0 = haloOffset(100, 200, 0);
    expect(g.getNodeAttribute('s2', 'x')).toBeCloseTo(slot0.x);
  });

  it('leaves orphan stubs (parent not in graph) where they are', () => {
    const g = haloGraph(100, 200, [['s1', 'missing', false]]);
    positionStubsAroundParents(g);
    expect(g.getNodeAttribute('s1', 'x')).toBe(0);
    expect(g.getNodeAttribute('s1', 'y')).toBe(0);
  });
});

// A graph with `crowd` fetched nodes on a circle of radius `crowdR` about a
// centre, plus parentless uncrawled stubs seeded at the origin.
function orphanGraph(
  centre: [number, number],
  crowdR: number,
  crowd: number,
  orphanKeys: string[],
  draggedKeys: string[] = [],
): Graph {
  const g = new Graph();
  for (let i = 0; i < crowd; i++) {
    const theta = (i / crowd) * 2 * Math.PI;
    g.addNode(`f${i}`, {
      x: centre[0] + Math.cos(theta) * crowdR,
      y: centre[1] + Math.sin(theta) * crowdR,
      raw: { state: 'crawled' },
    });
  }
  for (const k of orphanKeys) {
    g.addNode(k, { x: 0, y: 0, raw: { state: 'known' }, parent_id: null });
  }
  for (const k of draggedKeys) {
    g.addNode(k, {
      x: 0,
      y: 0,
      raw: { state: 'known' },
      parent_id: null,
      userPositioned: true,
    });
  }
  return g;
}

describe('positionOrphanStubsOutside', () => {
  it('rings orphans outside the crowd\'s bounding circle, centred on it', () => {
    const g = orphanGraph([50, 50], 30, 8, ['10']);
    positionOrphanStubsOutside(g);
    const x = g.getNodeAttribute('10', 'x') as number;
    const y = g.getNodeAttribute('10', 'y') as number;
    // Distance from the crowd centre must clear the crowd radius (30) plus gap.
    const r = Math.hypot(x - 50, y - 50);
    expect(r).toBeGreaterThan(30 + NODE_SPACING * 2);
  });

  it('is deterministic and id-ordered, packing later ids further out', () => {
    const a = orphanGraph([0, 0], 10, 4, ['100', '5', '20']);
    const b = orphanGraph([0, 0], 10, 4, ['20', '100', '5']);
    positionOrphanStubsOutside(a);
    positionOrphanStubsOutside(b);
    for (const k of ['5', '20', '100']) {
      expect(a.getNodeAttribute(k, 'x')).toBeCloseTo(b.getNodeAttribute(k, 'x') as number);
      expect(a.getNodeAttribute(k, 'y')).toBeCloseTo(b.getNodeAttribute(k, 'y') as number);
    }
    // Slot 0 is the lowest id (5); each later slot pushes further out.
    const dist = (g: Graph, k: string) =>
      Math.hypot(g.getNodeAttribute(k, 'x') as number, g.getNodeAttribute(k, 'y') as number);
    expect(dist(a, '100')).toBeGreaterThan(dist(a, '5'));
  });

  it('spreads orphans on an empty graph instead of stacking on the origin', () => {
    const g = orphanGraph([0, 0], 0, 0, ['1', '2']);
    positionOrphanStubsOutside(g);
    const d1 = Math.hypot(g.getNodeAttribute('1', 'x') as number, g.getNodeAttribute('1', 'y') as number);
    expect(d1).toBeGreaterThan(0);
    // Two distinct positions, not co-located.
    expect(g.getNodeAttribute('1', 'x')).not.toBeCloseTo(g.getNodeAttribute('2', 'x') as number);
  });

  it('leaves dragged orphans put and excludes them from the ring', () => {
    const g = orphanGraph([0, 0], 10, 4, [], ['7']);
    positionOrphanStubsOutside(g);
    expect(g.getNodeAttribute('7', 'x')).toBe(0);
    expect(g.getNodeAttribute('7', 'y')).toBe(0);
  });

  it('no-ops when there are no orphan stubs', () => {
    const g = orphanGraph([5, 5], 10, 3, []);
    const before = ['f0', 'f1', 'f2'].map((k) => g.getNodeAttribute(k, 'x'));
    positionOrphanStubsOutside(g);
    const after = ['f0', 'f1', 'f2'].map((k) => g.getNodeAttribute(k, 'x'));
    expect(after).toEqual(before);
  });
});
