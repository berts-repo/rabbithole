// Graph data store for the Explore tab. Holds the latest /api/graph
// payload + a graphology Graph instance built from it, and exposes the
// derived counts the toolbar status line renders. One graphology
// instance per workspace tab; F4a only ships the Global tab.
//
// F4b SWR slice 1 — incremental diff on poll. applyPayload picks between
// two paths: rebuildInto (full clear + re-add, slow but always correct)
// and applyDiff (in-place add/remove/update against the previous
// payload, preserves WebGL state + user-dragged x/y). Diff is taken
// only when the cluster topology hasn't changed since the previous
// apply; rebuild is the safe fallback for cluster transitions, filter
// toggles, and the first apply on a fresh tab.
//
// F4b Slice 7 — domain clustering. When `graphFiltersStore.groupByDomain`
// is on, every domain with > 1 fetched member that isn't in
// `expandedDomains` is collapsed into a single synthetic cluster node
// keyed `cluster:<domain>`. Edges crossing into a collapsed domain are
// rewritten through the cluster; same-domain self-loops are dropped.
// Clustering is purely client-side — the backend always serves
// `is_cluster: false` (see backend/backend/db/graph.py:232).

import Graph from 'graphology';
import type { GraphPayload } from '$lib/api';
import { graphFiltersStore } from './graphFilters.svelte';
import { graphPinsStore } from './graphPins.svelte';
import { graphCollapseStore } from './graphCollapse.svelte';
import { labelsStore } from './labels.svelte';
import {
  rebuildInto,
  applyDiff,
  type ClusterFilterOptions,
} from '$lib/graph/model/applyPayload';
import type { LabelClusterDef } from '$lib/graph/model/foldPlan';
import { deriveStructuralCounts, deriveScopeCounts } from '$lib/graph/model/graphCounts';

export interface EgoFocus {
  nodeId: number;
  depth: 1 | 2 | 3;
}

interface GraphState {
  payload: GraphPayload | null;
  lastUpdated: number | null;
  loading: boolean;
  error: string | null;
  egoFocus: EgoFocus | null;
  // Domains the analyst has double-clicked open while groupByDomain is
  // on. Transient — not persisted across reloads. Reset on workspace
  // switch or when groupByDomain toggles off.
  expandedDomains: Set<string>;
  // Counts derived from the graphology instance after structural
  // filtering. F4b's reducer-time visual filters update visibleNodeCount
  // / visibleEdgeCount separately — these are the structural baseline
  // (post uncrawled-filter, pre-reducer). The toolbar reads `visibleX` so
  // the analyst sees the actually-rendered count; debugging reads the
  // structural baseline to spot reducer-vs-structural mismatches.
  nodeCount: number;
  edgeCount: number;
  visibleNodeCount: number;
  visibleEdgeCount: number;
  // Workspace-scoped totals for the tab-bar status line. Unlike the
  // structural counts above (which track the filtered graphology instance),
  // these are derived from the raw payload so they reflect the collection's
  // true scale regardless of the active view filters. Set once per
  // applyPayload — filter toggles never change them.
  scopeDomains: number;
  scopePages: number;
  // Bumped every time graphInstance is rebuilt or re-filtered. The
  // canvas watches this to refresh Sigma without re-mounting the WebGL
  // context. A filter toggle bumps the version and re-runs reducers;
  // a fresh payload also bumps it and re-runs the FA2 layout if it
  // looks like a structural change has landed.
  version: number;
  // Workspace id the graphology instance was last built for. Used by
  // applyPayload to force a full rebuild on workspace switch instead of
  // running applyDiff — dropping thousands of global nodes one-by-one
  // triggers an O(n²) Sigma refresh storm that freezes the browser.
  lastWorkspaceId: string | null;
}

const state = $state<GraphState>({
  payload: null,
  lastUpdated: null,
  loading: false,
  error: null,
  egoFocus: null,
  expandedDomains: new Set<string>(),
  nodeCount: 0,
  edgeCount: 0,
  visibleNodeCount: 0,
  visibleEdgeCount: 0,
  scopeDomains: 0,
  scopePages: 0,
  version: 0,
  lastWorkspaceId: null,
});

// graphology Graph lives outside the rune state object — its mutation
// surface is its own; we don't want $state to proxy every internal Map.
// Critical: this reference is kept stable for the lifetime of the page.
// Sigma binds to it once and re-uses the same WebGL context across
// rebuilds; swapping the reference forces Sigma to kill its renderer
// and recompile its shaders, which is 10-20s on SwiftShader.
const graphInstance: Graph = new Graph({ type: 'directed', multi: false });

// Snapshot the filter inputs the apply paths need. Built fresh per
// apply so rebuildInto/applyDiff stay free of any rune dependency.
function currentClusterOptions(): ClusterFilterOptions {
  return {
    showUncrawled: graphFiltersStore.showUncrawled,
    groupByDomain: graphFiltersStore.groupByDomain,
    expandedDomains: state.expandedDomains,
    pinnedIds: graphPinsStore.pinned,
    // Phase 3d collapse axes for the active workspace tab.
    collapsedDomains: graphCollapseStore.domains,
    collapsedLabels: collapsedLabelDefs(),
  };
}

// Resolve the active tab's collapsed label ids to rank-ordered fold defs. The
// catalog is already rank-sorted, so iterating it in order yields the D5
// priority the fold resolver needs (first carried label wins). Ids the catalog
// no longer knows (a label deleted out from under a stale fold) drop out.
function collapsedLabelDefs(): LabelClusterDef[] {
  const collapsed = graphCollapseStore.labels;
  if (collapsed.size === 0) return [];
  const out: LabelClusterDef[] = [];
  for (const l of labelsStore.labels) {
    if (collapsed.has(l.id)) out.push({ id: l.id, name: l.name, color: l.color });
  }
  return out;
}

export const graphStore = {
  get payload() {
    return state.payload;
  },
  get lastUpdated() {
    return state.lastUpdated;
  },
  get loading() {
    return state.loading;
  },
  get error() {
    return state.error;
  },
  get egoFocus() {
    return state.egoFocus;
  },
  get expandedDomains(): ReadonlySet<string> {
    return state.expandedDomains;
  },
  get nodeCount() {
    return state.nodeCount;
  },
  get edgeCount() {
    return state.edgeCount;
  },
  get visibleNodeCount() {
    return state.visibleNodeCount;
  },
  get visibleEdgeCount() {
    return state.visibleEdgeCount;
  },
  get scopeDomains() {
    return state.scopeDomains;
  },
  get scopePages() {
    return state.scopePages;
  },
  get version() {
    return state.version;
  },
  // graphology instance is shared by reference — Sigma binds to it once
  // and we mutate in place on each poll. Sigma's `refresh()` picks up
  // changes; full rebuild keeps internal `add/drop` event noise bounded.
  graph(): Graph {
    return graphInstance;
  },

  setLoading(loading: boolean): void {
    state.loading = loading;
  },
  setError(error: string | null): void {
    state.error = error;
  },
  applyPayload(payload: GraphPayload, workspaceId: string): void {
    // First apply for this graph (fresh tab / cold start) → rebuild.
    // Workspace switch → always rebuild: applyDiff drops nodes one-by-one
    // which triggers a Sigma refresh per drop; on a large global graph
    // switching to a small collection that's O(n²) and freezes the browser.
    // Subsequent same-workspace applies try the in-place diff path; rebuild
    // is the safe fallback for cluster-topology / filter transitions the
    // diff can't express. See applyDiff for the bail conditions.
    const workspaceSwitched =
      state.lastWorkspaceId !== null && state.lastWorkspaceId !== workspaceId;
    let diffed = false;
    if (!workspaceSwitched && state.payload !== null && graphInstance.order > 0) {
      diffed = applyDiff(graphInstance, payload, currentClusterOptions());
    }
    if (!diffed) {
      rebuildInto(graphInstance, payload, currentClusterOptions());
    }
    state.lastWorkspaceId = workspaceId;
    state.payload = payload;
    // visible* default to the structural counts until the canvas
    // computes reducer-time visibility (one tick later). Keeps the
    // toolbar accurate during the first paint after a poll lands.
    Object.assign(state, deriveStructuralCounts(graphInstance));
    // Tab-bar scope counts come straight off the payload, not the filtered
    // graphology instance — they don't move when the analyst toggles a
    // view filter, so only applyPayload (a fresh fetch) recomputes them.
    const scope = deriveScopeCounts(payload);
    state.scopeDomains = scope.domains;
    state.scopePages = scope.pages;
    state.lastUpdated = Date.now();
    state.error = null;
    state.version++;
  },
  /**
   * Re-runs `rebuildInto` against the last applied payload. Used when a
   * structural filter (showUncrawled, groupByDomain, expandedDomains)
   * changes between polls and we need the graphology graph to reflect
   * the new structure without a refetch.
   */
  rebuildFromCurrentPayload(): void {
    if (!state.payload) return;
    rebuildInto(graphInstance, state.payload, currentClusterOptions());
    Object.assign(state, deriveStructuralCounts(graphInstance));
    state.version++;
  },
  /**
   * Called from the canvas after `filterVisibility` recomputes — the
   * toolbar reads visibleX so the status line shows what's actually
   * rendered, not just what's in graphology.
   */
  setVisibleCounts(nodes: number, edges: number): void {
    state.visibleNodeCount = nodes;
    state.visibleEdgeCount = edges;
  },

  setEgoFocus(focus: EgoFocus | null): void {
    state.egoFocus = focus;
  },
  setEgoDepth(depth: 1 | 2 | 3): void {
    if (state.egoFocus) {
      state.egoFocus = { ...state.egoFocus, depth };
    }
  },

  /**
   * Flips a domain's expanded state and rebuilds graphology. Called from
   * the canvas's double-click handler — on a cluster node to expand, on
   * any member node (while groupByDomain is on) to collapse the domain
   * back. A no-op if groupByDomain is off.
   */
  toggleDomainExpanded(domain: string): void {
    if (!domain) return;
    const next = new Set(state.expandedDomains);
    if (next.has(domain)) next.delete(domain);
    else next.add(domain);
    state.expandedDomains = next;
    this.rebuildFromCurrentPayload();
  },
  /**
   * Drops every expanded-domain flag in one shot. Called when
   * groupByDomain is toggled off so the next on-toggle starts from a
   * fully-collapsed view, and on workspace switch so the old tab's
   * exploration state doesn't bleed.
   */
  clearExpandedDomains(): void {
    if (state.expandedDomains.size === 0) return;
    state.expandedDomains = new Set();
    this.rebuildFromCurrentPayload();
  },
};
