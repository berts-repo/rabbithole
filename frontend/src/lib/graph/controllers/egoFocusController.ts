// Ego-focus controller — focused node id, reachability cache, expansion depth.
//
// Owns: focusedNodeId | null, expansion depth, identity-keyed reachability cache.
// Exposes: focusOn(id, depth?), unfocus(), setDepth(d), isReachable(id),
//          getReachable(), getFocusedNodeId(), getDepth(), subscribe().
//
// Pure graph BFS via computeEgoReachable. The cache is keyed by "nodeId:depth"
// so re-focusing at the same depth returns the cached set without re-traversal.
// Cache is invalidated on unfocus, graph version change (via invalidateCache()),
// or focus node change.

import type Graph from 'graphology';
import { computeEgoReachable } from '$lib/graph/interactions/egoFocus';

export interface EgoFocusControllerDeps {
  /** Returns the current graphology instance. Called on focusOn and isReachable. */
  getGraph: () => Graph;
}

export interface EgoFocusController {
  /** Set focus to the given node at the given depth (default: preserve current or 2). */
  focusOn(nodeId: number, depth?: number): void;
  /** Clear focus. */
  unfocus(): void;
  /** Change depth while keeping the same focused node. Invalidates cache. */
  setDepth(depth: number): void;
  /** Invalidate the reachability cache (call on graph version change). */
  invalidateCache(): void;
  /** True when nodeId is in the current reachable set. False when no focus. */
  isReachable(nodeId: string): boolean;
  /** Current reachable set, or null when no focus or root is missing. */
  getReachable(): Set<string> | null;
  /** Currently focused node id, or null. */
  getFocusedNodeId(): number | null;
  /** Current ego depth. */
  getDepth(): number;
  /** Register a listener called on every state change. Returns unsub fn. */
  subscribe(listener: () => void): () => void;
}

const DEFAULT_DEPTH = 2;

export function createEgoFocusController(deps: EgoFocusControllerDeps): EgoFocusController {
  let focusedNodeId: number | null = null;
  let depth: number = DEFAULT_DEPTH;
  let cache: { key: string; reachable: Set<string> } | null = null;

  const listeners = new Set<() => void>();

  function notify(): void {
    for (const l of listeners) l();
  }

  function cacheKey(): string {
    return `${focusedNodeId}:${depth}`;
  }

  function computeReachable(): Set<string> | null {
    if (focusedNodeId === null) return null;
    const key = cacheKey();
    if (cache && cache.key === key) return cache.reachable;
    const g = deps.getGraph();
    const root = String(focusedNodeId);
    if (!g.hasNode(root)) return new Set();
    const reachable = computeEgoReachable(g, root, depth);
    cache = { key, reachable };
    return reachable;
  }

  function focusOn(nodeId: number, newDepth?: number): void {
    if (newDepth !== undefined) depth = newDepth;
    if (focusedNodeId !== nodeId) {
      // Changing node — invalidate the cache.
      cache = null;
    }
    focusedNodeId = nodeId;
    notify();
  }

  function unfocus(): void {
    focusedNodeId = null;
    cache = null;
    notify();
  }

  function setDepth(newDepth: number): void {
    if (depth === newDepth) return;
    depth = newDepth;
    cache = null;
    notify();
  }

  function invalidateCache(): void {
    cache = null;
  }

  function isReachable(nodeId: string): boolean {
    const r = computeReachable();
    if (!r) return false;
    return r.has(nodeId);
  }

  function getReachable(): Set<string> | null {
    return computeReachable();
  }

  function getFocusedNodeId(): number | null {
    return focusedNodeId;
  }

  function getDepth(): number {
    return depth;
  }

  function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  return {
    focusOn,
    unfocus,
    setDepth,
    invalidateCache,
    isReachable,
    getReachable,
    getFocusedNodeId,
    getDepth,
    subscribe,
  };
}
