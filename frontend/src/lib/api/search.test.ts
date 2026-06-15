import { describe, expect, it } from 'vitest';
import { distanceToScore } from './search';

describe('distanceToScore', () => {
  it('maps cosine distance to a 0–1 similarity (higher = closer)', () => {
    expect(distanceToScore(0)).toBe(1); // identical
    expect(distanceToScore(1)).toBe(0); // orthogonal
    expect(distanceToScore(0.25)).toBeCloseTo(0.75);
  });

  it('clamps float noise and out-of-range distances into [0, 1]', () => {
    expect(distanceToScore(-0.0001)).toBe(1);
    expect(distanceToScore(1.2)).toBe(0);
  });
});
