import { describe, it, expect } from 'vitest';
import Graph from 'graphology';
import { computeEgoReachable, shortestPathEdges } from './egoFocus';

// A path graph 1-2-...-n. graphology's forEachNeighbor / forEachEdge(node)
// are direction-agnostic, so a plain directed addEdge is fine here.
function lineGraph(n: number): Graph {
  const g = new Graph();
  for (let i = 1; i <= n; i++) g.addNode(String(i));
  for (let i = 1; i < n; i++) g.addEdge(String(i), String(i + 1));
  return g;
}

describe('computeEgoReachable', () => {
  it('returns just the root at depth 0', () => {
    expect(computeEgoReachable(lineGraph(4), '1', 0)).toEqual(new Set(['1']));
  });

  it('expands one hop per depth step', () => {
    const g = lineGraph(5);
    expect(computeEgoReachable(g, '1', 1)).toEqual(new Set(['1', '2']));
    expect(computeEgoReachable(g, '1', 2)).toEqual(new Set(['1', '2', '3']));
  });

  it('reaches neighbours regardless of edge direction', () => {
    const g = lineGraph(3); // edges 1->2, 2->3
    expect(computeEgoReachable(g, '3', 1)).toEqual(new Set(['3', '2']));
  });

  it('returns an empty set when the root is absent', () => {
    expect(computeEgoReachable(lineGraph(3), '99', 2)).toEqual(new Set());
  });

  it('does not over-expand past the graph at large depth', () => {
    const g = lineGraph(3);
    expect(computeEgoReachable(g, '1', 10)).toEqual(new Set(['1', '2', '3']));
  });
});

describe('shortestPathEdges', () => {
  it('returns an empty set when source equals target', () => {
    expect(shortestPathEdges(lineGraph(3), '2', '2', new Set(['2']))).toEqual(
      new Set(),
    );
  });

  it('returns the edge keys along the path', () => {
    const g = new Graph();
    for (const id of ['1', '2', '3']) g.addNode(id);
    const e12 = g.addEdge('1', '2');
    const e23 = g.addEdge('2', '3');
    expect(
      shortestPathEdges(g, '1', '3', new Set(['1', '2', '3'])),
    ).toEqual(new Set([e12, e23]));
  });

  it('returns null when the target is outside the reachable set', () => {
    const g = lineGraph(3);
    expect(shortestPathEdges(g, '1', '3', new Set(['1', '2']))).toBeNull();
  });

  it('returns null when no path exists within reachable', () => {
    const g = new Graph();
    for (const id of ['1', '2', '3', '4']) g.addNode(id);
    g.addEdge('1', '2');
    g.addEdge('3', '4'); // disconnected component
    expect(
      shortestPathEdges(g, '1', '4', new Set(['1', '2', '3', '4'])),
    ).toBeNull();
  });

  it('picks the shorter of two routes', () => {
    // 1-2-4 is 2 hops; 1-3-2-4 is 3. BFS must take the former.
    const g = new Graph();
    for (const id of ['1', '2', '3', '4']) g.addNode(id);
    const e12 = g.addEdge('1', '2');
    const e24 = g.addEdge('2', '4');
    g.addEdge('1', '3');
    g.addEdge('3', '2');
    expect(
      shortestPathEdges(g, '1', '4', new Set(['1', '2', '3', '4'])),
    ).toEqual(new Set([e12, e24]));
  });
});
