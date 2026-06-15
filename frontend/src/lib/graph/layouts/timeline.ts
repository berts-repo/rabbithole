// Timeline layout — time runs down the y-axis (earliest at the top);
// nodes discovered on the same day spread across x columns. Undated nodes
// (no first_seen) get a column off to the left. Returns legend data the
// canvas renders as a small overlay. Pure geometry, no physics.

import type Graph from 'graphology';
import type { GraphNode } from '$lib/api';
import { isUncrawled } from '$lib/nodeState';

export interface TimelineLegend {
  minDate: string | null;
  maxDate: string | null;
  dayCount: number;
  undatedCount: number;
}

const DAY_MS = 86_400_000;

export function timelineLayout(g: Graph): { timeline: TimelineLegend } {
  const Y_PER_DAY = 28;
  const COL_GAP = 24;
  const UNDATED_X = -200;

  const dated: { node: string; day: number }[] = [];
  const undated: string[] = [];
  let minDay = Infinity;
  let maxDay = -Infinity;

  g.forEachNode((node, attrs) => {
    const raw = attrs.raw as GraphNode | undefined;
    if (!raw || isUncrawled(raw)) return;
    const t = raw.first_seen ? Date.parse(raw.first_seen) : NaN;
    if (Number.isNaN(t)) {
      undated.push(node);
      return;
    }
    const day = Math.floor(t / DAY_MS);
    dated.push({ node, day });
    if (day < minDay) minDay = day;
    if (day > maxDay) maxDay = day;
  });

  // Group dated nodes by day → spread across x columns within that row.
  const byDay = new Map<number, string[]>();
  for (const { node, day } of dated) {
    const b = byDay.get(day);
    if (b) b.push(node);
    else byDay.set(day, [node]);
  }
  for (const [day, nodes] of byDay) {
    const y = (day - minDay) * Y_PER_DAY;
    const width = (nodes.length - 1) * COL_GAP;
    nodes.forEach((node, i) => {
      g.setNodeAttribute(node, 'x', i * COL_GAP - width / 2);
      g.setNodeAttribute(node, 'y', y);
    });
  }

  // Undated nodes stack in a single column to the left of the timeline.
  undated.forEach((node, i) => {
    g.setNodeAttribute(node, 'x', UNDATED_X);
    g.setNodeAttribute(node, 'y', i * COL_GAP);
  });

  const toIso = (day: number) =>
    Number.isFinite(day)
      ? new Date(day * DAY_MS).toISOString().slice(0, 10)
      : null;

  return {
    timeline: {
      minDate: dated.length ? toIso(minDay) : null,
      maxDate: dated.length ? toIso(maxDay) : null,
      dayCount: dated.length ? maxDay - minDay + 1 : 0,
      undatedCount: undated.length,
    },
  };
}
