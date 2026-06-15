// Visibility controller — visibility predicate over filters/scope/collection membership.
//
// Owns: FilterVisibility result (visibleNodes, visibleEdges Sets).
// Exposes: compute(), isVisible(nodeId), isEdgeVisible(edgeId),
//          getVisibleNodes(), getVisibleEdges(), getVisibleCount(),
//          setScope(predicate), subscribe().
//
// Scope predicate seam: a `scopePredicate` can be injected via setScope().
// NodeSet Workspaces (item 4) will plug in a workspace-scope predicate here
// without reshaping the controller. Default scope = all nodes visible.
//
// Pure TypeScript — no Svelte $state. Call compute() to recompute from deps.

import type Graph from 'graphology';
import type { GraphNode } from '$lib/api';

export interface FilterDeps {
  maxHops: number;
  hideOrphans: boolean;
  mutualOnly: boolean;
  showAllEdges: boolean;
  edgeMode: 'all' | 'cross-site' | 'same-site';
}

export interface DomainVisibilityDeps {
  isHidden(domain: string | null | undefined): boolean;
  isNodeHidden(id: number | null | undefined): boolean;
}

export interface FilterVisibility {
  visibleNodes: Set<string>;
  visibleEdges: Set<string>;
}

/**
 * A scope predicate can restrict the visible node set beyond the filter-level
 * restrictions. Return true to allow the node through, false to hide it.
 * NodeSet Workspaces will inject a workspace-membership predicate here.
 */
export type ScopePredicate = (nodeId: string, raw: GraphNode | undefined) => boolean;

export interface VisibilityControllerDeps {
  /** Returns the current graphology instance. */
  getGraph: () => Graph;
  /** Returns the current ego-reachable set, or null when no focus. */
  getReachable: () => Set<string> | null;
  /** Filter configuration. */
  filters: FilterDeps;
  /** Domain/node hide lists. */
  domainVisibility: DomainVisibilityDeps;
  /**
   * Label include/exclude filter (item 11, Phase 3c). A separate dimension
   * from the domain/node hide lists: it drops a node whose direct *or*
   * via-domain labels fail the analyst's include/exclude marks. Optional —
   * absent means no label filtering.
   */
  labelFilter?: {
    passes(directIds: readonly number[], domainIds: readonly number[]): boolean;
  };
}

export interface VisibilityController {
  /** Recompute visibility from current deps. Call when any dep changes. */
  compute(): void;
  /** True when the given node key is in the current visible set. */
  isVisible(nodeId: string): boolean;
  /** True when the given edge key is in the current visible set. */
  isEdgeVisible(edgeId: string): boolean;
  /** The current visible nodes Set. */
  getVisibleNodes(): Set<string>;
  /** The current visible edges Set. */
  getVisibleEdges(): Set<string>;
  /** Count of currently visible nodes. */
  getVisibleNodeCount(): number;
  /** Count of currently visible edges. */
  getVisibleEdgeCount(): number;
  /**
   * Install a scope predicate. Replaces any previous scope.
   * Pass null to clear the scope (all nodes are in scope).
   * NodeSet Workspaces calls this to restrict to workspace membership.
   *
   * `opts.includeHidden` keeps nodes the controller would normally drop for
   * being hidden — required by the `hidden` node-set source, whose whole
   * purpose is to display those nodes. Defaults to false.
   */
  setScope(predicate: ScopePredicate | null, opts?: { includeHidden?: boolean }): void;
  /** Register a listener called after each compute(). Returns unsub fn. */
  subscribe(listener: () => void): () => void;
}

export function createVisibilityController(deps: VisibilityControllerDeps): VisibilityController {
  let visibleNodes: Set<string> = new Set();
  let visibleEdges: Set<string> = new Set();
  let scopePredicate: ScopePredicate | null = null;
  let scopeIncludesHidden = false;

  const listeners = new Set<() => void>();

  function notify(): void {
    for (const l of listeners) l();
  }

  function compute(): void {
    const g = deps.getGraph();
    const reachable = deps.getReachable();
    const { filters, domainVisibility } = deps;
    const maxHops = filters.maxHops;
    const useDepthCap = !reachable && maxHops > 0;

    const nextNodes = new Set<string>();
    const nextEdges = new Set<string>();

    g.forEachNode((node, attrs) => {
      const raw = attrs.raw as GraphNode | undefined;
      if (!raw) return;
      if (reachable && !reachable.has(node)) return;
      if (useDepthCap && (raw.depth ?? Infinity) > maxHops) return;
      // A scope that includes hidden nodes (the `hidden` node-set source)
      // bypasses the hide drops — showing those nodes is the point.
      if (!scopeIncludesHidden) {
        if (domainVisibility.isHidden(raw.domain)) return;
        if (domainVisibility.isNodeHidden(raw.id)) return;
      }
      if (
        deps.labelFilter &&
        !deps.labelFilter.passes(raw.label_ids, raw.domain_label_ids)
      ) {
        return;
      }
      if (scopePredicate && !scopePredicate(node, raw)) return;
      nextNodes.add(node);
    });

    // Edge pass — only include edges between two visible nodes.
    const edgeMode = filters.edgeMode;
    const dedup = !filters.showAllEdges;
    const seenDomainPair = new Set<string>();

    g.forEachEdge((edge, _attrs, src, tgt, srcAttrs, tgtAttrs) => {
      if (!nextNodes.has(src) || !nextNodes.has(tgt)) return;
      const sRaw = srcAttrs.raw as GraphNode | undefined;
      const tRaw = tgtAttrs.raw as GraphNode | undefined;
      const sDom = sRaw?.domain ?? '';
      const tDom = tRaw?.domain ?? '';
      const sameSite = sDom !== '' && sDom === tDom;
      if (edgeMode === 'same-site' && !sameSite) return;
      if (edgeMode === 'cross-site' && sameSite) return;
      if (dedup) {
        const pair = sDom <= tDom ? `${sDom}|${tDom}` : `${tDom}|${sDom}`;
        if (seenDomainPair.has(pair)) return;
        seenDomainPair.add(pair);
      }
      nextEdges.add(edge);
    });

    // Mutual-only and hide-orphans: depend on the edge set.
    const { mutualOnly, hideOrphans } = filters;
    if (mutualOnly || hideOrphans) {
      const inDeg = new Map<string, number>();
      const outDeg = new Map<string, number>();
      for (const e of nextEdges) {
        const src = g.source(e);
        const tgt = g.target(e);
        outDeg.set(src, (outDeg.get(src) ?? 0) + 1);
        inDeg.set(tgt, (inDeg.get(tgt) ?? 0) + 1);
      }
      const dropped = new Set<string>();
      for (const n of nextNodes) {
        const i = inDeg.get(n) ?? 0;
        const o = outDeg.get(n) ?? 0;
        if (hideOrphans && i + o === 0) { dropped.add(n); continue; }
        if (mutualOnly && (i === 0 || o === 0)) { dropped.add(n); continue; }
      }
      if (dropped.size > 0) {
        for (const n of dropped) nextNodes.delete(n);
        for (const e of [...nextEdges]) {
          if (!nextNodes.has(g.source(e)) || !nextNodes.has(g.target(e))) {
            nextEdges.delete(e);
          }
        }
      }
    }

    visibleNodes = nextNodes;
    visibleEdges = nextEdges;
    notify();
  }

  function isVisible(nodeId: string): boolean {
    return visibleNodes.has(nodeId);
  }

  function isEdgeVisible(edgeId: string): boolean {
    return visibleEdges.has(edgeId);
  }

  function getVisibleNodes(): Set<string> {
    return visibleNodes;
  }

  function getVisibleEdges(): Set<string> {
    return visibleEdges;
  }

  function getVisibleNodeCount(): number {
    return visibleNodes.size;
  }

  function getVisibleEdgeCount(): number {
    return visibleEdges.size;
  }

  function setScope(predicate: ScopePredicate | null, opts?: { includeHidden?: boolean }): void {
    scopePredicate = predicate;
    scopeIncludesHidden = predicate !== null && (opts?.includeHidden ?? false);
  }

  function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  return {
    compute,
    isVisible,
    isEdgeVisible,
    getVisibleNodes,
    getVisibleEdges,
    getVisibleNodeCount,
    getVisibleEdgeCount,
    setScope,
    subscribe,
  };
}
