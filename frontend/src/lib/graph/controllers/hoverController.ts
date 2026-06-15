// Hover controller — hovered node id + animated fade map.
//
// Owns: hoveredNode | null, hoverNeighbours, fade timing state,
//       hold-dim state, fade rAF loop.
// Exposes: setHover(nodeId | null), getHoveredNode(), getHoverNeighbours(),
//          getFadeInProgress(), getFadeOutProgress(), getHeldFrom(),
//          getFadeFrom(), lerpHex(), subscribe().
//
// Pure TypeScript — no Svelte $state. GraphCanvas wraps the subscribe
// callback in an $effect and drives renderer.refresh() from there.

import type Graph from 'graphology';

export interface HoverState {
  hoveredNode: string | null;
  hoverNeighbours: Set<string>;
}

export interface FadeFromState {
  node: string;
  neighbours: Set<string>;
  startTs: number;
}

export interface HeldFromState {
  node: string;
  neighbours: Set<string>;
}

export interface HoverControllerDeps {
  /** Returns the current graphology instance (called on each hover). */
  getGraph: () => Graph;
  /** Called when a refresh of the Sigma renderer is needed. */
  onRefresh: () => void;
  /** Called when tooltip text changes (node label / title). */
  onTooltipChange: (text: string) => void;
  /** Called with viewport coords when tooltip position should update. */
  onTooltipPos: (pos: { x: number; y: number } | null) => void;
  /** Called to get current node display data (viewport coords). */
  getNodeDisplayData: (node: string) => { x: number; y: number } | null;
  /**
   * Optional override for requestAnimationFrame (for testing in non-browser
   * environments). Defaults to the global requestAnimationFrame.
   */
  requestAnimationFrame?: (cb: FrameRequestCallback) => number;
  /**
   * Optional override for cancelAnimationFrame (for testing).
   */
  cancelAnimationFrame?: (id: number) => void;
  /**
   * Optional override for window.setTimeout (for testing).
   */
  setTimeout?: (fn: () => void, ms: number) => number;
  /**
   * Optional override for clearTimeout (for testing).
   */
  clearTimeout?: (id: number) => void;
}

export interface HoverController {
  /** Transition hover state to the given node (or null to leave). */
  setHover(node: string | null): void;
  /** Update path-edge cache key and re-derive the tooltip position. */
  updateTooltipPos(): void;
  /** The currently hovered node id, or null. */
  getHoveredNode(): string | null;
  /** Neighbour set of the hovered node (O(1) membership test). */
  getHoverNeighbours(): Set<string>;
  /** 0 = baseline, 1 = fully dimmed. Active on fade-in. */
  getFadeInProgress(): number;
  /** 0 = still dimmed (just left), 1 = back to baseline. Active on fade-out. */
  getFadeOutProgress(): number;
  /** The held-from state while in the dim-hold window. */
  getHeldFrom(): HeldFromState | null;
  /** The fade-out origin while the brighten-out ramp is animating. */
  getFadeFrom(): FadeFromState | null;
  /** Interpolate two #rrggbb hex colours. */
  lerpHex(from: string, to: string, t: number): string;
  /** Register a listener called on every state change. Returns unsub fn. */
  subscribe(listener: () => void): () => void;
  /** Clean up timers and rAF loop. */
  dispose(): void;
}

const FADE_DURATION_MS = 500;
const FADE_OUT_DURATION_MS = 350;
const HOLD_MS = 250;

export function createHoverController(deps: HoverControllerDeps): HoverController {
  // Platform abstractions — injectable for testing in node environments.
  const raf: (cb: FrameRequestCallback) => number =
    deps.requestAnimationFrame ?? ((cb) => requestAnimationFrame(cb));
  const caf: (id: number) => void =
    deps.cancelAnimationFrame ?? ((id) => cancelAnimationFrame(id));
  const setTO: (fn: () => void, ms: number) => number =
    deps.setTimeout ?? ((fn, ms) => window.setTimeout(fn, ms));
  const clearTO: (id: number) => void =
    deps.clearTimeout ?? ((id) => clearTimeout(id));

  let hoveredNode: string | null = null;
  let hoverNeighbours: Set<string> = new Set();

  // Fade-in timing
  let hoverStartTs: number | null = null;
  // Fade-out state
  let fadeFrom: FadeFromState | null = null;
  // Hold-dim state
  let heldFrom: HeldFromState | null = null;
  let holdTimerId: number | null = null;
  // rAF loop
  let fadeRafId: number | null = null;

  const listeners = new Set<() => void>();

  function notify(): void {
    for (const l of listeners) l();
  }

  function lerpHex(from: string, to: string, t: number): string {
    const fr = parseInt(from.slice(1, 3), 16);
    const fg = parseInt(from.slice(3, 5), 16);
    const fb = parseInt(from.slice(5, 7), 16);
    const tr = parseInt(to.slice(1, 3), 16);
    const tg = parseInt(to.slice(3, 5), 16);
    const tb = parseInt(to.slice(5, 7), 16);
    const r = Math.round(fr + (tr - fr) * t);
    const g = Math.round(fg + (tg - fg) * t);
    const b = Math.round(fb + (tb - fb) * t);
    return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
  }

  function getFadeInProgress(): number {
    if (hoverStartTs === null) return 1;
    return Math.min(1, (performance.now() - hoverStartTs) / FADE_DURATION_MS);
  }

  function getFadeOutProgress(): number {
    if (!fadeFrom) return 1;
    return Math.min(1, (performance.now() - fadeFrom.startTs) / FADE_OUT_DURATION_MS);
  }

  function tickFade(): void {
    if (hoverStartTs !== null && getFadeInProgress() >= 1) {
      hoverStartTs = null;
    }
    if (fadeFrom !== null && getFadeOutProgress() >= 1) {
      fadeFrom = null;
    }
    const inActive = hoverStartTs !== null;
    const outActive = fadeFrom !== null;
    deps.onRefresh();
    if (!inActive && !outActive) {
      fadeRafId = null;
      return;
    }
    fadeRafId = raf(tickFade);
  }

  function startFadeLoop(): void {
    if (fadeRafId === null) {
      fadeRafId = raf(tickFade);
    }
  }

  function setHover(node: string | null): void {
    const prev = hoveredNode;
    const prevNbrs = hoverNeighbours;

    if (!node) {
      hoveredNode = null;
      hoverNeighbours = new Set();
      hoverStartTs = null;
      deps.onTooltipChange('');
      deps.onTooltipPos(null);
      if (prev) {
        heldFrom = { node: prev, neighbours: prevNbrs };
        if (holdTimerId !== null) clearTO(holdTimerId);
        holdTimerId = setTO(() => {
          holdTimerId = null;
          if (!heldFrom) return;
          fadeFrom = {
            node: heldFrom.node,
            neighbours: heldFrom.neighbours,
            startTs: performance.now(),
          };
          heldFrom = null;
          startFadeLoop();
          deps.onRefresh();
        }, HOLD_MS);
      }
    } else {
      if (holdTimerId !== null) {
        clearTO(holdTimerId);
        holdTimerId = null;
      }
      hoveredNode = node;
      const g = deps.getGraph();
      const nbrs = new Set<string>();
      g.forEachNeighbor(node, (v) => nbrs.add(v));
      hoverNeighbours = nbrs;

      if (heldFrom) {
        heldFrom = null;
        fadeFrom = null;
        hoverStartTs = null;
      } else if (fadeFrom) {
        const dimLevel = 1 - getFadeOutProgress();
        fadeFrom = null;
        hoverStartTs = performance.now() - dimLevel * FADE_DURATION_MS;
        startFadeLoop();
      } else if (hoverStartTs !== null) {
        startFadeLoop();
      } else if (prev === null) {
        hoverStartTs = performance.now();
        startFadeLoop();
      }

      const attrs = g.getNodeAttributes(node);
      const raw = attrs.raw as { title_text?: string } | undefined;
      deps.onTooltipChange(raw?.title_text ?? attrs.label ?? '');
      const vp = deps.getNodeDisplayData(node);
      if (vp) {
        deps.onTooltipPos({ x: vp.x, y: vp.y - 18 });
      }
    }

    deps.onRefresh();
    notify();
  }

  function updateTooltipPos(): void {
    const node = hoveredNode;
    if (!node) return;
    const vp = deps.getNodeDisplayData(node);
    if (vp) {
      deps.onTooltipPos({ x: vp.x, y: vp.y - 18 });
    }
  }

  function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  function dispose(): void {
    if (fadeRafId !== null) {
      caf(fadeRafId);
      fadeRafId = null;
    }
    if (holdTimerId !== null) {
      clearTO(holdTimerId);
      holdTimerId = null;
    }
    fadeFrom = null;
    heldFrom = null;
    hoverStartTs = null;
    hoveredNode = null;
    hoverNeighbours = new Set();
    listeners.clear();
  }

  return {
    setHover,
    updateTooltipPos,
    getHoveredNode: () => hoveredNode,
    getHoverNeighbours: () => hoverNeighbours,
    getFadeInProgress,
    getFadeOutProgress,
    getHeldFrom: () => heldFrom,
    getFadeFrom: () => fadeFrom,
    lerpHex,
    subscribe,
    dispose,
  };
}
