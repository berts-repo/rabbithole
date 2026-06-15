import { describe, expect, it } from 'vitest';
import { parseSnippet, resultKey } from './findResults';
import type { KeywordResult } from '$lib/api';

describe('parseSnippet', () => {
  it('returns a single plain segment when there are no marks', () => {
    expect(parseSnippet('just plain text')).toEqual([
      { text: 'just plain text', mark: false },
    ]);
  });

  it('splits plain and marked segments', () => {
    expect(parseSnippet('a <mark>hit</mark> b')).toEqual([
      { text: 'a ', mark: false },
      { text: 'hit', mark: true },
      { text: ' b', mark: false },
    ]);
  });

  it('handles a mark at the start and multiple marks', () => {
    expect(parseSnippet('<mark>x</mark> y <mark>z</mark>')).toEqual([
      { text: 'x', mark: true },
      { text: ' y ', mark: false },
      { text: 'z', mark: true },
    ]);
  });

  it('SECURITY: raw HTML in page text is preserved as plain text, never a tag', () => {
    // The component renders these `text` values as auto-escaped text nodes, so
    // a malicious snippet can't inject elements or load external resources.
    const segs = parseSnippet('<img src=x onerror=alert(1)> <mark>btc</mark>');
    expect(segs).toEqual([
      { text: '<img src=x onerror=alert(1)> ', mark: false },
      { text: 'btc', mark: true },
    ]);
  });

  it('returns an empty array for an empty snippet', () => {
    expect(parseSnippet('')).toEqual([]);
  });
});

describe('resultKey', () => {
  it('disambiguates a page and entity that share a node_id by position', () => {
    const page: KeywordResult = {
      type: 'page',
      node_id: 7,
      url: 'http://a.onion',
      title: null,
      snippet: '',
    };
    const entity: KeywordResult = {
      type: 'entity',
      node_id: 7,
      url: 'http://a.onion',
      entity_type: 'btc',
      value: 'bc1q',
    };
    expect(resultKey(page, 0)).not.toBe(resultKey(entity, 1));
    expect(resultKey(page, 0)).toBe('page:7:0');
  });
});
