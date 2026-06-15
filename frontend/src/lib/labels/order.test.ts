import { describe, it, expect } from 'vitest';
import { reorderedIds } from './order';

describe('reorderedIds', () => {
  it('moves an item down', () => {
    expect(reorderedIds([1, 2, 3, 4], 0, 2)).toEqual([2, 3, 1, 4]);
  });

  it('moves an item up', () => {
    expect(reorderedIds([1, 2, 3, 4], 3, 1)).toEqual([1, 4, 2, 3]);
  });

  it('returns a copy unchanged for a no-op or out-of-range move', () => {
    expect(reorderedIds([1, 2, 3], 1, 1)).toEqual([1, 2, 3]);
    expect(reorderedIds([1, 2, 3], 5, 0)).toEqual([1, 2, 3]);
    expect(reorderedIds([1, 2, 3], 0, -1)).toEqual([1, 2, 3]);
  });
});
