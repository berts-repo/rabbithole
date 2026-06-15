// Layout controller — layout name, worker lifecycle, position application.
//
// Owns: current layout name, force worker lifecycle (start/stop/cancel),
//       position application (stubs halo around parents).
// Exposes: runLayout(name?), stopLayout(), cancelLayout(), relayout(),
//          isRunning(), getLayoutKind(), subscribe().
//
// Wraps existing layouts/force.ts and SYNC_LAYOUTS — no algorithm change.
// Plain TypeScript — no Svelte $state.

import type Graph from 'graphology';
import {
  SYNC_LAYOUTS,
  runForceLayout,
  type ForceHandle,
  type TimelineLegend,
  type LayoutKind,
} from '$lib/graph/layouts';
import {
  positionStubsAroundParents,
  positionOrphanStubsOutside,
} from '$lib/graph/model/geometry';
import type Sigma from 'sigma';
import { refitToGraph } from '$lib/graph/runtime/camera';

export interface LayoutControllerDeps {
  /** Returns the current graphology instance. */
  getGraph: () => Graph;
  /** Returns the current Sigma renderer (or null if not mounted). */
  getRenderer: () => Sigma | null;
  /** Called when the layout starts settling (force). */
  onSettlingStart: () => void;
  /** Called when the layout settles or is stopped. */
  onSettlingEnd: () => void;
  /** Called with timeline metadata when a timeline layout runs. */
  onTimelineLegend: (legend: TimelineLegend | null) => void;
}

export interface LayoutController {
  /**
   * Run the active layout from scratch. Randomises node positions first so
   * force-atlas starts fresh; synchronous layouts overwrite them.
   * Pass a LayoutKind to override; defaults to the current kind.
   */
  relayout(): void;
  /** Stop an in-flight FA2 worker early (copy positions back). */
  stopLayout(): void;
  /** Cancel an in-flight FA2 worker (no copy-back). Used when switching layouts. */
  cancelLayout(): void;
  /** Whether the FA2 worker is currently settling. */
  isRunning(): boolean;
  /** Current layout kind. */
  getLayoutKind(): LayoutKind;
  /** Set the layout kind (does not trigger a re-layout). */
  setLayoutKind(kind: LayoutKind): void;
  /** Register a listener on state change. Returns unsub fn. */
  subscribe(listener: () => void): () => void;
  /** Dispose (cancels any running worker). */
  dispose(): void;
}

export function createLayoutController(
  kind: LayoutKind,
  deps: LayoutControllerDeps,
): LayoutController {
  let currentKind: LayoutKind = kind;
  let forceHandle: ForceHandle | null = null;
  let running = false;

  const listeners = new Set<() => void>();

  function notify(): void {
    for (const l of listeners) l();
  }

  function finishLayout(g: Graph): void {
    const renderer = deps.getRenderer();
    if (!renderer) return;
    positionStubsAroundParents(g);
    positionOrphanStubsOutside(g);
    refitToGraph(renderer, g);
  }

  function runActiveLayout(g: Graph): void {
    cancelLayout();
    if (currentKind === 'force') {
      running = true;
      deps.onSettlingStart();
      deps.onTimelineLegend(null);
      notify();
      forceHandle = runForceLayout(g, {
        onTick: () => deps.getRenderer()?.refresh(),
        onSettle: () => {
          forceHandle = null;
          running = false;
          deps.onSettlingEnd();
          finishLayout(g);
          notify();
        },
      });
      return;
    }
    const meta = SYNC_LAYOUTS[currentKind](g);
    deps.onTimelineLegend(meta && (meta as { timeline?: TimelineLegend }).timeline ? (meta as { timeline: TimelineLegend }).timeline : null);
    finishLayout(g);
    notify();
  }

  function relayout(): void {
    const g = deps.getGraph();
    g.forEachNode((n) => {
      g.setNodeAttribute(n, 'x', Math.random());
      g.setNodeAttribute(n, 'y', Math.random());
    });
    runActiveLayout(g);
  }

  function stopLayout(): void {
    forceHandle?.stop();
  }

  function cancelLayout(): void {
    if (forceHandle) {
      forceHandle.cancel();
      forceHandle = null;
      if (running) {
        running = false;
        deps.onSettlingEnd();
        notify();
      }
    }
  }

  function isRunning(): boolean {
    return running;
  }

  function getLayoutKind(): LayoutKind {
    return currentKind;
  }

  function setLayoutKind(k: LayoutKind): void {
    currentKind = k;
  }

  function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  function dispose(): void {
    cancelLayout();
    listeners.clear();
  }

  return {
    relayout,
    stopLayout,
    cancelLayout,
    isRunning,
    getLayoutKind,
    setLayoutKind,
    subscribe,
    dispose,
  };
}
