import { describe, it, expect } from 'vitest';
import { qs } from './core';

// qs() is the one pure unit in the API client — it builds the query-string
// suffix appended to route paths. apiFetch is exercised end-to-end by the
// app and would need a fetch mock; qs is covered directly here.
describe('qs', () => {
  it('returns an empty string for no params', () => {
    expect(qs({})).toBe('');
  });

  it('returns an empty string when every value is null or undefined', () => {
    expect(qs({ a: null, b: undefined })).toBe('');
  });

  it('skips null and undefined values but keeps the rest', () => {
    expect(qs({ a: 1, b: null, c: undefined, d: 'x' })).toBe('?a=1&d=x');
  });

  it('prefixes a single param with ?', () => {
    expect(qs({ limit: 50 })).toBe('?limit=50');
  });

  it('joins multiple params with &', () => {
    expect(qs({ a: 1, b: 2 })).toBe('?a=1&b=2');
  });

  it('stringifies boolean and numeric values, including 0 and false', () => {
    expect(qs({ force: false, n: 0 })).toBe('?force=false&n=0');
  });

  it('url-encodes both keys and values', () => {
    expect(qs({ url: 'http://x.onion/a b' })).toBe(
      '?url=http%3A%2F%2Fx.onion%2Fa%20b',
    );
    expect(qs({ 'a&b': 'c=d' })).toBe('?a%26b=c%3Dd');
  });
});
