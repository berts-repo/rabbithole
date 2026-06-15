import { describe, expect, it } from 'vitest';

import {
  buildSparkline,
  SPARKLINE_HEIGHT,
  SPARKLINE_WIDTH,
} from './sparkline';

describe('buildSparkline', () => {
  it('returns empty for no data', () => {
    expect(buildSparkline([])).toEqual({ kind: 'empty' });
  });

  it('returns single-point layout for one day of data', () => {
    const result = buildSparkline([{ date: '2026-05-01', count: 5 }]);
    expect(result.kind).toBe('single');
    if (result.kind !== 'single') return;
    expect(result.point.date).toBe('2026-05-01');
    expect(result.point.count).toBe(5);
    expect(result.point.x).toBe(SPARKLINE_WIDTH / 2);
    expect(result.point.y).toBe(SPARKLINE_HEIGHT / 2);
  });

  it('builds polyline for multi-day data, scaled to max count', () => {
    const result = buildSparkline([
      { date: '2026-05-01', count: 0 },
      { date: '2026-05-02', count: 10 },
      { date: '2026-05-03', count: 5 },
    ]);
    expect(result.kind).toBe('multi');
    if (result.kind !== 'multi') return;
    expect(result.points).toHaveLength(3);
    // Max-count point should sit at the top edge (smallest y).
    const peakY = Math.min(...result.points.map((p) => p.y));
    const peak = result.points.find((p) => p.y === peakY)!;
    expect(peak.count).toBe(10);
    // First and last x cover the inner width.
    expect(result.points[0].x).toBeLessThan(result.points[2].x);
    expect(result.polyline.split(' ')).toHaveLength(3);
  });

  it('handles all-zero series without divide-by-zero', () => {
    const result = buildSparkline([
      { date: '2026-05-01', count: 0 },
      { date: '2026-05-02', count: 0 },
    ]);
    expect(result.kind).toBe('multi');
    if (result.kind !== 'multi') return;
    // Both points sit on the baseline (max y).
    expect(result.points[0].y).toBe(result.points[1].y);
  });
});
