import { describe, it, expect } from 'vitest';
import { isMultiSelectModifier, shouldOpenMultiMenu } from './selection';

describe('isMultiSelectModifier', () => {
  it('is false for a null event (non-mouse origin)', () => {
    expect(isMultiSelectModifier(null)).toBe(false);
  });

  it('is false for a plain click with no modifier', () => {
    expect(
      isMultiSelectModifier({
        ctrlKey: false,
        metaKey: false,
        shiftKey: false,
      }),
    ).toBe(false);
  });

  it('is true when ctrl, meta, or shift is held', () => {
    expect(
      isMultiSelectModifier({
        ctrlKey: true,
        metaKey: false,
        shiftKey: false,
      }),
    ).toBe(true);
    expect(
      isMultiSelectModifier({
        ctrlKey: false,
        metaKey: true,
        shiftKey: false,
      }),
    ).toBe(true);
    expect(
      isMultiSelectModifier({
        ctrlKey: false,
        metaKey: false,
        shiftKey: true,
      }),
    ).toBe(true);
  });
});

describe('shouldOpenMultiMenu', () => {
  it('opens the multi menu for a selected node in a 2+ selection', () => {
    expect(shouldOpenMultiMenu(3, true)).toBe(true);
    expect(shouldOpenMultiMenu(2, true)).toBe(true);
  });

  it('stays single when the right-clicked node is not selected', () => {
    expect(shouldOpenMultiMenu(3, false)).toBe(false);
  });

  it('stays single below a 2-node selection', () => {
    expect(shouldOpenMultiMenu(1, true)).toBe(false);
    expect(shouldOpenMultiMenu(0, true)).toBe(false);
  });
});
