import { describe, it, expect } from 'vitest';
import type { DomainRow } from '$lib/api';
import { displayName, filterDomains } from './domains';

const D = (
  host: string,
  alias: string | null = null,
  page_count = 1,
): DomainRow => ({
  host,
  alias,
  last_seen: null,
  page_count,
  fail_count: 0,
  flag_count: 0,
});

describe('domains helpers', () => {
  it('returns input unchanged when filter is empty or whitespace', () => {
    const rows = [D('aaa.onion'), D('bbb.onion')];
    expect(filterDomains(rows, '')).toEqual(rows);
    expect(filterDomains(rows, '   ')).toEqual(rows);
  });

  it('matches host substring case-insensitively', () => {
    const rows = [D('alpha.onion'), D('beta.onion'), D('gamma.onion')];
    expect(filterDomains(rows, 'BET')).toEqual([D('beta.onion')]);
  });

  it('matches alias when set', () => {
    const rows = [
      D('alpha.onion', 'Marketplace'),
      D('beta.onion', null),
      D('gamma.onion', 'forum'),
    ];
    expect(filterDomains(rows, 'market').map((r) => r.host)).toEqual([
      'alpha.onion',
    ]);
    expect(filterDomains(rows, 'forum').map((r) => r.host)).toEqual([
      'gamma.onion',
    ]);
  });

  it('matches either alias or host', () => {
    const rows = [
      D('shop.onion', 'Bazaar'),
      D('chat.onion', null),
    ];
    // 'shop' matches host of the first row.
    expect(filterDomains(rows, 'shop').map((r) => r.host)).toEqual([
      'shop.onion',
    ]);
    // 'bazaar' matches alias of the first row.
    expect(filterDomains(rows, 'bazaar').map((r) => r.host)).toEqual([
      'shop.onion',
    ]);
  });

  it('displayName prefers a non-empty alias, falls back to host', () => {
    expect(displayName(D('x.onion', 'Alpha'))).toBe('Alpha');
    expect(displayName(D('x.onion', null))).toBe('x.onion');
    expect(displayName(D('x.onion', '   '))).toBe('x.onion');
  });
});
