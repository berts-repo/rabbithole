// Graph layout selection + run state.
//
// The chosen layout persists under `settings.graph.layout` (same
// round-trip pattern as graphFilters). `settling` and the stop/run tokens
// are runtime-only — never persisted. GraphCanvas owns the actual FA2
// worker handle; it drives `settling` and watches the tokens. The toolbar
// reads `kind` / `settling` and calls `setKind` / `requestStop`.

import { getSetting, putSetting } from '$lib/api';
import { isLayoutKind, type LayoutKind } from '$lib/graph/layouts';
import { toastStore } from './toast.svelte';

const DEFAULT_LAYOUT: LayoutKind = 'force';

interface LayoutState {
  kind: LayoutKind;
  loaded: boolean;
  // True while the Force (FA2) worker is settling.
  settling: boolean;
  // Bumped by the toolbar Stop button — GraphCanvas freezes FA2 early.
  stopToken: number;
  // Bumped on every layout pick — GraphCanvas re-runs the active layout.
  runToken: number;
}

const state = $state<LayoutState>({
  kind: DEFAULT_LAYOUT,
  loaded: false,
  settling: false,
  stopToken: 0,
  runToken: 0,
});

export const graphLayoutStore = {
  get kind() {
    return state.kind;
  },
  get loaded() {
    return state.loaded;
  },
  get settling() {
    return state.settling;
  },
  get stopToken() {
    return state.stopToken;
  },
  get runToken() {
    return state.runToken;
  },

  /** Rehydrate the chosen layout from settings. Falls back to the default
   *  on a missing key or any read failure — the canvas works regardless. */
  async load(): Promise<void> {
    try {
      const s = await getSetting<string>('graph.layout');
      if (isLayoutKind(s.value)) state.kind = s.value;
    } catch {
      // Missing/failed read → keep the default.
    }
    state.loaded = true;
  },

  /** Pick a layout. Persists in the background and, when the layout
   *  actually changes, bumps runToken so GraphCanvas re-lays-out. */
  setKind(kind: LayoutKind): void {
    if (!isLayoutKind(kind) || state.kind === kind) return;
    state.kind = kind;
    state.runToken++;
    putSetting('graph.layout', kind).catch((e) => {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Layout save failed: ${msg}`, 'warn');
    });
  },

  /** GraphCanvas calls this as it starts/finishes the FA2 worker. */
  setSettling(v: boolean): void {
    state.settling = v;
  },

  /** Toolbar Stop button — freeze the FA2 settle at its current frame. */
  requestStop(): void {
    state.stopToken++;
  },
};
