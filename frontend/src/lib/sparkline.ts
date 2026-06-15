// Pure helper for the right pane Domain tab's activity sparkline.
//
// Backend returns ``[{date, count}, ...]`` already aggregated per day.
// We compute viewBox coordinates so the SVG itself stays declarative.
// Empty / single-day data states are surfaced as variants so the view
// can render them differently (text label / "no data" message) without
// duplicating the layout math.

import type { DomainActivityPoint } from './api/types';

export interface SparkPoint {
  date: string;
  count: number;
  // Coordinates in the chart's own coordinate space (see ``viewBox``).
  x: number;
  y: number;
}

export type SparklineLayout =
  | { kind: 'empty' }
  | { kind: 'single'; point: SparkPoint }
  | {
      kind: 'multi';
      viewBox: string;
      width: number;
      height: number;
      polyline: string;
      points: SparkPoint[];
    };

export const SPARKLINE_WIDTH = 160;
export const SPARKLINE_HEIGHT = 36;
const PADDING = 3;

export function buildSparkline(
  activity: DomainActivityPoint[],
  width: number = SPARKLINE_WIDTH,
  height: number = SPARKLINE_HEIGHT,
): SparklineLayout {
  if (!activity || activity.length === 0) {
    return { kind: 'empty' };
  }
  if (activity.length === 1) {
    const a = activity[0];
    return {
      kind: 'single',
      point: {
        date: a.date,
        count: a.count,
        x: width / 2,
        y: height / 2,
      },
    };
  }

  const innerW = Math.max(1, width - PADDING * 2);
  const innerH = Math.max(1, height - PADDING * 2);
  const maxCount = activity.reduce((m, a) => Math.max(m, a.count), 0);
  // Guard divide-by-zero — a flat all-zero series still gets a single
  // baseline polyline.
  const denom = maxCount === 0 ? 1 : maxCount;
  const stepX = innerW / (activity.length - 1);

  const points: SparkPoint[] = activity.map((a, i) => ({
    date: a.date,
    count: a.count,
    x: PADDING + i * stepX,
    y: PADDING + innerH - (a.count / denom) * innerH,
  }));
  const polyline = points.map((p) => `${p.x},${p.y}`).join(' ');

  return {
    kind: 'multi',
    viewBox: `0 0 ${width} ${height}`,
    width,
    height,
    polyline,
    points,
  };
}
