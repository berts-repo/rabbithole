// Client-side filter state for the graph canvas. Every value here is
// applied at render time over the already-fetched /api/graph payload —
// toggling any field does NOT refetch the graph. The only server-side
// filter is the `graph_filters` table (Hidden sub-tab), which the
// backend already honours when building /api/graph.
//
// Each field round-trips through PUT/GET /api/settings/<key> so the
// shelf rehydrates on reload. Keys match `SETTING_VALIDATORS` in
// `backend/backend/db/settings.py` — frontend names like `colorMode`
// map to the backend key `graph.color` etc.
//
// Defaults are chosen so a fresh project shows the full graph with the
// least decoration: uncrawled hidden, no overlays, no hop cap, no edge
// dedup, colour-by-domain.
//
// Load order: `app.svelte` calls `graphFiltersStore.load()` on mount
// after `projects.load()` so the GET hits the active project. The
// canvas reads via the runes getters and re-renders on change without
// touching the poller.

import { getSetting, putSetting } from '$lib/api';
import { toastStore } from './toast.svelte';

export type ColorMode =
  | 'none'
  | 'domain'
  | 'cluster'
  | 'depth'
  | 'category'
  | 'infra'
  | 'label'
  | 'network';

export type EdgeMode = 'all' | 'cross-site' | 'same-site';

interface FiltersState {
  // Topology
  maxHops: number; // 0 = no limit; 1-10 caps reachability from the ego root
  showUncrawled: boolean;
  hideOrphans: boolean;
  mutualOnly: boolean;
  groupByDomain: boolean;
  // showAllEdges true (default) = render every edge between two nodes;
  // false = dedup parallel edges between the same domain pair into one.
  // Matches the existing backend key `graph.show_all_edges`.
  showAllEdges: boolean;
  edgeMode: EdgeMode;
  // Colour
  colorMode: ColorMode;
  // Overlays
  flaggedBorders: boolean;
  isolate: boolean;
  bridgeHighlight: boolean;
  bridgeBetweennessMin: number; // 0.0 - 1.0
  bridgeInDegreeMin: number; // 0 - 1000
  // Lifecycle flags
  loaded: boolean;
}

const DEFAULTS: Omit<FiltersState, 'loaded'> = {
  maxHops: 0,
  showUncrawled: false,
  hideOrphans: false,
  mutualOnly: false,
  groupByDomain: false,
  showAllEdges: true,
  edgeMode: 'all',
  colorMode: 'none',
  flaggedBorders: true,
  isolate: false,
  bridgeHighlight: false,
  bridgeBetweennessMin: 0.1,
  bridgeInDegreeMin: 5,
};

const state = $state<FiltersState>({ ...DEFAULTS, loaded: false });

function parseBool(v: unknown, fallback: boolean): boolean {
  if (typeof v === 'boolean') return v;
  if (typeof v === 'string') {
    const lo = v.trim().toLowerCase();
    if (lo === 'true') return true;
    if (lo === 'false') return false;
  }
  return fallback;
}

function parseInt0(v: unknown, fallback: number): number {
  if (typeof v === 'number' && Number.isFinite(v)) return Math.trunc(v);
  if (typeof v === 'string') {
    const n = parseInt(v, 10);
    if (Number.isFinite(n)) return n;
  }
  return fallback;
}

function parseFloat0(v: unknown, fallback: number): number {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string') {
    const n = parseFloat(v);
    if (Number.isFinite(n)) return n;
  }
  return fallback;
}

function parseEnum<T extends string>(
  v: unknown,
  allowed: readonly T[],
  fallback: T,
): T {
  if (typeof v === 'string') {
    const trimmed = v.trim() as T;
    if (allowed.includes(trimmed)) return trimmed;
  }
  return fallback;
}

async function readSetting<T>(key: string): Promise<T | null> {
  try {
    const s = await getSetting<T>(key);
    return s.value;
  } catch {
    // Missing key returns null from the backend route; any other failure
    // falls through to defaults. The poller still works without filters
    // loaded, so we don't surface a toast for read failures.
    return null;
  }
}

async function writeSetting(key: string, value: unknown): Promise<void> {
  try {
    await putSetting(key, value);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    toastStore.show(`Settings save failed (${key}): ${msg}`, 'warn');
  }
}

export const graphFiltersStore = {
  // --- runes getters ---
  get maxHops() {
    return state.maxHops;
  },
  get showUncrawled() {
    return state.showUncrawled;
  },
  get hideOrphans() {
    return state.hideOrphans;
  },
  get mutualOnly() {
    return state.mutualOnly;
  },
  get groupByDomain() {
    return state.groupByDomain;
  },
  get showAllEdges() {
    return state.showAllEdges;
  },
  get edgeMode() {
    return state.edgeMode;
  },
  get colorMode() {
    return state.colorMode;
  },
  get flaggedBorders() {
    return state.flaggedBorders;
  },
  get isolate() {
    return state.isolate;
  },
  get bridgeHighlight() {
    return state.bridgeHighlight;
  },
  get bridgeBetweennessMin() {
    return state.bridgeBetweennessMin;
  },
  get bridgeInDegreeMin() {
    return state.bridgeInDegreeMin;
  },
  get loaded() {
    return state.loaded;
  },

  /**
   * Pulls every filter key in parallel. Anything missing or malformed
   * falls back to the local default; we do not block the canvas on
   * settings — the poller and renderer work fine on defaults.
   */
  async load(): Promise<void> {
    const [
      maxHops,
      showUncrawled,
      hideOrphans,
      mutualOnly,
      groupByDomain,
      showAllEdges,
      edgeMode,
      colorMode,
      flaggedBorders,
      isolate,
      bridgeHighlight,
      bridgeBetweennessMin,
      bridgeInDegreeMin,
    ] = await Promise.all([
      readSetting<number | string>('graph.max_hops'),
      readSetting<boolean | string>('graph.show_uncrawled'),
      readSetting<boolean | string>('graph.hide_orphans'),
      readSetting<boolean | string>('graph.mutual_only'),
      readSetting<boolean | string>('graph.group_by_domain'),
      readSetting<boolean | string>('graph.show_all_edges'),
      readSetting<string>('graph.edges'),
      readSetting<string>('graph.color'),
      readSetting<boolean | string>('graph.flagged_borders'),
      readSetting<boolean | string>('graph.isolate'),
      readSetting<boolean | string>('graph.bridge_highlight'),
      readSetting<number | string>('graph.bridge_betweenness_min'),
      readSetting<number | string>('graph.bridge_in_degree_min'),
    ]);
    state.maxHops = parseInt0(maxHops, DEFAULTS.maxHops);
    state.showUncrawled = parseBool(showUncrawled, DEFAULTS.showUncrawled);
    state.hideOrphans = parseBool(hideOrphans, DEFAULTS.hideOrphans);
    state.mutualOnly = parseBool(mutualOnly, DEFAULTS.mutualOnly);
    state.groupByDomain = parseBool(groupByDomain, DEFAULTS.groupByDomain);
    state.showAllEdges = parseBool(showAllEdges, DEFAULTS.showAllEdges);
    state.edgeMode = parseEnum<EdgeMode>(
      edgeMode,
      ['all', 'cross-site', 'same-site'],
      DEFAULTS.edgeMode,
    );
    state.colorMode = parseEnum<ColorMode>(
      colorMode,
      ['none', 'domain', 'cluster', 'depth', 'category', 'infra', 'label', 'network'],
      DEFAULTS.colorMode,
    );
    state.flaggedBorders = parseBool(flaggedBorders, DEFAULTS.flaggedBorders);
    state.isolate = parseBool(isolate, DEFAULTS.isolate);
    state.bridgeHighlight = parseBool(
      bridgeHighlight,
      DEFAULTS.bridgeHighlight,
    );
    state.bridgeBetweennessMin = parseFloat0(
      bridgeBetweennessMin,
      DEFAULTS.bridgeBetweennessMin,
    );
    state.bridgeInDegreeMin = parseInt0(
      bridgeInDegreeMin,
      DEFAULTS.bridgeInDegreeMin,
    );
    state.loaded = true;
  },

  // --- setters: update state immediately, persist in background ---

  setMaxHops(value: number): void {
    const clamped = Math.max(0, Math.min(10, Math.trunc(value)));
    if (state.maxHops === clamped) return;
    state.maxHops = clamped;
    void writeSetting('graph.max_hops', clamped);
  },
  setShowUncrawled(value: boolean): void {
    if (state.showUncrawled === value) return;
    state.showUncrawled = value;
    void writeSetting('graph.show_uncrawled', value);
  },
  setHideOrphans(value: boolean): void {
    if (state.hideOrphans === value) return;
    state.hideOrphans = value;
    void writeSetting('graph.hide_orphans', value);
  },
  setMutualOnly(value: boolean): void {
    if (state.mutualOnly === value) return;
    state.mutualOnly = value;
    void writeSetting('graph.mutual_only', value);
  },
  setGroupByDomain(value: boolean): void {
    if (state.groupByDomain === value) return;
    state.groupByDomain = value;
    void writeSetting('graph.group_by_domain', value);
  },
  setShowAllEdges(value: boolean): void {
    if (state.showAllEdges === value) return;
    state.showAllEdges = value;
    void writeSetting('graph.show_all_edges', value);
  },
  setEdgeMode(value: EdgeMode): void {
    if (state.edgeMode === value) return;
    state.edgeMode = value;
    void writeSetting('graph.edges', value);
  },
  setColorMode(value: ColorMode): void {
    if (state.colorMode === value) return;
    state.colorMode = value;
    void writeSetting('graph.color', value);
  },
  setFlaggedBorders(value: boolean): void {
    if (state.flaggedBorders === value) return;
    state.flaggedBorders = value;
    void writeSetting('graph.flagged_borders', value);
  },
  setIsolate(value: boolean): void {
    if (state.isolate === value) return;
    state.isolate = value;
    void writeSetting('graph.isolate', value);
  },
  setBridgeHighlight(value: boolean): void {
    if (state.bridgeHighlight === value) return;
    state.bridgeHighlight = value;
    void writeSetting('graph.bridge_highlight', value);
  },
  setBridgeBetweennessMin(value: number): void {
    const clamped = Math.max(0, Math.min(1, value));
    if (state.bridgeBetweennessMin === clamped) return;
    state.bridgeBetweennessMin = clamped;
    void writeSetting('graph.bridge_betweenness_min', clamped);
  },
  setBridgeInDegreeMin(value: number): void {
    const clamped = Math.max(0, Math.min(1000, Math.trunc(value)));
    if (state.bridgeInDegreeMin === clamped) return;
    state.bridgeInDegreeMin = clamped;
    void writeSetting('graph.bridge_in_degree_min', clamped);
  },

  /**
   * True when any control sits at a non-default value. Used by the
   * toolbar to mark the Filter button as "active" so the analyst can
   * tell the view is filtered at a glance.
   */
  get hasActiveFilters() {
    return (
      state.maxHops !== DEFAULTS.maxHops ||
      state.showUncrawled !== DEFAULTS.showUncrawled ||
      state.hideOrphans !== DEFAULTS.hideOrphans ||
      state.mutualOnly !== DEFAULTS.mutualOnly ||
      state.groupByDomain !== DEFAULTS.groupByDomain ||
      state.showAllEdges !== DEFAULTS.showAllEdges ||
      state.edgeMode !== DEFAULTS.edgeMode ||
      state.colorMode !== DEFAULTS.colorMode ||
      state.flaggedBorders !== DEFAULTS.flaggedBorders ||
      state.isolate !== DEFAULTS.isolate ||
      state.bridgeHighlight !== DEFAULTS.bridgeHighlight
    );
  },
};
