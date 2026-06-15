// Camera + viewport operations for the Sigma graph renderer.
//
// Three distinct camera moves GraphCanvas needs, kept here so the component
// doesn't carry the Sigma camera API directly:
//   - fitView:      toolbar Fit button — animated reset to frame the graph.
//   - restoreView:  workspace tab switch — snap to a saved camera state, or
//                   animated-reset when the tab has none.
//   - refitToGraph: post-layout — fit, then lock a custom bbox so Sigma's
//                   resize handler can't re-fit and jump the view.

import type Sigma from 'sigma';
import type Graph from 'graphology';

// Structural shape of Sigma's camera state — kept local so the camera module
// and the workspace snapshot store agree without importing each other.
export interface CameraView {
  x: number;
  y: number;
  ratio: number;
  angle: number;
}

// Axis-aligned bounding box over every node's current x/y.
export function graphBBox(g: Graph): {
  x: [number, number];
  y: [number, number];
} {
  let xMin = Infinity;
  let xMax = -Infinity;
  let yMin = Infinity;
  let yMax = -Infinity;
  g.forEachNode((_node, attr) => {
    const x = attr.x as number;
    const y = attr.y as number;
    if (x < xMin) xMin = x;
    if (x > xMax) xMax = x;
    if (y < yMin) yMin = y;
    if (y > yMax) yMax = y;
  });
  return { x: [xMin, xMax], y: [yMin, yMax] };
}

// Toolbar Fit — animated reset framing the whole graph.
export function fitView(renderer: Sigma, durationMs = 300): void {
  renderer.getCamera().animatedReset({ duration: durationMs });
}

// Workspace tab switch. The prior bbox was sized for the previous tab's
// layout, so clear it. If the snapshot carried a camera state, snap straight
// to it (the user already knows this view); otherwise animated-reset to fit
// the new tab's layout.
export function restoreView(renderer: Sigma, camera: CameraView | null): void {
  renderer.setCustomBBox(null);
  if (camera) {
    renderer.getCamera().setState(camera);
  } else {
    renderer.getCamera().animatedReset({ duration: 200 });
  }
}

// Post-layout refit. Clearing the bbox lets autoRescale fit the new
// arrangement; re-locking the bbox afterwards stops Sigma's resize handler
// (fired when the right panel auto-expands on a click) from re-fitting and
// jumping the view.
export function refitToGraph(renderer: Sigma, g: Graph): void {
  renderer.setCustomBBox(null);
  renderer.setSetting('autoRescale', true);
  renderer.refresh();
  renderer.setCustomBBox(graphBBox(g));
}
