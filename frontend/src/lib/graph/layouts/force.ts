// Force layout — ForceAtlas2 in a Web Worker, run-to-settle.
//
// The 2026 freeze that retired FA2 was caused by running it synchronously,
// on the main thread, over the whole 38k-node stub-heavy graph. All three
// causes are removed here:
//   - stubs are excluded (they orbit their parents in a halo, never the
//     force layout) so FA2 only sees the fetched subgraph — hundreds of
//     nodes on a typical project;
//   - it runs in a Web Worker, so the main thread never blocks;
//   - it runs for a bounded budget and then stops — a layout, not a
//     perpetual simulation.
//
// Positions are copied back to the rendered graph every TICK_MS for a
// coarse live settle, and once more on finish. The caller freezes them
// from there (the diff-update / drag-to-move systems own positions until
// the next explicit re-layout).

import Graph from 'graphology';
import forceAtlas2 from 'graphology-layout-forceatlas2';
import FA2Layout from 'graphology-layout-forceatlas2/worker';
import type { GraphNode } from '$lib/api';
import { radialLayout } from './radial';
import { isUncrawled } from '$lib/nodeState';

export interface ForceHandle {
  /** Settle early: copy current positions back, fire onSettle now. */
  stop: () => void;
  /** Abandon: kill the worker with no copy-back and no onSettle — used
   *  when a new layout is taking over mid-settle. */
  cancel: () => void;
}

interface ForceOpts {
  /** Coarse progress repaint — no camera refit. */
  onTick: () => void;
  /** Final callback — positions are copied back, ready to fit. */
  onSettle: () => void;
}

const SETTLE_MS = 2500;
const TICK_MS = 320;

// Edge weights drive FA2 attraction (edgeWeightInfluence defaults to 1, and
// inferSettings leaves it there). We weight by domain boundary so the two
// relationships move independently under a single layout:
//   - cross-domain links pull hard, so separate sites settle close together;
//   - intra-domain links pull lightly, so one site's pages spread out under
//     the default repulsion instead of stacking on top of each other.
// scalingRatio is left at inferSettings' default (10).
const CROSS_DOMAIN_WEIGHT = 5;
const INTRA_DOMAIN_WEIGHT = 0.3;

export function runForceLayout(g: Graph, opts: ForceOpts): ForceHandle {
  // Build a temp graph of fetched nodes + the edges between them. FA2's
  // `fixed` attribute doesn't exempt nodes from repulsion, so a fresh
  // graph that simply omits stubs is the clean route with zero new deps.
  const sub = new Graph();
  g.forEachNode((node, attrs) => {
    const raw = attrs.raw as GraphNode | undefined;
    if (raw && !isUncrawled(raw)) {
      sub.addNode(node, { x: Math.random() * 100, y: Math.random() * 100 });
    }
  });
  if (sub.order === 0) {
    opts.onSettle();
    return { stop: () => {}, cancel: () => {} };
  }
  g.forEachEdge((_e, _a, s, t, sAttrs, tAttrs) => {
    if (s === t || !sub.hasNode(s) || !sub.hasNode(t) || sub.hasEdge(s, t)) return;
    const sd = (sAttrs.raw as GraphNode | undefined)?.domain;
    const td = (tAttrs.raw as GraphNode | undefined)?.domain;
    const sameSite = !!sd && sd === td;
    sub.addEdge(s, t, {
      weight: sameSite ? INTRA_DOMAIN_WEIGHT : CROSS_DOMAIN_WEIGHT,
    });
  });

  // Construct + start the worker. If the worker can't spawn (locked-down
  // environment, bundler quirk), fall back to instant radial geometry so
  // the default layout never leaves the analyst staring at a blob.
  let layout: FA2Layout;
  try {
    const settings = forceAtlas2.inferSettings(sub);
    layout = new FA2Layout(sub, {
      settings: {
        ...settings,
        barnesHutOptimize: sub.order > 500,
        // Stronger repulsion than inferSettings' default (~10): spreads the
        // hubs further apart so their stub halos stop overlapping near the
        // crowded centre of the graph.
        scalingRatio: 40,
      },
    });
    layout.start();
  } catch {
    radialLayout(g);
    opts.onSettle();
    return { stop: () => {}, cancel: () => {} };
  }

  let done = false;
  let timer: ReturnType<typeof setTimeout>;

  const copyBack = (): void => {
    sub.forEachNode((node, attrs) => {
      // A poll between start and finish can drop a node from `g`; guard so
      // the copy-back never throws on a stale key.
      if (g.hasNode(node)) {
        g.setNodeAttribute(node, 'x', attrs.x);
        g.setNodeAttribute(node, 'y', attrs.y);
      }
    });
  };

  const finish = (settle: boolean): void => {
    if (done) return;
    done = true;
    clearInterval(tick);
    clearTimeout(timer);
    layout.kill();
    if (settle) {
      copyBack();
      opts.onSettle();
    }
  };

  const tick = setInterval(() => {
    copyBack();
    opts.onTick();
  }, TICK_MS);
  timer = setTimeout(() => finish(true), SETTLE_MS);

  return {
    stop: () => finish(true),
    cancel: () => finish(false),
  };
}
