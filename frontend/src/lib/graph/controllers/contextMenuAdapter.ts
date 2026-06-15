// Context menu adapter — click/right-click → context-menu state.
//
// Owns: mapping graph click/right-click events to context-menu section specs.
// Connects to the existing $lib/contextMenu/* system (buildSingleTargetSections,
// buildMultiSelectSections) and the action wiring (act*/openModal functions).
//
// Does NOT modify actions.ts. Reads from contextMenu/* but owns no state.
// Plain TypeScript — no Svelte $state.

import {
  buildMultiSelectSections,
  buildSingleTargetSections,
  type MenuSection,
  type MultiSelectMenuHandlers,
  type SingleTargetMenuHandlers,
} from '$lib/contextMenu';
import type { GraphNode, GraphEdge } from '$lib/api';

// ---- Types re-exported for consumers ----

export type { MenuSection };

export interface NodeMenuState {
  x: number;
  y: number;
  nodeId: number;
  mode: 'single' | 'multi';
}

export interface EdgeMenuState {
  x: number;
  y: number;
  edgeKey: string;
}

// ---- Deps ----

export interface ContextMenuAdapterDeps {
  // Tor state
  isTorArmed(): boolean;
  // Node lookup
  lookupNode(id: number): GraphNode | undefined;
  selectedGraphNodes(): GraphNode[];
  // Single-node actions
  actCopyUrl(url: string): void | Promise<void>;
  actOpenInTor(nodeId: number): void | Promise<void>;
  actQueueCrawl(url: string): void | Promise<void>;
  actSaveSeedBookmark(url: string): void | Promise<void>;
  actFlag(nodeId: number, priority: number): void | Promise<void>;
  actRemoveFlag(nodeId: number): void | Promise<void>;
  actToggleReviewed(nodeId: number, currentReviewed: boolean): void | Promise<void>;
  actFocus(node: GraphNode): void;
  actHideFromGraph(url: string): void | Promise<void>;
  // Phase 3d collapse (D7) — fold/unfold a whole domain on the active tab, and
  // the current fold state for the Collapse/Expand label.
  isDomainCollapsed(domain: string): boolean;
  toggleCollapseDomain(domain: string): void;
  // Pin state + toggle for the node menu's Pin/Unpin row (uncrawled nodes).
  isPinned(nodeId: number): boolean;
  actTogglePin(nodeId: number): void;
  openMonitorModal(node: GraphNode): void;
  openRenamePopover(node: GraphNode): void;
  openLabelPicker(node: GraphNode): void;
  // Funnels the nodes to the Intel compose form (no modal); see actions.ts.
  queueAnalysisForNodes(nodes: GraphNode[]): void;
  // Multi-select actions
  openCollectionModal(nodes: GraphNode[]): void;
  openEdgeModal(nodes: GraphNode[]): void;
  openSelectionAsTab(nodes: GraphNode[]): void;
  actCrawlSelected(nodes: GraphNode[]): void | Promise<void>;
  actFlagAll(nodes: GraphNode[]): void | Promise<void>;
  actMarkReviewedAll(nodes: GraphNode[]): void | Promise<void>;
  actHideAll(nodes: GraphNode[]): void | Promise<void>;
  // Edge actions
  actDeleteAnalystEdge(edge: GraphEdge): Promise<void>;
  lookupEdgeRaw(edgeKey: string): GraphEdge | undefined;
}

export interface ContextMenuAdapter {
  /**
   * Build sections for a node context menu.
   * Returns null if the node can't be found or has no menu.
   */
  buildNodeMenuSections(state: NodeMenuState, selectedIds: ReadonlySet<number>): MenuSection[] | null;
  /**
   * Build sections for an edge context menu.
   * Returns null if the edge is not found or is not an analyst edge.
   */
  buildEdgeMenuSections(state: EdgeMenuState): MenuSection[] | null;
}

export function createContextMenuAdapter(deps: ContextMenuAdapterDeps): ContextMenuAdapter {
  function singleNodeHandlers(node: GraphNode): SingleTargetMenuHandlers {
    return {
      copyUrl: () => deps.actCopyUrl(node.raw_url),
      openInTor: () => deps.actOpenInTor(node.id),
      queueCrawl: () => deps.actQueueCrawl(node.raw_url),
      saveSeedBookmark: () => deps.actSaveSeedBookmark(node.raw_url),
      flag: (priority) => deps.actFlag(node.id, priority),
      removeFlag: () => deps.actRemoveFlag(node.id),
      toggleReviewed: () => deps.actToggleReviewed(node.id, !!node.reviewed),
      addMonitor: () => deps.openMonitorModal(node),
      renameAlias: () => deps.openRenamePopover(node),
      applyLabels: () => deps.openLabelPicker(node),
      queueAnalysis: () => deps.queueAnalysisForNodes([node]),
      addToCollection: () => deps.openCollectionModal([node]),
      focus: () => deps.actFocus(node),
      toggleCollapseDomain: node.domain
        ? () => deps.toggleCollapseDomain(node.domain as string)
        : undefined,
      hideFromGraph: () => deps.actHideFromGraph(node.raw_url),
      togglePin: () => deps.actTogglePin(node.id),
    };
  }

  function multiSelectHandlers(nodes: GraphNode[]): MultiSelectMenuHandlers {
    return {
      addToCollection: () => deps.openCollectionModal(nodes),
      drawEdge: () => deps.openEdgeModal(nodes),
      openAsTab: () => deps.openSelectionAsTab(nodes),
      crawlSelected: () => deps.actCrawlSelected(nodes),
      flagAll: () => deps.actFlagAll(nodes),
      markReviewedAll: () => deps.actMarkReviewedAll(nodes),
      queueAnalysis: () => deps.queueAnalysisForNodes(nodes),
      hideAll: () => deps.actHideAll(nodes),
    };
  }

  function buildNodeMenuSections(
    state: NodeMenuState,
    _selectedIds: ReadonlySet<number>,
  ): MenuSection[] | null {
    if (state.mode === 'multi') {
      const nodes = deps.selectedGraphNodes();
      return buildMultiSelectSections(nodes, multiSelectHandlers(nodes));
    }
    const node = deps.lookupNode(state.nodeId);
    if (!node) return null;
    // Spread so the builder still sees every GraphNode field (state, domain,
    // flag_status…) and layer the pin flag on top for the Pin/Unpin label.
    return buildSingleTargetSections(
      { ...node, pinned: deps.isPinned(node.id) },
      {
        torArmed: deps.isTorArmed(),
        domainCollapsed: !!node.domain && deps.isDomainCollapsed(node.domain),
      },
      singleNodeHandlers(node),
    );
  }

  function buildEdgeMenuSections(state: EdgeMenuState): MenuSection[] | null {
    const raw = deps.lookupEdgeRaw(state.edgeKey);
    if (!raw || raw.source !== 'analyst') return null;
    return [
      {
        items: [
          {
            label: 'Delete analyst edge',
            onSelect: () => deps.actDeleteAnalystEdge(raw),
          },
        ],
      },
    ];
  }

  return { buildNodeMenuSections, buildEdgeMenuSections };
}
