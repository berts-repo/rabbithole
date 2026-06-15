// Sigma renderer construction for the Explore graph.
//
// Owns everything about *bringing up* the WebGL renderer — the WebGL
// availability probe, the dark-themed hover label, the flagged-border node
// program, and the Sigma settings object — so GraphCanvas.svelte only has to
// supply reducers and wire event handlers. It does not own interaction or
// app state.
//
// The graphology instance passed to createGraphRenderer is stable for the
// page lifetime (see stores/graph.svelte.ts): Sigma binds to it once and is
// never re-mounted.

import Sigma from 'sigma';
import type Graph from 'graphology';
import { createNodeBorderProgram } from '@sigma/node-border';
import type {
  NodeDisplayData,
  EdgeDisplayData,
  PartialButFor,
} from 'sigma/types';
import type { Settings } from 'sigma/settings';
import type { Attributes } from 'graphology-types';

const WEBGL_UNAVAILABLE_MESSAGE =
  'WebGL is unavailable in this browser. The graph needs hardware or software WebGL — ' +
  'in Chromium try enabling chrome://flags/#enable-unsafe-swiftshader and relaunch.';

/**
 * Probe for a usable WebGL context. Sigma 3.0.3's createWebGLContext crashes
 * with an opaque `null.blendFunc` error when no context is available, so the
 * canvas probes once up front. Returns null when WebGL (webgl2 or webgl) is
 * available, or a human-readable error message when it is not — a non-null
 * result means "do not construct Sigma".
 */
export function probeWebGL(): string | null {
  const probe = document.createElement('canvas');
  if (!probe.getContext('webgl2') && !probe.getContext('webgl')) {
    return WEBGL_UNAVAILABLE_MESSAGE;
  }
  return null;
}

// F4b flagged-borders renderer. The default sigma circle program has no
// border slot; @sigma/node-border drives an attribute-fed ring around a
// node. Registered as a *secondary* program — only flagged nodes opt in via
// `type: 'bordered'` from the node reducer. Sigma's default circle program
// is kept for everyone else: the border program's outer-edge AA mixes
// consecutive layer colours, and a transparent outer layer (the "no border"
// case) collapses that gradient into a hard step, making un-flagged nodes
// look pixelated.
const BorderedNodeProgram = createNodeBorderProgram({
  borders: [
    {
      color: { attribute: 'borderColor', defaultValue: '#ffb852' },
      size: { attribute: 'borderSize', defaultValue: 2.5, mode: 'pixels' },
    },
    { color: { attribute: 'color' }, size: { fill: true } },
  ],
});

// Sigma 3's stock drawDiscNodeHover paints a hardcoded #FFF capsule behind
// the hovered/selected label, which blares against this app's dark terminal
// palette. Port the same geometry but with a bg-toned fill and a teal
// border, and re-use settings.labelColor for the text on top so any future
// label-color tweak also threads through here.
function drawDarkNodeHover(
  context: CanvasRenderingContext2D,
  data: PartialButFor<NodeDisplayData, 'x' | 'y' | 'size' | 'label' | 'color'>,
  settings: Settings,
): void {
  const size = settings.labelSize;
  const font = settings.labelFont;
  const weight = settings.labelWeight;
  context.font = `${weight} ${size}px ${font}`;

  context.fillStyle = 'rgba(13, 25, 22, 0.95)';
  context.strokeStyle = '#1a3a2a';
  context.lineWidth = 1;
  context.shadowOffsetX = 0;
  context.shadowOffsetY = 0;
  context.shadowBlur = 6;
  context.shadowColor = '#000';

  const PADDING = 2;
  if (typeof data.label === 'string' && data.label.length > 0) {
    const textWidth = context.measureText(data.label).width;
    const boxWidth = Math.round(textWidth + 5);
    const boxHeight = Math.round(size + 2 * PADDING);
    const radius = Math.max(data.size, size / 2) + PADDING;
    const angleRadian = Math.asin(boxHeight / 2 / radius);
    const xDelta = Math.sqrt(Math.abs(radius ** 2 - (boxHeight / 2) ** 2));
    context.beginPath();
    context.moveTo(data.x + xDelta, data.y + boxHeight / 2);
    context.lineTo(data.x + radius + boxWidth, data.y + boxHeight / 2);
    context.lineTo(data.x + radius + boxWidth, data.y - boxHeight / 2);
    context.lineTo(data.x + xDelta, data.y - boxHeight / 2);
    context.arc(data.x, data.y, radius, angleRadian, -angleRadian);
    context.closePath();
    context.fill();
    context.stroke();
  } else {
    context.beginPath();
    context.arc(data.x, data.y, data.size + PADDING, 0, Math.PI * 2);
    context.closePath();
    context.fill();
  }
  context.shadowOffsetX = 0;
  context.shadowOffsetY = 0;
  context.shadowBlur = 0;

  if (data.label) {
    const lc = settings.labelColor;
    const color = lc.attribute
      ? ((data as unknown as Record<string, string>)[lc.attribute] ??
          lc.color ??
          '#000')
      : (lc.color ?? '#000');
    context.fillStyle = color;
    context.fillText(data.label, data.x + data.size + 3, data.y + size / 3);
  }
}

export type NodeReducer = (
  node: string,
  data: Attributes,
) => Partial<NodeDisplayData>;
export type EdgeReducer = (
  edge: string,
  data: Attributes,
) => Partial<EdgeDisplayData>;

/**
 * Construct the Sigma renderer over a (stable) graphology instance. The
 * caller owns the reducers and the event-handler wiring; this only bakes in
 * the app's renderer settings, node programs, and dark hover label.
 */
export function createGraphRenderer(
  graph: Graph,
  container: HTMLElement,
  reducers: { nodeReducer: NodeReducer; edgeReducer: EdgeReducer },
): Sigma {
  return new Sigma(graph, container, {
    nodeReducer: reducers.nodeReducer,
    edgeReducer: reducers.edgeReducer,
    renderEdgeLabels: false,
    labelRenderedSizeThreshold: 6,
    defaultEdgeType: 'arrow',
    nodeProgramClasses: { bordered: BorderedNodeProgram },
    labelColor: { color: '#7eb39e' },
    labelSize: 11,
    labelDensity: 0.4,
    itemSizesReference: 'positions',
    zoomToSizeRatioFunction: (x) => x,
    defaultNodeColor: '#2eb89a',
    defaultEdgeColor: '#1a3a2a',
    defaultDrawNodeHover: drawDarkNodeHover,
    // enableEdgeEvents: needed so rightClickEdge fires for the analyst-edge
    // context menu. Sigma's edge picking is a per-frame cost we accept
    // because the menu is the only edge-targeted interaction the canvas
    // owns; node-on-top precedence keeps endpoint clicks routing to nodes.
    enableEdgeEvents: true,
  });
}
