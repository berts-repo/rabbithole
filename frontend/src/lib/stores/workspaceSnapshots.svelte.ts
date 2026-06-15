// Per-workspace UI snapshots: node positions, selection, ego-focus, last
// payload, and camera state.
//
// One graphology instance lives for the page lifetime (graph.svelte.ts:56)
// — Sigma's WebGL context never re-mounts. Per-tab independence is
// achieved by capturing the full view on switch and restoring it after the
// new workspace's payload has been applied.
//
// SWR (stale-while-revalidate): `onSwitch` now optimistically pushes the
// next tab's last-seen payload into graphStore immediately, so the canvas
// renders the cached view while the background refresh is in flight.
// `consumePending` returns the cached camera state so the canvas can snap
// to it instead of re-running animatedReset.
//
// `pendingRestoreId` defers the position/selection/ego restore until
// *after* `applyPayload` rebuilds graphology for the new scope — snapshot
// positions can reference ids that don't exist yet in graphInstance.

import { graphStore, type EgoFocus } from '$lib/stores/graph.svelte';
import { selectionStore } from '$lib/stores/selection.svelte';
import type { GraphPayload } from '$lib/api';

type CameraState = { x: number; y: number; ratio: number; angle: number };

interface Snapshot {
  positions: Map<string, { x: number; y: number }>;
  selectedNodeId: number | null;
  selectedIds: Set<number>;
  egoFocus: EgoFocus | null;
  payload: GraphPayload | null;
  camera: CameraState | null;
}

const snapshots = new Map<string, Snapshot>();

const state = $state<{ version: number }>({ version: 0 });

let pendingRestoreId: string | null = null;
let cameraGetter: (() => CameraState | null) | null = null;

function snapshotFor(): Snapshot {
  const g = graphStore.graph();
  const positions = new Map<string, { x: number; y: number }>();
  g.forEachNode((node, attrs) => {
    positions.set(node, {
      x: attrs.x as number,
      y: attrs.y as number,
    });
  });
  return {
    positions,
    selectedNodeId: selectionStore.selectedNodeId,
    selectedIds: new Set(selectionStore.selectedIds),
    egoFocus: graphStore.egoFocus,
    payload: graphStore.payload,
    camera: cameraGetter?.() ?? null,
  };
}

function restoreFrom(snap: Snapshot): void {
  const g = graphStore.graph();
  for (const [node, { x, y }] of snap.positions) {
    if (!g.hasNode(node)) continue;
    g.setNodeAttribute(node, 'x', x);
    g.setNodeAttribute(node, 'y', y);
  }
  selectionStore.restoreSet(snap.selectedIds, snap.selectedNodeId);
  graphStore.setEgoFocus(snap.egoFocus);
}

export const workspaceSnapshots = {
  get version() {
    return state.version;
  },

  capture(id: string): void {
    snapshots.set(id, snapshotFor());
  },

  restore(id: string): boolean {
    const snap = snapshots.get(id);
    if (!snap) return false;
    restoreFrom(snap);
    state.version++;
    return true;
  },

  initFresh(): void {
    selectionStore.clear();
    graphStore.setEgoFocus(null);
    state.version++;
  },

  drop(id: string): void {
    snapshots.delete(id);
  },

  knownIds(): Set<string> {
    return new Set(snapshots.keys());
  },

  has(id: string): boolean {
    return snapshots.has(id);
  },

  // Register/unregister Sigma camera state provider. GraphCanvas calls
  // this on mount/destroy so snapshotFor() can capture camera state.
  registerCameraGetter(fn: () => CameraState | null): void {
    cameraGetter = fn;
  },
  unregisterCameraGetter(): void {
    cameraGetter = null;
  },

  // True if this tab has a cached payload from a previous visit.
  // Used by GraphCanvas to decide whether to show the first-visit skeleton.
  hasCachedPayload(id: string): boolean {
    return !!(snapshots.get(id)?.payload);
  },

  // Drop the payload field from every snapshot without touching positions
  // or camera. Called after a server-side graph_filters add/delete so that
  // hidden nodes don't briefly reappear when the old cached payload is
  // applied on the next tab switch. Positions and camera are preserved so
  // the layout survives; only the optimistic-apply step is skipped (the
  // user sees the first-visit skeleton briefly instead).
  invalidatePayloads(): void {
    for (const snap of snapshots.values()) {
      snap.payload = null;
    }
  },

  // Bridge helpers — used by GraphTab's $effect on activeWorkspaceId.
  onSwitch(prevId: string, nextId: string): void {
    if (prevId === nextId) return;
    snapshots.set(prevId, snapshotFor());
    pendingRestoreId = nextId;
    // SWR: if the next tab has a cached payload, push it into the graph
    // store immediately so the canvas renders stale data while the
    // background refresh is in flight. The real fetch's diff-update will
    // apply cleanly on top of this (positions are preserved by applyDiff).
    const nextSnap = snapshots.get(nextId);
    if (nextSnap?.payload) {
      graphStore.applyPayload(nextSnap.payload, nextId);
    }
  },

  // Called by GraphCanvas after applyPayloadAndLayout. Returns whether a
  // restore landed and the camera state to restore (null → animatedReset).
  consumePending(): { restored: boolean; camera: CameraState | null } {
    if (pendingRestoreId === null) return { restored: false, camera: null };
    const id = pendingRestoreId;
    pendingRestoreId = null;
    const snap = snapshots.get(id);
    if (snap) {
      restoreFrom(snap);
      state.version++;
      return { restored: true, camera: snap.camera };
    }
    // Fresh tab — clear selection / ego so the previous tab's state
    // doesn't bleed in.
    selectionStore.clear();
    graphStore.setEgoFocus(null);
    state.version++;
    return { restored: true, camera: null };
  },
};
