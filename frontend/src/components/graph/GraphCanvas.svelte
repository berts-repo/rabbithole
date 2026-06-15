<script lang="ts">
  // Sigma canvas — mount, controllers, reactive bridges, DOM + overlays.
  // See $lib/graph/controllers/README.md for the controller shape.

  import type Sigma from 'sigma';
  import Graph from 'graphology';
  import { onMount, untrack, onDestroy } from 'svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { graphFiltersStore } from '$lib/stores/graphFilters.svelte';
  import { graphPinsStore } from '$lib/stores/graphPins.svelte';
  import { domainVisibilityStore } from '$lib/stores/domainVisibility.svelte';
  import { graphLayoutStore } from '$lib/stores/graphLayout.svelte';
  import { drawEdgeStore } from '$lib/stores/drawEdge.svelte';
  import { createGraphRenderer, probeWebGL } from '$lib/graph/runtime/sigmaRuntime';
  import { fitView, restoreView } from '$lib/graph/runtime/camera';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { layoutStore } from '$lib/stores/layout.svelte';
  import { workspaceSnapshots } from '$lib/stores/workspaceSnapshots.svelte';
  import { workspaceStore } from '$lib/stores/workspace.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { servicesStore } from '$lib/stores/services.svelte';
  import { graphPoller } from '$lib/pollers/graph.svelte';
  import {
    positionStubsAroundParents,
    positionOrphanStubsOutside,
  } from '$lib/graph/model/geometry';
  import { isUncrawled } from '$lib/nodeState';
  import { deleteEdge, type GraphEdge, type GraphNode } from '$lib/api';
  import {
    actCopyUrl, actCrawlSelected, actFlag, actFlagAll, actHideAll,
    actHideFromGraph, actMarkReviewedAll, actOpenInTor, actQueueCrawl,
    actRemoveFlag, actSaveSeedBookmark, actToggleReviewed, actTogglePin, explainApiError,
    queueAnalysis, labelPickerModal, renameModal, renameTarget, selectionFromNodes,
    type LabelPickerModal, type RenameModal, type RenameTarget,
  } from '$lib/contextMenu/actions';
  import { resolveDrawEdgeRequest } from '$lib/graph/interactions/drawEdge';
  import { shortestPathEdges } from '$lib/graph/interactions/egoFocus';
  import { createHoverController } from '$lib/graph/controllers/hoverController';
  import { createEgoFocusController } from '$lib/graph/controllers/egoFocusController';
  import { createVisibilityController } from '$lib/graph/controllers/visibilityController';
  import { buildNodeSetPredicate } from '$lib/graph/nodeSetScope';
  import { createReducerController, dominantLabelColor } from '$lib/graph/controllers/reducerController';
  import { labelsStore } from '$lib/stores/labels.svelte';
  import { labelFilterStore } from '$lib/stores/labelFilter.svelte';
  import { graphCollapseStore } from '$lib/stores/graphCollapse.svelte';
  import { createLayoutController } from '$lib/graph/controllers/layoutController';
  import { createSigmaEventController } from '$lib/graph/controllers/sigmaEventController';
  import { createContextMenuAdapter } from '$lib/graph/controllers/contextMenuAdapter';
  import type { TimelineLegend } from '$lib/graph/layouts';
  import EgoFocusOverlay from './EgoFocusOverlay.svelte';
  import GraphTooltip from './GraphTooltip.svelte';
  import ContextMenu from '$lib/contextMenu/ContextMenu.svelte';
  import SelectAllConfirm from './SelectAllConfirm.svelte';
  import RenameAliasPopover from './RenameAliasPopover.svelte';
  import LabelPickerPopover from '../labels/LabelPickerPopover.svelte';
  import AddMonitorModal from '../modals/AddMonitorModal.svelte';
  import CollectionPickerModal from '../modals/CollectionPickerModal.svelte';
  import DrawAnalystEdgeModal from '../modals/DrawAnalystEdgeModal.svelte';

  interface Props { fitToken: number; resetToken: number; onSelectionChange?: () => void; }
  let { fitToken, resetToken }: Props = $props();

  let containerEl: HTMLDivElement | undefined = $state();
  let renderer: Sigma | null = null;
  let lastAppliedVersion = -1;
  let webglError: string | null = $state(null);
  let showFirstVisitSkeleton = $state(false);
  let webglProbed = false;
  const MAX_AUTO_LAYOUT_NODES = 3000;
  let firstLayoutDone = false;
  let prevShowUncrawled = false;
  let timelineLegend = $state<TimelineLegend | null>(null);
  let tooltipPos: { x: number; y: number } | null = $state(null);
  let tooltipText = $state('');
  let showSelectAll = $state(false);
  let nodeMenu: { x: number; y: number; nodeId: number; mode: 'single' | 'multi' } | null = $state(null);
  let edgeMenu: { x: number; y: number; edgeKey: string } | null = $state(null);
  type ActiveModal =
    | { kind: 'monitor'; url: string }
    | RenameModal
    | LabelPickerModal
    | { kind: 'collection'; nodes: GraphNode[] }
    | { kind: 'edge'; mode: 'batch'; nodes: GraphNode[] }
    | { kind: 'edge'; mode: 'sequential'; source: GraphNode; dest: GraphNode }
    | null;
  let activeModal = $state<ActiveModal>(null);
  let pathEdges: Set<string> = new Set();
  let pathCacheKey: string | null = null;
  const MAX_MULTI_PATH_SOURCES = 50;

  const hoverCtrl = createHoverController({
    getGraph: () => graphStore.graph(),
    onRefresh: () => renderer?.refresh(),
    onTooltipChange: (t) => { tooltipText = t; },
    onTooltipPos: (p) => { tooltipPos = p; },
    getNodeDisplayData: (n) => renderer?.getNodeDisplayData(n) ?? null,
  });

  const egoCtrl = createEgoFocusController({ getGraph: () => graphStore.graph() });

  $effect(() => {
    const f = graphStore.egoFocus;
    untrack(() => { if (f) egoCtrl.focusOn(f.nodeId, f.depth); else egoCtrl.unfocus(); });
  });

  const visCtrl = createVisibilityController({
    getGraph: () => graphStore.graph(),
    getReachable: () => egoCtrl.getReachable(),
    filters: {
      get maxHops() { return graphFiltersStore.maxHops; },
      get hideOrphans() { return graphFiltersStore.hideOrphans; },
      get mutualOnly() { return graphFiltersStore.mutualOnly; },
      get showAllEdges() { return graphFiltersStore.showAllEdges; },
      get edgeMode() { return graphFiltersStore.edgeMode; },
    },
    domainVisibility: {
      isHidden: (d) => domainVisibilityStore.isHidden(d),
      isNodeHidden: (id) => domainVisibilityStore.isNodeHidden(id),
    },
    labelFilter: {
      passes: (direct, domain) => labelFilterStore.passes(direct, domain),
    },
  });

  $effect(() => {
    void graphStore.version; void graphStore.egoFocus;
    void graphFiltersStore.maxHops; void graphFiltersStore.hideOrphans;
    void graphFiltersStore.mutualOnly; void graphFiltersStore.showAllEdges;
    void graphFiltersStore.edgeMode;
    void domainVisibilityStore.hidden; void domainVisibilityStore.hiddenNodes;
    void labelFilterStore.include; void labelFilterStore.exclude;
    untrack(() => visCtrl.compute());
  });

  // NodeSet scope: install the active workspace's scope predicate on the
  // visibility controller. Global / collection tabs clear it (all in scope).
  // Tracks openTabs too so reopening a source with refreshed members
  // re-installs even when the active id is unchanged.
  $effect(() => {
    void workspaceStore.activeWorkspaceId; void workspaceStore.openTabs;
    untrack(() => {
      const source = workspaceStore.activeNodeSetSource();
      if (source) {
        const { predicate, includeHidden } = buildNodeSetPredicate(source, {
          isHidden: (d) => domainVisibilityStore.isHidden(d),
          isNodeHidden: (id) => domainVisibilityStore.isNodeHidden(id),
        });
        visCtrl.setScope(predicate, { includeHidden });
      } else {
        visCtrl.setScope(null);
      }
      visCtrl.compute();
      renderer?.refresh();
    });
  });

  visCtrl.subscribe(() =>
    graphStore.setVisibleCounts(visCtrl.getVisibleNodeCount(), visCtrl.getVisibleEdgeCount()),
  );

  const isolateBrightSet = $derived.by<Set<string> | null>(() => {
    void graphStore.version;
    if (!graphFiltersStore.isolate || !graphStore.egoFocus) return null;
    return egoCtrl.getReachable();
  });

  function updatePathForHover(hovered: string | null): void {
    const focus = graphStore.egoFocus;
    const sel = selectionStore.selectedIds;
    const multi = sel.size >= 2 && sel.size <= MAX_MULTI_PATH_SOURCES;
    const sources: number[] = multi ? [...sel]
      : focus?.nodeId != null ? [focus.nodeId]
      : selectionStore.selectedNodeId != null ? [selectionStore.selectedNodeId] : [];
    if (!sources.length || !hovered) { pathEdges = new Set(); pathCacheKey = null; return; }
    const key = multi
      ? `multi:${[...sources].sort((a, b) => a - b).join(',')}:${hovered}`
      : focus ? `${focus.nodeId}:${focus.depth}:${hovered}` : `sel:${sources[0]}:${hovered}`;
    if (pathCacheKey === key) return;
    const reachable = focus ? egoCtrl.getReachable() : visCtrl.getVisibleNodes();
    if (!reachable?.size) { pathEdges = new Set(); pathCacheKey = null; return; }
    const union = new Set<string>();
    const g = graphStore.graph();
    for (const src of sources) {
      if (String(src) === hovered) continue;
      const edges = shortestPathEdges(g, String(src), hovered, reachable);
      if (edges) for (const e of edges) union.add(e);
    }
    pathEdges = union; pathCacheKey = key;
  }

  const reducerCtrl = createReducerController({
    getColorMode: () => graphFiltersStore.colorMode,
    getLabelColor: (raw) =>
      dominantLabelColor(raw.label_ids, raw.domain_label_ids, (id) => labelsStore.byId(id)),
    getFlaggedBorders: () => graphFiltersStore.flaggedBorders,
    getBridgeHighlight: () => graphFiltersStore.bridgeHighlight,
    getBridgeBetweennessMin: () => graphFiltersStore.bridgeBetweennessMin,
    getBridgeInDegreeMin: () => graphFiltersStore.bridgeInDegreeMin,
    getIsolate: () => graphFiltersStore.isolate,
    isVisible: (n) => visCtrl.isVisible(n),
    isEdgeVisible: (e) => visCtrl.isEdgeVisible(e),
    getHoveredNode: () => hoverCtrl.getHoveredNode(),
    getHoverNeighbours: () => hoverCtrl.getHoverNeighbours(),
    getFadeInProgress: () => hoverCtrl.getFadeInProgress(),
    getFadeOutProgress: () => hoverCtrl.getFadeOutProgress(),
    getHeldFrom: () => hoverCtrl.getHeldFrom(),
    getFadeFrom: () => hoverCtrl.getFadeFrom(),
    lerpHex: (f, t, p) => hoverCtrl.lerpHex(f, t, p),
    getEgoFocusNodeId: () => graphStore.egoFocus?.nodeId ?? null,
    getIsolateBrightSet: () => isolateBrightSet,
    getPathEdges: () => pathEdges,
    isSelected: (id) => selectionStore.isSelected(id),
    getSelectedNodeId: () => selectionStore.selectedNodeId,
    getSelectedIds: () => selectionStore.selectedIds,
    getGraphEdge: (e) => { const g = graphStore.graph(); return { source: g.source(e), target: g.target(e) }; },
  });

  const layoutCtrl = createLayoutController(graphLayoutStore.kind, {
    getGraph: () => graphStore.graph(),
    getRenderer: () => renderer,
    onSettlingStart: () => graphLayoutStore.setSettling(true),
    onSettlingEnd: () => graphLayoutStore.setSettling(false),
    onTimelineLegend: (l) => { timelineLegend = l; },
  });

  function lookupNode(id: number) { return graphStore.payload?.nodes.find((n) => n.id === id); }
  function selectedGraphNodes() {
    const p = graphStore.payload; if (!p) return [];
    const s = selectionStore.selectedIds; return p.nodes.filter((n) => s.has(n.id));
  }
  function actFocus(node: GraphNode) {
    graphStore.setEgoFocus({ nodeId: node.id, depth: graphStore.egoFocus?.depth ?? 2 });
    selectionStore.highlight(node.id); renderer?.refresh();
  }
  function openMonitorModal(node: GraphNode) { activeModal = { kind: 'monitor', url: node.raw_url }; }
  function openRenamePopover(node: GraphNode) {
    if (!node.domain || !renderer || !containerEl) return;
    const key = String(node.id); const g = graphStore.graph();
    if (!g.hasNode(key)) return;
    const { x: gx, y: gy } = g.getNodeAttributes(key) as { x: number; y: number };
    const { x: vx, y: vy } = renderer.graphToViewport({ x: gx, y: gy });
    const rect = containerEl.getBoundingClientRect();
    activeModal = renameModal(
      { kind: 'domain', host: node.domain },
      { x: rect.left + vx, y: rect.top + vy },
      node.alias,
    );
  }
  // Anchor the label picker at the node's viewport position, mirroring the
  // rename popover. Labels attach to the resource (node id); current direct
  // ids come off the node payload.
  function openLabelPicker(node: GraphNode) {
    if (!renderer || !containerEl) return;
    const key = String(node.id); const g = graphStore.graph();
    if (!g.hasNode(key)) return;
    const { x: gx, y: gy } = g.getNodeAttributes(key) as { x: number; y: number };
    const { x: vx, y: vy } = renderer.graphToViewport({ x: gx, y: gy });
    const rect = containerEl.getBoundingClientRect();
    activeModal = labelPickerModal(
      { kind: 'resource', resourceId: node.id, name: node.label },
      { x: rect.left + vx, y: rect.top + vy },
      node.label_ids ?? [],
    );
  }
  // Surface fast-path: repaint every node sharing this domain instantly,
  // layered on top of renameTarget()'s shared graph refresh so the new label
  // shows without waiting for the next poll.
  function repaintDomainLabels(target: RenameTarget, alias: string | null) {
    if (target.kind !== 'domain' || alias === null) return;
    const g = graphStore.graph();
    g.forEachNode((n, a) => {
      const r = a.raw as GraphNode | undefined;
      if (!r || r.is_cluster || r.domain !== target.host) return;
      g.setNodeAttribute(n, 'label', alias); r.alias = alias;
    });
    renderer?.refresh();
  }
  function queueAnalysisForNodes(nodes: GraphNode[]) { if (nodes.length) queueAnalysis(selectionFromNodes(nodes), 'Graph selection'); }
  function openCollectionModal(nodes: GraphNode[]) { if (nodes.length) activeModal = { kind: 'collection', nodes }; }
  function openEdgeModal(nodes: GraphNode[]) { if (nodes.length >= 2) activeModal = { kind: 'edge', mode: 'batch', nodes }; }
  async function actDeleteAnalystEdge(edge: GraphEdge) {
    try { await deleteEdge(edge.from, edge.to); toastStore.show('Analyst edge deleted'); void graphPoller.refresh(); }
    catch (err) { toastStore.show(explainApiError(err, 'Delete failed'), 'error'); }
  }
  function selectAllVisible() { selectionStore.replaceCluster([...visCtrl.getVisibleNodes()].map(Number)); }
  // Open the current multi-selection as its own persistent graph tab — the
  // induced subgraph over the selected nodes (NodeSet Workspaces, item 4).
  function openSelectionAsTab(nodes: GraphNode[]) {
    if (nodes.length < 2) return;
    const ids = nodes.map((n) => n.id);
    workspaceStore.openNodeSetTab({ kind: 'selection', nodeIds: ids }, `Selection (${ids.length})`);
  }
  const menuAdapter = createContextMenuAdapter({
    isTorArmed: () => servicesStore.killSwitch.phase === 'armed',
    lookupNode, selectedGraphNodes,
    actCopyUrl, actOpenInTor, actQueueCrawl, actSaveSeedBookmark,
    actFlag, actRemoveFlag, actToggleReviewed,
    actFocus, actHideFromGraph,
    isDomainCollapsed: (d) => graphCollapseStore.isDomainCollapsed(d),
    toggleCollapseDomain: (d) => graphCollapseStore.toggleDomain(d),
    isPinned: (id) => graphPinsStore.has(id),
    actTogglePin,
    openMonitorModal, openRenamePopover, openLabelPicker, queueAnalysisForNodes, openCollectionModal, openEdgeModal,
    openSelectionAsTab,
    actCrawlSelected, actFlagAll, actMarkReviewedAll, actHideAll, actDeleteAnalystEdge,
    lookupEdgeRaw: (k) => graphStore.graph().getEdgeAttribute(k, 'raw') as GraphEdge | undefined,
  });

  const nodeMenuSections = $derived.by(() => {
    if (!nodeMenu) return null; void selectionStore.selectedIds; void graphPinsStore.pinned;
    return menuAdapter.buildNodeMenuSections(nodeMenu, selectionStore.selectedIds);
  });
  const edgeMenuSections = $derived.by(() => {
    if (!edgeMenu) return null; void graphStore.version;
    if (!graphStore.graph().hasEdge(edgeMenu.edgeKey)) return null;
    return menuAdapter.buildEdgeMenuSections(edgeMenu);
  });
  const eventCtrl = createSigmaEventController({
    setHover: (n) => { updatePathForHover(n); hoverCtrl.setHover(n); },
    highlight: (id) => selectionStore.highlight(id),
    toggleCluster: (id) => selectionStore.toggleCluster(id),
    clearSelection: () => selectionStore.clear(),
    multiCount: () => selectionStore.multiCount,
    isSelected: (id) => selectionStore.isSelected(id),
    onNodeClick: () => {
      // Keep the right pane on whatever tab the analyst is using so they can
      // sweep through nodes without losing context. Just surface the pane if
      // it was collapsed.
      if (layoutStore.rightCollapsed) layoutStore.expandRight();
    },
    onNodeMenu: (req) => { nodeMenu = req; },
    onEdgeMenu: (req) => { edgeMenu = req; },
    clearMenus: () => { nodeMenu = null; edgeMenu = null; },
    drawEdgeActive: () => drawEdgeStore.active,
    drawEdgeSource: () => drawEdgeStore.source,
    onDrawEdgeOutcome: (o) => {
      if (o.kind === 'set-source') { drawEdgeStore.setSource(o.node); }
      else if (o.kind === 'open-sequential') {
        drawEdgeStore.cancel();
        activeModal = { kind: 'edge', mode: 'sequential', source: o.source, dest: o.dest };
      }
    },
    toggleDomainExpanded: (d) => graphStore.toggleDomainExpanded(d),
    isGroupByDomain: () => graphFiltersStore.groupByDomain,
    isDomainFoldCollapsed: (d) => graphCollapseStore.isDomainCollapsed(d),
    expandDomainFold: (d) => graphCollapseStore.expandDomain(d),
    expandLabelFold: (id) => graphCollapseStore.expandLabel(id),
    lookupNode,
    lookupNodeDomain: (n) => (graphStore.graph().getNodeAttribute(n, 'raw') as GraphNode | undefined)?.domain,
    lookupEdgeRaw: (k) => graphStore.graph().hasEdge(k)
      ? (graphStore.graph().getEdgeAttribute(k, 'raw') as GraphEdge | undefined) : undefined,
    getNodePayloadCount: (d) => {
      const p = graphStore.payload; if (!p) return 0;
      let c = 0; for (const n of p.nodes) { if (!isUncrawled(n) && n.domain === d && ++c >= 2) break; } return c;
    },
    onEscape: () => {
      if (drawEdgeStore.active) { drawEdgeStore.cancel(); renderer?.refresh(); }
      else if (graphStore.egoFocus) { graphStore.setEgoFocus(null); renderer?.refresh(); }
      else { selectionStore.clear(); renderer?.refresh(); }
    },
    onSelectAll: (count) => { if (count > 50) showSelectAll = true; else { selectAllVisible(); renderer?.refresh(); } },
    onFocusNode: (id) => { const n = lookupNode(id); if (n) actFocus(n); },
    getHoveredNode: () => hoverCtrl.getHoveredNode(),
    visibleNodeCount: () => visCtrl.getVisibleNodeCount(),
    selectedNodeId: () => selectionStore.selectedNodeId,
    setNodePosition: (id, x, y) => { const g = graphStore.graph(); g.setNodeAttribute(id, 'x', x); g.setNodeAttribute(id, 'y', y); },
    setNodeUserPositioned: (id) => graphStore.graph().setNodeAttribute(id, 'userPositioned', true),
    refresh: () => renderer?.refresh(),
    onAfterRender: () => hoverCtrl.updateTooltipPos(),
  });

  function countFetchedNodes(g: Graph): number {
    let n = 0;
    g.forEachNode((_nd, a) => { const r = a.raw as GraphNode | undefined; if (r && !isUncrawled(r)) n++; });
    return n;
  }
  function applyPayloadAndLayout(): void {
    if (!renderer || graphStore.version === lastAppliedVersion) return;
    lastAppliedVersion = graphStore.version;
    const g = graphStore.graph();
    const uncrawledChanged = prevShowUncrawled !== graphFiltersStore.showUncrawled;
    prevShowUncrawled = graphFiltersStore.showUncrawled;
    const fetchedCount = countFetchedNodes(g);
    if (!firstLayoutDone && fetchedCount > 0 && fetchedCount <= MAX_AUTO_LAYOUT_NODES) {
      firstLayoutDone = true; layoutCtrl.setLayoutKind(graphLayoutStore.kind); layoutCtrl.relayout(); return;
    }
    if (!firstLayoutDone && fetchedCount > MAX_AUTO_LAYOUT_NODES) {
      firstLayoutDone = true;
      toastStore.show(`Graph too large for auto-layout (${fetchedCount.toLocaleString()} fetched nodes). Existing positions kept; click Reset to force a layout.`, 'warn');
    } else if (!firstLayoutDone && fetchedCount === 0 && g.order > 0) {
      // No fetched nodes to lay out, but there ARE nodes to show — e.g.
      // "Add to Graph" on a fresh project yields an all-uncrawled graph.
      // FA2 has no topology to spread here, but we must still frame the
      // camera, or the node(s) sit off-screen at their seed coords and the
      // canvas looks empty even as the node count rises.
      firstLayoutDone = true;
      fitView(renderer);
    } else if (uncrawledChanged) {
      positionStubsAroundParents(g);
      positionOrphanStubsOutside(g);
    }
    renderer.refresh();
  }
  function mountRenderer(): void {
    if (!containerEl || webglError !== null) return;
    if (!webglProbed) { webglProbed = true; const err = probeWebGL(); if (err) { webglError = err; return; } }
    renderer = createGraphRenderer(graphStore.graph(), containerEl, {
      nodeReducer: (n, d) => reducerCtrl.nodeReducer(n, d),
      edgeReducer: (e, d) => reducerCtrl.edgeReducer(e, d),
    });
    eventCtrl.bind(renderer);
  }
  onMount(() => {
    workspaceSnapshots.registerCameraGetter(() => renderer?.getCamera().getState() ?? null);
    mountRenderer(); applyPayloadAndLayout();
    const onVis = () => { if (document.visibilityState !== 'visible') return; egoCtrl.invalidateCache(); renderer?.refresh(); void graphPoller.refresh(); };
    const onFocus = () => { egoCtrl.invalidateCache(); renderer?.refresh(); };
    document.addEventListener('visibilitychange', onVis);
    window.addEventListener('focus', onFocus);
    return () => {
      document.removeEventListener('visibilitychange', onVis);
      window.removeEventListener('focus', onFocus);
      hoverCtrl.dispose(); layoutCtrl.dispose(); eventCtrl.unbind(); renderer?.kill(); renderer = null;
    };
  });

  onDestroy(() => { workspaceSnapshots.unregisterCameraGetter(); layoutCtrl.cancelLayout(); });
  $effect(() => {
    const v = graphStore.version;
    if (v === lastAppliedVersion || !renderer) return;
    untrack(() => {
      applyPayloadAndLayout(); egoCtrl.invalidateCache();
      showFirstVisitSkeleton = false; pathEdges = new Set(); pathCacheKey = null;
      const { restored, camera } = workspaceSnapshots.consumePending();
      if (restored) restoreView(renderer!, camera);
    });
  });

  $effect(() => { void workspaceSnapshots.version; if (!renderer) return; untrack(() => renderer!.refresh()); });
  $effect(() => {
    const id = workspaceStore.activeWorkspaceId;
    untrack(() => { if (!workspaceSnapshots.hasCachedPayload(id)) showFirstVisitSkeleton = true; });
  });
  $effect(() => { void fitToken; untrack(() => { if (renderer) fitView(renderer); }); });
  $effect(() => {
    void resetToken; if (!renderer) return;
    untrack(() => { lastAppliedVersion = -1; firstLayoutDone = false; layoutCtrl.setLayoutKind(graphLayoutStore.kind); layoutCtrl.relayout(); });
  });
  $effect(() => {
    void graphLayoutStore.runToken; if (!renderer) return;
    untrack(() => { lastAppliedVersion = -1; firstLayoutDone = false; layoutCtrl.setLayoutKind(graphLayoutStore.kind); layoutCtrl.relayout(); });
  });
  $effect(() => { void graphLayoutStore.stopToken; untrack(() => layoutCtrl.stopLayout()); });
  $effect(() => {
    if (!drawEdgeStore.requestToken) return;
    untrack(() => {
      const o = resolveDrawEdgeRequest(selectionStore.multiCount);
      if (o.kind === 'open-batch-modal') openEdgeModal(selectedGraphNodes()); else drawEdgeStore.begin();
    });
  });
  $effect(() => {
    void selectionStore.selectedIds; void selectionStore.selectedNodeId;
    untrack(() => { pathCacheKey = null; updatePathForHover(hoverCtrl.getHoveredNode()); renderer?.refresh(); });
  });
  $effect(() => {
    void graphStore.egoFocus;
    untrack(() => { egoCtrl.invalidateCache(); pathEdges = new Set(); pathCacheKey = null; renderer?.refresh(); });
  });
  $effect(() => {
    void graphFiltersStore.showUncrawled; if (!renderer) return;
    untrack(() => { prevShowUncrawled = !graphFiltersStore.showUncrawled; graphStore.rebuildFromCurrentPayload(); });
  });
  // Pin set changed (Add to Graph / Add all / Unpin) — rebuild so newly-pinned
  // uncrawled nodes enter the graph and unpinned ones leave, without touching
  // the global showUncrawled toggle.
  $effect(() => {
    void graphPinsStore.pinned; if (!renderer) return;
    untrack(() => graphStore.rebuildFromCurrentPayload());
  });
  $effect(() => {
    void graphFiltersStore.groupByDomain; if (!renderer) return;
    untrack(() => {
      if (!graphFiltersStore.groupByDomain && graphStore.expandedDomains.size > 0) graphStore.clearExpandedDomains();
      else graphStore.rebuildFromCurrentPayload();
    });
  });
  // Selective collapse axes (Phase 3d) for the active tab changed — rebuild so
  // the new domain/label folds materialise. Tracks both fold sets; a tab switch
  // (which moves these getters) is already covered by the payload re-apply.
  $effect(() => {
    void graphCollapseStore.domains; void graphCollapseStore.labels; if (!renderer) return;
    untrack(() => graphStore.rebuildFromCurrentPayload());
  });
  $effect(() => {
    void graphFiltersStore.maxHops; void graphFiltersStore.hideOrphans;
    void graphFiltersStore.mutualOnly; void graphFiltersStore.showAllEdges;
    void graphFiltersStore.edgeMode; void graphFiltersStore.colorMode;
    void graphFiltersStore.flaggedBorders; void graphFiltersStore.isolate;
    void graphFiltersStore.bridgeHighlight; void graphFiltersStore.bridgeBetweennessMin;
    void graphFiltersStore.bridgeInDegreeMin;
    // Label catalog + filter: recolour (color-by-label) and refilter repaint.
    void labelsStore.labels;
    void labelFilterStore.include; void labelFilterStore.exclude;
    if (!renderer) return; untrack(() => renderer!.refresh());
  });
</script>

<div class="wrap">
  <div class="sigma" bind:this={containerEl}></div>
  {#if webglError}
    <div class="webgl-error" role="alert"><p>{webglError}</p></div>
  {/if}
  {#if graphLayoutStore.kind === 'timeline' && timelineLegend}
    <div class="timeline-legend" aria-live="polite">
      {#if timelineLegend.minDate}
        <span class="tl-range">{timelineLegend.minDate} → {timelineLegend.maxDate}</span>
        <span class="tl-sep">·</span><span>{timelineLegend.dayCount} days</span>
      {:else}<span>No dated nodes</span>{/if}
      {#if timelineLegend.undatedCount > 0}<span class="tl-sep">·</span><span>{timelineLegend.undatedCount} undated</span>{/if}
    </div>
  {/if}
  {#if tooltipPos && tooltipText}
    <GraphTooltip x={tooltipPos.x} y={tooltipPos.y} text={tooltipText} />
  {/if}
  {#if graphStore.egoFocus}
    <EgoFocusOverlay
      onExit={() => { graphStore.setEgoFocus(null); renderer?.refresh(); }}
      onDepthChange={(d) => { graphStore.setEgoDepth(d); renderer?.refresh(); }}
    />
  {/if}
  {#if showSelectAll}
    <SelectAllConfirm
      count={visCtrl.getVisibleNodeCount()}
      onConfirm={() => { showSelectAll = false; selectAllVisible(); renderer?.refresh(); }}
      onCancel={() => (showSelectAll = false)}
    />
  {/if}
  {#if nodeMenu && nodeMenuSections}
    <ContextMenu x={nodeMenu.x} y={nodeMenu.y} sections={nodeMenuSections} onClose={() => (nodeMenu = null)} />
  {/if}
  {#if edgeMenu && edgeMenuSections}
    <ContextMenu x={edgeMenu.x} y={edgeMenu.y} sections={edgeMenuSections} onClose={() => (edgeMenu = null)} />
  {/if}
  {#if showFirstVisitSkeleton && graphStore.loading}
    <div class="workspace-skeleton" aria-label="Loading workspace">
      <span class="workspace-skeleton-dot"></span>Loading workspace…
    </div>
  {/if}
</div>

{#if activeModal?.kind === 'rename'}
  {@const rename = activeModal}
  <RenameAliasPopover x={rename.x} y={rename.y} target={rename.target}
    currentName={rename.currentName} onClose={() => (activeModal = null)}
    onSave={async (alias) => {
      await renameTarget(rename.target, alias);
      repaintDomainLabels(rename.target, alias);
    }} />
{:else if activeModal?.kind === 'labelPicker'}
  {@const picker = activeModal}
  <LabelPickerPopover x={picker.x} y={picker.y} target={picker.target}
    currentIds={picker.currentIds} onClose={() => (activeModal = null)}
    onChanged={() => void graphPoller.refresh()} />
{:else if activeModal?.kind === 'monitor'}
  <AddMonitorModal url={activeModal.url} onClose={() => (activeModal = null)} />
{:else if activeModal?.kind === 'collection'}
  <CollectionPickerModal
    nodeIds={activeModal.nodes.map((n) => n.id)}
    onClose={() => (activeModal = null)} />
{:else if activeModal?.kind === 'edge' && activeModal.mode === 'batch'}
  <DrawAnalystEdgeModal mode="batch" nodes={activeModal.nodes}
    onClose={() => (activeModal = null)} onCreated={() => void graphPoller.refresh()} />
{:else if activeModal?.kind === 'edge' && activeModal.mode === 'sequential'}
  <DrawAnalystEdgeModal mode="sequential" source={activeModal.source} dest={activeModal.dest}
    onClose={() => (activeModal = null)} onCreated={() => void graphPoller.refresh()} />
{/if}

<style>
  .wrap { position: relative; width: 100%; height: 100%; overflow: hidden; }
  .sigma { position: absolute; inset: 0; }
  .webgl-error {
    position: absolute; inset: 12px; display: flex; align-items: center;
    justify-content: center; padding: 16px; border: 1px solid var(--border);
    background: var(--bg); color: var(--text); font-size: 12px; line-height: 1.5; z-index: 10;
  }
  .webgl-error p { max-width: 560px; margin: 0; }
  .timeline-legend {
    position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%);
    display: flex; align-items: center; gap: 6px; padding: 3px 10px;
    border: 1px solid var(--border); border-radius: 10px; background: var(--bg);
    color: var(--muted); font-size: 10px; white-space: nowrap; pointer-events: none; z-index: 8;
  }
  .timeline-legend .tl-range { color: var(--accent); }
  .timeline-legend .tl-sep { opacity: 0.5; }
  .workspace-skeleton {
    position: absolute; inset: 0; display: flex; align-items: center;
    justify-content: center; gap: 8px; background: rgba(10, 15, 13, 0.75);
    color: var(--muted); font-size: 12px; z-index: 5; pointer-events: none;
  }
  .workspace-skeleton-dot {
    width: 6px; height: 6px; border-radius: 50%; background: var(--accent);
    animation: skeleton-pulse 1.2s ease-in-out infinite;
  }
  @keyframes skeleton-pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
</style>
