import { describe, it, expect } from 'vitest';
import {
  cycleLabel,
  isLabelFilterEmpty,
  labelMode,
  passesLabelFilter,
  pruneLabelFilter,
  type LabelFilterState,
} from './labelFilter';

const state = (over: Partial<LabelFilterState> = {}): LabelFilterState => ({
  include: [],
  exclude: [],
  ...over,
});

describe('passesLabelFilter', () => {
  it('passes everything when the filter is empty', () => {
    expect(passesLabelFilter(state(), [1], [])).toBe(true);
    expect(passesLabelFilter(state(), [], [])).toBe(true);
  });

  it('drops a node carrying an excluded label (direct or via domain)', () => {
    const s = state({ exclude: [9] });
    expect(passesLabelFilter(s, [9], [])).toBe(false);
    expect(passesLabelFilter(s, [], [9])).toBe(false);
    expect(passesLabelFilter(s, [1], [2])).toBe(true);
  });

  it('treats include as an allowlist', () => {
    const s = state({ include: [1] });
    expect(passesLabelFilter(s, [1], [])).toBe(true);
    expect(passesLabelFilter(s, [], [1])).toBe(true);
    expect(passesLabelFilter(s, [2], [])).toBe(false);
    expect(passesLabelFilter(s, [], [])).toBe(false);
  });

  it('lets exclude win over include', () => {
    const s = state({ include: [1], exclude: [9] });
    expect(passesLabelFilter(s, [1, 9], [])).toBe(false);
  });
});

describe('labelMode + cycleLabel', () => {
  it('cycles neutral → include → exclude → neutral', () => {
    let s = state();
    expect(labelMode(s, 5)).toBe('neutral');
    s = cycleLabel(s, 5);
    expect(labelMode(s, 5)).toBe('include');
    s = cycleLabel(s, 5);
    expect(labelMode(s, 5)).toBe('exclude');
    s = cycleLabel(s, 5);
    expect(labelMode(s, 5)).toBe('neutral');
  });

  it('keeps a label in only one set', () => {
    const s = cycleLabel(state({ exclude: [5] }), 5); // exclude → neutral
    expect(s.include).not.toContain(5);
    expect(s.exclude).not.toContain(5);
  });
});

describe('pruneLabelFilter', () => {
  it('drops ids the catalog no longer knows', () => {
    const s = state({ include: [1, 2], exclude: [3, 4] });
    const pruned = pruneLabelFilter(s, new Set([1, 3]));
    expect(pruned).toEqual({ include: [1], exclude: [3] });
  });
});

describe('isLabelFilterEmpty', () => {
  it('is empty only with no includes and no excludes', () => {
    expect(isLabelFilterEmpty(state())).toBe(true);
    expect(isLabelFilterEmpty(state({ include: [1] }))).toBe(false);
    expect(isLabelFilterEmpty(state({ exclude: [1] }))).toBe(false);
  });
});
