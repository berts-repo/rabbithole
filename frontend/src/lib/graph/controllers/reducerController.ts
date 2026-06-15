// Reducer controller — Sigma node/edge reducer functions.
//
// Owns: per-node and per-edge reducer logic composed from hover, ego-focus,
//       visibility, color-mode, selection, and path state.
// Exposes: getNodeReducer(), getEdgeReducer() — ready to pass to Sigma.
//
// Pure TypeScript — no Svelte $state. GraphCanvas passes the returned
// functions directly to Sigma on each refresh.

import type { NodeDisplayData, EdgeDisplayData } from 'sigma/types';
import type { Attributes } from 'graphology-types';
import type { GraphNode } from '$lib/api';
import type { ColorMode } from '$lib/stores/graphFilters.svelte';
import { isUncrawled } from '$lib/nodeState';

// ---- Colour helpers (kept here since they back the nodeReducer) ----

export const CATEGORICAL_PALETTE = [
  '#2eb89a', // teal (base)
  '#7eb39e', // muted teal
  '#ffb852', // amber
  '#7df3d0', // bright teal
  '#c084fc', // soft purple
  '#fb7185', // coral
  '#67e8f9', // cyan
  '#a8e063', // lime
];

export const FLAG_RING_COLORS: Record<string, string> = {
  pending: '#caa14a',
  flagged: '#ffb852',
  investigating: '#fb7185',
};

export function hashStr(s: string): number {
  let h = 5381;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

export function categoricalColor(key: string | number | null | undefined): string {
  if (key === null || key === undefined) return '#3a5a4d';
  const s = String(key);
  return CATEGORICAL_PALETTE[hashStr(s) % CATEGORICAL_PALETTE.length];
}

export function depthColor(depth: number | null | undefined): string {
  if (depth === null || depth === undefined) return '#3a5a4d';
  const d = Math.min(6, Math.max(0, depth));
  const t = d / 6;
  const fr = 0x7d, fg = 0xf3, fb = 0xd0;
  const tr = 0x1f, tg = 0x4a, tb = 0x3d;
  const r = Math.round(fr + (tr - fr) * t);
  const gg = Math.round(fg + (tg - fg) * t);
  const b = Math.round(fb + (tb - fb) * t);
  return `#${r.toString(16).padStart(2, '0')}${gg.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
}

// A minimal label shape for dominant-label color resolution — the catalog
// store's Label widened to just what the color math needs.
export interface LabelColorLite {
  id: number;
  rank: number;
  color: string | null;
}

// The color of a node's *dominant* label (item 11, color-by-label): the
// highest-ranked (lowest `rank`) label among its direct and via-domain ids,
// per the single D5 ordering. Falls back to a stable categorical swatch when
// the label has no explicit color, and null when the node carries no resolvable
// label (the reducer then greys it like depth/category nulls).
export function dominantLabelColor(
  directIds: readonly number[],
  domainIds: readonly number[],
  byId: (id: number) => LabelColorLite | undefined,
): string | null {
  let best: LabelColorLite | undefined;
  for (const id of [...directIds, ...domainIds]) {
    const l = byId(id);
    if (l && (best === undefined || l.rank < best.rank)) best = l;
  }
  if (!best) return null;
  return best.color ?? categoricalColor(best.id);
}

export function nodeColorFromMode(
  raw: GraphNode | undefined,
  fallback: string,
  mode: ColorMode,
  labelColor?: (raw: GraphNode) => string | null,
): string {
  if (!raw) return fallback;
  switch (mode) {
    case 'none':    return raw.color;
    case 'domain':  return categoricalColor(raw.domain);
    case 'cluster': return categoricalColor(raw.cluster_id);
    case 'depth':   return depthColor(raw.depth);
    case 'category': return categoricalColor(raw.category);
    case 'infra':   return categoricalColor(raw.infra_cluster_id);
    case 'label':   return labelColor?.(raw) ?? '#3a5a4d';
    // Fixed two-network palette: Tor in the accent teal, I2P in amber.
    case 'network': return raw.network === 'i2p' ? '#e0a44a' : '#00d4aa';
    default:        return raw.color;
  }
}

// ---- Controller deps ----

export interface ReducerControllerDeps {
  /** Current color mode from graphFiltersStore. */
  getColorMode: () => ColorMode;
  /**
   * Dominant-label color for a node (color-by-label mode), or null when the
   * node carries no resolvable label. Resolved against the live label catalog
   * so a recolor reflects without a payload rebuild.
   */
  getLabelColor: (raw: GraphNode) => string | null;
  /** Whether flagged borders overlay is on. */
  getFlaggedBorders: () => boolean;
  /** Whether bridge highlight overlay is on. */
  getBridgeHighlight: () => boolean;
  /** Bridge betweenness threshold. */
  getBridgeBetweennessMin: () => number;
  /** Bridge in-degree threshold. */
  getBridgeInDegreeMin: () => number;
  /** Whether isolate overlay is on. */
  getIsolate: () => boolean;
  /** Visibility controller — isVisible(nodeId), isEdgeVisible(edgeId). */
  isVisible: (nodeId: string) => boolean;
  isEdgeVisible: (edgeId: string) => boolean;
  /** Hover state. */
  getHoveredNode: () => string | null;
  getHoverNeighbours: () => Set<string>;
  getFadeInProgress: () => number;
  getFadeOutProgress: () => number;
  getHeldFrom: () => { node: string; neighbours: Set<string> } | null;
  getFadeFrom: () => { node: string; neighbours: Set<string>; startTs: number } | null;
  lerpHex: (from: string, to: string, t: number) => string;
  /** Ego focus state. */
  getEgoFocusNodeId: () => number | null;
  /** Isolate bright set (focus root + reachable). */
  getIsolateBrightSet: () => Set<string> | null;
  /** Path edges (shortest path from focus/selection to hovered node). */
  getPathEdges: () => Set<string>;
  /** Selection state. */
  isSelected: (id: number) => boolean;
  getSelectedNodeId: () => number | null;
  getSelectedIds: () => ReadonlySet<number>;
  /** Graph source edges. */
  getGraphEdge: (edgeKey: string) => { source: string; target: string };
}

export interface ReducerController {
  nodeReducer(node: string, data: Attributes): Partial<NodeDisplayData>;
  edgeReducer(edge: string, data: Attributes): Partial<EdgeDisplayData>;
}

const LABEL_FADE_THRESHOLD = 0.85;

export function createReducerController(deps: ReducerControllerDeps): ReducerController {
  function nodeReducer(node: string, data: Attributes): Partial<NodeDisplayData> {
    const raw = data.raw as GraphNode | undefined;
    const baseColor = nodeColorFromMode(
      raw,
      data.color,
      deps.getColorMode(),
      deps.getLabelColor,
    );

    const out: Partial<NodeDisplayData> & { borderColor?: string; borderSize?: number } = {
      label: data.label,
      size: data.size,
      color: baseColor,
      x: data.x,
      y: data.y,
    };

    if (!deps.isVisible(node)) {
      out.hidden = true;
      return out;
    }

    // Flagged borders overlay
    if (deps.getFlaggedBorders() && raw?.flag_status) {
      (out as Partial<NodeDisplayData>).type = 'bordered';
      out.borderColor = FLAG_RING_COLORS[raw.flag_status] ?? '#ffb852';
      out.borderSize = 2.5;
    }

    // Bridge highlight overlay
    if (
      deps.getBridgeHighlight() &&
      raw?.is_bridge &&
      (raw.betweenness ?? 0) >= deps.getBridgeBetweennessMin() &&
      (raw.in_degree_count ?? 0) >= deps.getBridgeInDegreeMin()
    ) {
      out.color = '#7df3d0';
      out.size = (out.size ?? data.size ?? 5) + 1.5;
    }

    const dimTarget = deps.getIsolate() ? '#0a0f0d' : '#1a2a24';
    const hoveredNode = deps.getHoveredNode();
    const hoverNeighbours = deps.getHoverNeighbours();
    const heldFrom = deps.getHeldFrom();
    const fadeFrom = deps.getFadeFrom();
    const isolateBrightSet = deps.getIsolateBrightSet();

    if (hoveredNode && hoveredNode !== node && !hoverNeighbours.has(node)) {
      const t = deps.getFadeInProgress();
      out.color = deps.lerpHex(out.color ?? baseColor, dimTarget, t);
      if (out.borderColor) out.borderColor = deps.lerpHex(out.borderColor, dimTarget, t);
      if (t > LABEL_FADE_THRESHOLD) out.label = '';
    } else if (heldFrom && heldFrom.node !== node && !heldFrom.neighbours.has(node)) {
      out.color = dimTarget;
      if (out.borderColor) out.borderColor = dimTarget;
      out.label = '';
    } else if (fadeFrom && fadeFrom.node !== node && !fadeFrom.neighbours.has(node)) {
      const t = deps.getFadeOutProgress();
      out.color = deps.lerpHex(dimTarget, out.color ?? baseColor, t);
      if (out.borderColor) out.borderColor = deps.lerpHex(dimTarget, out.borderColor, t);
      if (t < 1 - LABEL_FADE_THRESHOLD) out.label = '';
    } else if (isolateBrightSet && !isolateBrightSet.has(node)) {
      out.color = dimTarget;
      if (out.borderColor) out.borderColor = dimTarget;
      out.label = '';
    }

    // Uncrawled placeholders render hollow — a dark fill ringed by a faint
    // teal border. The ring is load-bearing: the #0d1916 fill is nearly the
    // #0a0f0d canvas colour, so without an outline a placeholder is invisible
    // whenever it has no bright crawled neighbour to read it against — exactly
    // the "Add to Graph" orphan case (no parent, no edge). A flag ring, if
    // present, already carries that node's outline and wins.
    if (raw && isUncrawled(raw)) {
      out.color = '#0d1916';
      if (!out.borderColor) {
        (out as Partial<NodeDisplayData>).type = 'bordered';
        out.borderColor = '#2eb89a';
        out.borderSize = 1.5;
      }
    }

    // analysis_excluded tone-down
    if (raw?.analysis_excluded) {
      out.color = '#3a5a4d';
    }

    // Selection fill
    const id = Number(node);
    if (deps.isSelected(id)) {
      out.color = '#39ff14';
      out.size = (data.size ?? 5) + (id === deps.getSelectedNodeId() ? 3 : 2);
    }

    // Hover wins last
    if (hoveredNode === node) {
      out.size = (out.size ?? data.size ?? 5) + 1;
    }

    return out;
  }

  function edgeReducer(edge: string, data: Attributes): Partial<EdgeDisplayData> {
    const out: Partial<EdgeDisplayData> = {
      size: data.size,
      color: data.color,
    };

    if (!deps.isEdgeVisible(edge)) {
      out.hidden = true;
      return out;
    }

    const { source: src, target: tgt } = deps.getGraphEdge(edge);
    const focusId = deps.getEgoFocusNodeId();
    const focusKey = focusId !== null ? String(focusId) : null;
    const focusAdjacent = focusKey !== null && (src === focusKey || tgt === focusKey);
    if (focusAdjacent) {
      out.color = '#00d4aa';
      out.size = (data.size ?? 1) + 0.5;
    }

    const sel = deps.getSelectedIds();
    let interSelected = false;
    if (sel.size >= 2) {
      if (sel.has(Number(src)) && sel.has(Number(tgt))) {
        interSelected = true;
        out.color = '#00d4aa';
        out.size = (data.size ?? 1) + 0.5;
      }
    }

    const onPath = deps.getPathEdges().has(edge);
    if (onPath) {
      out.color = '#7df3d0';
      out.size = (data.size ?? 1) + 1;
    }

    const stickyBright = interSelected || focusAdjacent || onPath;

    const hoveredNode = deps.getHoveredNode();
    const heldFrom = deps.getHeldFrom();
    const fadeFrom = deps.getFadeFrom();

    if (hoveredNode) {
      const adjacent = src === hoveredNode || tgt === hoveredNode;
      const t = deps.getFadeInProgress();
      if (adjacent && !stickyBright) {
        out.color = deps.lerpHex(data.color, '#00d4aa', t);
      } else if (!stickyBright) {
        out.color = deps.lerpHex(data.color, '#15201c', t);
      }
    } else if (heldFrom) {
      const adjacent = src === heldFrom.node || tgt === heldFrom.node;
      if (adjacent && !stickyBright) {
        out.color = '#00d4aa';
      } else if (!stickyBright) {
        out.color = '#15201c';
      }
    } else if (fadeFrom) {
      const adjacent = src === fadeFrom.node || tgt === fadeFrom.node;
      const t = deps.getFadeOutProgress();
      if (adjacent && !stickyBright) {
        out.color = deps.lerpHex('#00d4aa', data.color, t);
      } else if (!stickyBright) {
        out.color = deps.lerpHex('#15201c', data.color, t);
      }
    }

    return out;
  }

  return { nodeReducer, edgeReducer };
}
