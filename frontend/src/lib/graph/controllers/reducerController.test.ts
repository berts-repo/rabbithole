import { describe, it, expect } from 'vitest';
import {
  createReducerController,
  categoricalColor,
  depthColor,
  nodeColorFromMode,
  hashStr,
  CATEGORICAL_PALETTE,
} from './reducerController';
import type { ReducerControllerDeps } from './reducerController';

// Minimal GraphNode fixture for tests
function makeRaw(overrides: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    id: 1,
    color: '#2eb89a',
    domain: 'test.onion',
    depth: 1,
    flag_status: null,
    is_bridge: false,
    betweenness: 0,
    in_degree_count: 0,
    state: 'crawled',
    analysis_excluded: false,
    reviewed: false,
    cluster_id: null,
    infra_cluster_id: null,
    category: null,
    ...overrides,
  };
}

function makeNodeAttrs(overrides: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    label: 'test node',
    size: 5,
    color: '#2eb89a',
    x: 0,
    y: 0,
    raw: makeRaw(overrides.raw as Record<string, unknown> ?? {}),
    ...overrides,
  };
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

function makeDeps(overrides: Partial<ReducerControllerDeps> = {}): ReducerControllerDeps {
  return {
    getColorMode: () => 'none',
    getLabelColor: () => null,
    getFlaggedBorders: () => false,
    getBridgeHighlight: () => false,
    getBridgeBetweennessMin: () => 0.1,
    getBridgeInDegreeMin: () => 5,
    getIsolate: () => false,
    isVisible: () => true,
    isEdgeVisible: () => true,
    getHoveredNode: () => null,
    getHoverNeighbours: () => new Set(),
    getFadeInProgress: () => 1,
    getFadeOutProgress: () => 1,
    getHeldFrom: () => null,
    getFadeFrom: () => null,
    lerpHex,
    getEgoFocusNodeId: () => null,
    getIsolateBrightSet: () => null,
    getPathEdges: () => new Set(),
    isSelected: () => false,
    getSelectedNodeId: () => null,
    getSelectedIds: () => new Set<number>(),
    getGraphEdge: (_e) => ({ source: '1', target: '2' }),
    ...overrides,
  };
}

describe('reducerController', () => {
  describe('nodeReducer', () => {
    it('returns node color from colorMode=none', () => {
      const ctrl = createReducerController(makeDeps());
      const result = ctrl.nodeReducer('1', makeNodeAttrs());
      expect(result.color).toBe('#2eb89a');
    });

    it('hidden when not visible', () => {
      const ctrl = createReducerController(makeDeps({ isVisible: () => false }));
      const result = ctrl.nodeReducer('1', makeNodeAttrs());
      expect(result.hidden).toBe(true);
    });

    it('no hidden when visible', () => {
      const ctrl = createReducerController(makeDeps());
      const result = ctrl.nodeReducer('1', makeNodeAttrs());
      expect(result.hidden).toBeFalsy();
    });

    it('selection turns node green', () => {
      const ctrl = createReducerController(makeDeps({
        isSelected: (id) => id === 1,
        getSelectedNodeId: () => null,
        getSelectedIds: () => new Set([1]),
      }));
      const result = ctrl.nodeReducer('1', makeNodeAttrs());
      expect(result.color).toBe('#39ff14');
    });

    it('selected focus node gets extra size bump', () => {
      const ctrl = createReducerController(makeDeps({
        isSelected: (id) => id === 1,
        getSelectedNodeId: () => 1,
        getSelectedIds: () => new Set([1]),
      }));
      const result = ctrl.nodeReducer('1', makeNodeAttrs({ size: 5 }));
      expect(result.size).toBe(8); // 5 + 3 for focus node
    });

    it('flagged border with status', () => {
      const ctrl = createReducerController(makeDeps({ getFlaggedBorders: () => true }));
      const attrs = makeNodeAttrs({ raw: makeRaw({ flag_status: 'flagged' }) });
      const result = ctrl.nodeReducer('1', attrs);
      expect((result as Record<string, unknown>).type).toBe('bordered');
      expect((result as Record<string, unknown>).borderColor).toBe('#ffb852');
    });

    it('uncrawled renders hollow with a visible ring', () => {
      const ctrl = createReducerController(makeDeps());
      const attrs = makeNodeAttrs({ raw: makeRaw({ state: 'known' }) });
      const result = ctrl.nodeReducer('1', attrs);
      // Dark fill plus a teal border — the ring is what keeps an edgeless
      // orphan placeholder visible against the near-black canvas.
      expect(result.color).toBe('#0d1916');
      expect((result as Record<string, unknown>).type).toBe('bordered');
      expect((result as Record<string, unknown>).borderColor).toBe('#2eb89a');
    });

    it('flag ring wins over the uncrawled hollow ring', () => {
      const ctrl = createReducerController(makeDeps({ getFlaggedBorders: () => true }));
      const attrs = makeNodeAttrs({
        raw: makeRaw({ state: 'known', flag_status: 'flagged' }),
      });
      const result = ctrl.nodeReducer('1', attrs);
      expect(result.color).toBe('#0d1916');
      expect((result as Record<string, unknown>).borderColor).toBe('#ffb852');
    });

    it('analysis_excluded tones down', () => {
      const ctrl = createReducerController(makeDeps());
      const attrs = makeNodeAttrs({ raw: makeRaw({ analysis_excluded: true }) });
      const result = ctrl.nodeReducer('1', attrs);
      expect(result.color).toBe('#3a5a4d');
    });

    it('hover increases size', () => {
      const ctrl = createReducerController(makeDeps({
        getHoveredNode: () => '1',
      }));
      const result = ctrl.nodeReducer('1', makeNodeAttrs({ size: 5 }));
      expect(result.size).toBe(6); // +1 for hovered
    });

    it('non-neighbour dim during hover', () => {
      const ctrl = createReducerController(makeDeps({
        getHoveredNode: () => '2',
        getHoverNeighbours: () => new Set(['3']),
        getFadeInProgress: () => 1, // fully dimmed
        getIsolate: () => false,
      }));
      // node '1' is neither hovered nor neighbour, should be dimmed
      const result = ctrl.nodeReducer('1', makeNodeAttrs());
      // At t=1 the color should be the dim target (#1a2a24)
      expect(result.color).toBe('#1a2a24');
    });

    it('bridge highlight with matching thresholds', () => {
      const ctrl = createReducerController(makeDeps({
        getBridgeHighlight: () => true,
        getBridgeBetweennessMin: () => 0.1,
        getBridgeInDegreeMin: () => 5,
      }));
      const attrs = makeNodeAttrs({
        raw: makeRaw({ is_bridge: true, betweenness: 0.5, in_degree_count: 10 }),
      });
      const result = ctrl.nodeReducer('1', attrs);
      expect(result.color).toBe('#7df3d0');
    });
  });

  describe('edgeReducer', () => {
    it('hidden when not in visible edges', () => {
      const ctrl = createReducerController(makeDeps({ isEdgeVisible: () => false }));
      const result = ctrl.edgeReducer('e1', { size: 1, color: '#fff' });
      expect(result.hidden).toBe(true);
    });

    it('focus-adjacent edge gets teal color', () => {
      const ctrl = createReducerController(makeDeps({
        getEgoFocusNodeId: () => 1,
        getGraphEdge: () => ({ source: '1', target: '2' }),
      }));
      const result = ctrl.edgeReducer('e1', { size: 1, color: '#333' });
      expect(result.color).toBe('#00d4aa');
    });

    it('path edge gets brighter teal', () => {
      const ctrl = createReducerController(makeDeps({
        getPathEdges: () => new Set(['e1']),
        getGraphEdge: () => ({ source: '3', target: '4' }),
      }));
      const result = ctrl.edgeReducer('e1', { size: 1, color: '#333' });
      expect(result.color).toBe('#7df3d0');
    });

    it('inter-selected edge gets teal', () => {
      const ctrl = createReducerController(makeDeps({
        getSelectedIds: () => new Set<number>([1, 2]),
        getGraphEdge: () => ({ source: '1', target: '2' }),
      }));
      const result = ctrl.edgeReducer('e1', { size: 1, color: '#333' });
      expect(result.color).toBe('#00d4aa');
    });
  });

  describe('colour helpers', () => {
    it('hashStr is deterministic', () => {
      expect(hashStr('test')).toBe(hashStr('test'));
    });

    it('categoricalColor returns a palette colour', () => {
      const c = categoricalColor('a.onion');
      expect(CATEGORICAL_PALETTE).toContain(c);
    });

    it('categoricalColor null returns fallback tone', () => {
      expect(categoricalColor(null)).toBe('#3a5a4d');
    });

    it('depthColor for depth 0 is bright teal', () => {
      expect(depthColor(0)).toBe('#7df3d0');
    });

    it('depthColor for depth 6 is dark', () => {
      expect(depthColor(6)).toBe('#1f4a3d');
    });

    it('depthColor for null returns fallback', () => {
      expect(depthColor(null)).toBe('#3a5a4d');
    });

    it('nodeColorFromMode domain returns categorical', () => {
      const raw = makeRaw({ domain: 'x.onion' }) as unknown as Parameters<
        typeof nodeColorFromMode
      >[0];
      const c = nodeColorFromMode(raw, '#000', 'domain');
      expect(CATEGORICAL_PALETTE).toContain(c);
    });
  });
});
