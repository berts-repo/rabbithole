// Sigma event controller — Sigma event binding lifecycle.
//
// Owns: event binding setup/teardown for a Sigma renderer instance.
// Translates Sigma events → app actions: selection, context menu, drag,
// double-click, keyboard. Drag handling stays here for v1 (no separate
// dragController).
//
// Plain TypeScript — no Svelte $state.

import type Sigma from 'sigma';
import type { GraphNode, GraphEdge } from '$lib/api';
import { isClusterKey, clusterDomain } from '$lib/graph/model/clusterDomain';
import { isLabelClusterKey, labelClusterId } from '$lib/graph/model/clusterLabel';
import { classifyGraphKey } from '$lib/graph/interactions/keyboard';
import { isMultiSelectModifier, shouldOpenMultiMenu } from '$lib/graph/interactions/selection';
import { resolveDrawEdgeClick } from '$lib/graph/interactions/drawEdge';

const DRAG_THRESHOLD_PX = 4;
const TERMINAL_TARGET_SELECTOR = [
  '.xterm',
  '.terminal',
  '.codex-terminal',
  '[data-terminal]',
  '[data-codex-terminal]',
  '[role="terminal"]',
].join(',');

export interface NodeMenuRequest {
  x: number;
  y: number;
  nodeId: number;
  mode: 'single' | 'multi';
}

export interface EdgeMenuRequest {
  x: number;
  y: number;
  edgeKey: string;
}

export type DrawEdgeOutcome =
  | { kind: 'set-source'; node: GraphNode }
  | { kind: 'open-sequential'; source: GraphNode; dest: GraphNode };

export interface SigmaEventControllerDeps {
  // Hover
  setHover(node: string | null): void;
  // Selection
  highlight(nodeId: number): void;
  toggleCluster(nodeId: number): void;
  clearSelection(): void;
  multiCount(): number;
  isSelected(id: number): boolean;
  // Navigation (called on plain left-click)
  onNodeClick(nodeId: number): void;
  // Context menus
  onNodeMenu(req: NodeMenuRequest): void;
  onEdgeMenu(req: EdgeMenuRequest): void;
  clearMenus(): void;
  // Draw-edge
  drawEdgeActive(): boolean;
  drawEdgeSource(): GraphNode | null;
  onDrawEdgeOutcome(outcome: DrawEdgeOutcome): void;
  // Ego focus / domain toggle
  toggleDomainExpanded(domain: string): void;
  isGroupByDomain(): boolean;
  // Phase 3d collapse (D7). A domain double-click expands the persisted
  // selective fold when one exists, else toggles the transient groupByDomain
  // exception; a label-cluster double-click un-collapses that label.
  isDomainFoldCollapsed(domain: string): boolean;
  expandDomainFold(domain: string): void;
  expandLabelFold(labelId: number): void;
  // Node lookup
  lookupNode(id: number): GraphNode | undefined;
  lookupNodeDomain(node: string): string | null | undefined;
  lookupEdgeRaw(edgeKey: string): GraphEdge | undefined;
  getNodePayloadCount(domain: string): number;
  // Keyboard actions
  onEscape(): void;
  onSelectAll(visibleCount: number): void;
  onFocusNode(nodeId: number): void;
  getHoveredNode(): string | null;
  visibleNodeCount(): number;
  selectedNodeId(): number | null;
  // Graph mutation (drag)
  setNodePosition(nodeId: string, x: number, y: number): void;
  setNodeUserPositioned(nodeId: string): void;
  // Renderer refresh (called by the controller to force a repaint)
  refresh(): void;
  // After-render tooltip position update
  onAfterRender(): void;
  // Optional: window/document overrides for testing
  addEventListener?: typeof window.addEventListener;
  removeEventListener?: typeof window.removeEventListener;
}

export interface SigmaEventController {
  /** Bind all events to the renderer. Call once after Sigma is mounted. */
  bind(renderer: Sigma): void;
  /** Remove all event bindings and clean up listeners. */
  unbind(): void;
}

export function createSigmaEventController(deps: SigmaEventControllerDeps): SigmaEventController {
  let renderer: Sigma | null = null;
  let dragNode: string | null = null;
  let dragStartViewport: { x: number; y: number } | null = null;
  let dragHappened = false;

  const addEvt = deps.addEventListener ?? window.addEventListener.bind(window);
  const removeEvt = deps.removeEventListener ?? window.removeEventListener.bind(window);

  function isTerminalTarget(t: HTMLElement | null): boolean {
    return !!(
      t &&
      typeof t.closest === 'function' &&
      t.closest(TERMINAL_TARGET_SELECTOR)
    );
  }

  function onKey(e: KeyboardEvent): void {
    const t = e.target as HTMLElement | null;
    if (isTerminalTarget(t)) return;
    const inTextEntry = !!(
      t &&
      (t.tagName === 'INPUT' ||
        t.tagName === 'TEXTAREA' ||
        t.isContentEditable)
    );
    const intent = classifyGraphKey({
      key: e.key,
      ctrlKey: e.ctrlKey,
      metaKey: e.metaKey,
      altKey: e.altKey,
      inTextEntry,
    });
    if (intent === 'escape') {
      deps.onEscape();
      return;
    }
    if (intent === 'select-all') {
      e.preventDefault();
      deps.onSelectAll(deps.visibleNodeCount());
      return;
    }
    if (intent === 'focus-node') {
      let id: number | null = null;
      const hovered = deps.getHoveredNode();
      if (hovered !== null && !isClusterKey(hovered)) {
        id = Number(hovered);
      } else {
        id = deps.selectedNodeId();
      }
      if (id === null) return;
      const node = deps.lookupNode(id);
      if (!node) return;
      e.preventDefault();
      deps.onFocusNode(id);
    }
  }

  function bind(sig: Sigma): void {
    renderer = sig;

    sig.on('enterNode', ({ node }) => deps.setHover(node));
    sig.on('leaveNode', () => deps.setHover(null));

    sig.on('clickNode', ({ node, event }) => {
      if (dragHappened) {
        dragHappened = false;
        return;
      }
      if (deps.drawEdgeActive()) {
        const isCluster = isClusterKey(node);
        const picked = isCluster ? undefined : deps.lookupNode(Number(node));
        const outcome = resolveDrawEdgeClick(isCluster, picked, deps.drawEdgeSource());
        if (outcome.kind === 'set-source') {
          deps.onDrawEdgeOutcome({ kind: 'set-source', node: outcome.node });
        } else if (outcome.kind === 'open-sequential') {
          deps.onDrawEdgeOutcome({ kind: 'open-sequential', source: outcome.source, dest: outcome.dest });
        }
        if (picked) deps.refresh();
        return;
      }
      if (isClusterKey(node)) return;
      const id = Number(node);
      // Guard typeof MouseEvent for node test environments.
      const native =
        typeof MouseEvent !== 'undefined' && event.original instanceof MouseEvent
          ? event.original
          : (event.original as { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean } | null);
      const multi = isMultiSelectModifier(native);
      if (multi) {
        deps.toggleCluster(id);
      } else {
        deps.highlight(id);
        deps.onNodeClick(id);
      }
      deps.refresh();
    });

    sig.on('rightClickNode', ({ node, event }) => {
      event.preventSigmaDefault();
      event.original?.preventDefault?.();
      if (isClusterKey(node)) return;
      const id = Number(node);
      const inMulti = shouldOpenMultiMenu(deps.multiCount(), deps.isSelected(id));
      deps.clearMenus();
      deps.onNodeMenu({
        x: event.x,
        y: event.y,
        nodeId: id,
        mode: inMulti ? 'multi' : 'single',
      });
    });

    sig.on('rightClickEdge', ({ edge, event }) => {
      event.preventSigmaDefault();
      event.original?.preventDefault?.();
      const raw = deps.lookupEdgeRaw(edge);
      if (!raw || raw.source !== 'analyst') return;
      deps.clearMenus();
      deps.onEdgeMenu({ x: event.x, y: event.y, edgeKey: edge });
    });

    sig.on('doubleClickNode', ({ node, event }) => {
      event.preventSigmaDefault();
      if (isLabelClusterKey(node)) {
        deps.expandLabelFold(labelClusterId(node));
        return;
      }
      if (isClusterKey(node)) {
        const domain = clusterDomain(node);
        // A persisted selective fold expands persistently; otherwise this is a
        // groupByDomain fold, toggled via the transient exception set.
        if (deps.isDomainFoldCollapsed(domain)) deps.expandDomainFold(domain);
        else deps.toggleDomainExpanded(domain);
        return;
      }
      if (!deps.isGroupByDomain()) return;
      const domain = deps.lookupNodeDomain(node);
      if (!domain) return;
      const fetched = deps.getNodePayloadCount(domain);
      if (fetched < 2) return;
      deps.toggleDomainExpanded(domain);
    });

    sig.on('clickStage', () => {
      deps.clearSelection();
      deps.refresh();
    });

    // Drag-to-move
    sig.on('downNode', ({ node, event }) => {
      // Guard typeof MouseEvent for node test environments.
      const origAsButton = event.original as { button?: number } | null;
      if (
        typeof MouseEvent !== 'undefined' &&
        event.original instanceof MouseEvent &&
        event.original.button !== 0
      ) {
        return;
      }
      // Non-browser env: if a button field is present and non-zero, skip.
      if (
        typeof MouseEvent === 'undefined' &&
        origAsButton !== null &&
        origAsButton?.button !== undefined &&
        origAsButton.button !== 0
      ) {
        return;
      }
      dragNode = node;
      dragStartViewport = { x: event.x, y: event.y };
      dragHappened = false;
    });

    const mouseCaptor = sig.getMouseCaptor();
    mouseCaptor.on('mousemovebody', (event) => {
      if (!dragNode || !dragStartViewport || !renderer) return;
      const dx = event.x - dragStartViewport.x;
      const dy = event.y - dragStartViewport.y;
      if (!dragHappened && Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return;
      if (!dragHappened) {
        dragHappened = true;
        renderer.getCamera().disable();
      }
      const coords = renderer.viewportToGraph({ x: event.x, y: event.y });
      deps.setNodePosition(dragNode, coords.x, coords.y);
      event.preventSigmaDefault();
      event.original?.preventDefault?.();
      event.original?.stopPropagation?.();
    });

    mouseCaptor.on('mouseup', () => {
      if (dragHappened && dragNode && renderer) {
        deps.setNodeUserPositioned(dragNode);
        renderer.getCamera().enable();
      }
      dragNode = null;
      dragStartViewport = null;
    });

    sig.on('afterRender', () => {
      deps.onAfterRender();
    });

    (addEvt as typeof document.addEventListener)('keydown', onKey as EventListener);
  }

  function unbind(): void {
    (removeEvt as typeof document.removeEventListener)('keydown', onKey as EventListener);
    renderer = null;
    dragNode = null;
    dragStartViewport = null;
    dragHappened = false;
  }

  return { bind, unbind };
}
