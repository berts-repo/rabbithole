import { describe, it, expect } from 'vitest';
import { classifyGraphKey, type GraphKeyFacts } from './keyboard';

function facts(over: Partial<GraphKeyFacts>): GraphKeyFacts {
  return {
    key: '',
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    inTextEntry: false,
    ...over,
  };
}

describe('classifyGraphKey', () => {
  it('classifies Escape even inside a text-entry control', () => {
    expect(
      classifyGraphKey(facts({ key: 'Escape', inTextEntry: true })),
    ).toBe('escape');
  });

  it('suppresses non-Escape keys while typing in a control', () => {
    expect(
      classifyGraphKey(facts({ key: 'a', ctrlKey: true, inTextEntry: true })),
    ).toBe('none');
    expect(classifyGraphKey(facts({ key: 'f', inTextEntry: true }))).toBe(
      'none',
    );
  });

  it('classifies Ctrl/Cmd+A as select-all', () => {
    expect(classifyGraphKey(facts({ key: 'a', ctrlKey: true }))).toBe(
      'select-all',
    );
    expect(classifyGraphKey(facts({ key: 'A', metaKey: true }))).toBe(
      'select-all',
    );
  });

  it('does not treat a bare A as select-all', () => {
    expect(classifyGraphKey(facts({ key: 'a' }))).toBe('none');
  });

  it('classifies a bare F as focus-node, with or without Shift', () => {
    expect(classifyGraphKey(facts({ key: 'f' }))).toBe('focus-node');
    expect(classifyGraphKey(facts({ key: 'F' }))).toBe('focus-node');
  });

  it('does not classify F as focus-node when a modifier is held', () => {
    expect(classifyGraphKey(facts({ key: 'f', ctrlKey: true }))).toBe('none');
    expect(classifyGraphKey(facts({ key: 'f', metaKey: true }))).toBe('none');
    expect(classifyGraphKey(facts({ key: 'f', altKey: true }))).toBe('none');
  });

  it('returns none for unrelated keys', () => {
    expect(classifyGraphKey(facts({ key: 'x' }))).toBe('none');
  });
});
