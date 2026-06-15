import { describe, it, expect } from 'vitest';
import { normalizeTerm, isValidTerm, isDuplicate } from './hideRules';

describe('hide-rule helpers', () => {
  it('trims whitespace in normalizeTerm', () => {
    expect(normalizeTerm('  foo  ')).toBe('foo');
    expect(normalizeTerm('\tbar\n')).toBe('bar');
  });

  it('rejects empty / whitespace-only terms', () => {
    expect(isValidTerm('')).toBe(false);
    expect(isValidTerm('   ')).toBe(false);
    expect(isValidTerm('x')).toBe(true);
  });

  it('detects duplicates after trim', () => {
    const existing = ['spam', 'login'];
    expect(isDuplicate('spam', existing)).toBe(true);
    expect(isDuplicate('  spam  ', existing)).toBe(true);
    expect(isDuplicate('SPAM', existing)).toBe(false); // case-sensitive — matches backend
    expect(isDuplicate('phish', existing)).toBe(false);
  });
});
