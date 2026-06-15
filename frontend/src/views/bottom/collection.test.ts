import { describe, expect, it } from 'vitest';
import type { CollectionItem } from '$lib/api';
import { countStubs, filterItems, stubUrls } from './collection';

const URL_A = 'http://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaad.onion/';
const URL_B = 'http://bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbd.onion/forum';
const URL_C = 'http://ccccccccccccccccccccccccccccccccccccccccccccccccccccccd.onion/about';

const item = (overrides: Partial<CollectionItem>): CollectionItem => ({
  id: 1,
  url: URL_A,
  title: null,
  state: 'crawled',
  status_code: 200,
  domain: new URL(URL_A).hostname,
  ...overrides,
});

describe('filterItems', () => {
  const items: CollectionItem[] = [
    item({ id: 1, url: URL_A, title: 'Index page' }),
    item({ id: 2, url: URL_B, title: 'Forum mirror', domain: new URL(URL_B).hostname }),
    item({ id: 3, url: URL_C, title: null, state: 'known', status_code: null, domain: new URL(URL_C).hostname }),
  ];

  it('returns input unchanged for empty / whitespace filter', () => {
    expect(filterItems(items, '')).toBe(items);
    expect(filterItems(items, '   ')).toBe(items);
  });

  it('matches title substring case-insensitively', () => {
    const r = filterItems(items, 'FORUM');
    expect(r).toHaveLength(1);
    expect(r[0].title).toBe('Forum mirror');
  });

  it('matches URL substring case-insensitively', () => {
    const r = filterItems(items, '/about');
    expect(r).toHaveLength(1);
    expect(r[0].url).toBe(URL_C);
  });

  it('matches domain substring even when URL/title do not', () => {
    const r = filterItems(items, 'bbbbbbbbbbbbb');
    expect(r).toHaveLength(1);
    expect(r[0].id).toBe(2);
  });

  it('excludes rows with no URL / title / domain match', () => {
    expect(filterItems(items, 'zzzzz-no-such-string')).toHaveLength(0);
  });
});

describe('countStubs', () => {
  it('counts only stub rows', () => {
    const items: CollectionItem[] = [
      item({ id: 1, state: 'crawled' }),
      item({ id: 2, state: 'known' }),
      item({ id: 3, state: 'known' }),
    ];
    expect(countStubs(items)).toBe(2);
  });

  it('returns 0 for an empty list', () => {
    expect(countStubs([])).toBe(0);
  });
});

describe('stubUrls', () => {
  it('returns only stub URLs, preserving input order', () => {
    const items: CollectionItem[] = [
      item({ id: 1, url: URL_A, state: 'known' }),
      item({ id: 2, url: URL_B, state: 'crawled' }),
      item({ id: 3, url: URL_C, state: 'known' }),
    ];
    expect(stubUrls(items)).toEqual([URL_A, URL_C]);
  });

  it('dedupes repeat URLs without changing first-seen order', () => {
    const items: CollectionItem[] = [
      item({ id: 1, url: URL_A, state: 'known' }),
      item({ id: 2, url: URL_C, state: 'known' }),
      item({ id: 3, url: URL_A, state: 'known' }),
    ];
    expect(stubUrls(items)).toEqual([URL_A, URL_C]);
  });
});
