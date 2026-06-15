import { describe, expect, it } from 'vitest';
import {
  BOTTOM_TABS,
  DEFAULT_VISIBLE_TABS,
  decodeVisible,
  encodeVisible,
  isBottomTab,
  neighborAfterRemoval,
  normalizeVisible,
  orderTabs,
  type BottomTab,
} from './bottomTabs';

const ALL: BottomTab[] = BOTTOM_TABS.map((t) => t.id);

describe('BOTTOM_TABS', () => {
  it('has unique ids and a label for each', () => {
    expect(new Set(ALL).size).toBe(ALL.length);
    for (const t of BOTTOM_TABS) expect(t.label.length).toBeGreaterThan(0);
  });

  it('default visible strip is a subset of known tabs and non-empty', () => {
    expect(DEFAULT_VISIBLE_TABS.length).toBeGreaterThan(0);
    for (const id of DEFAULT_VISIBLE_TABS) expect(isBottomTab(id)).toBe(true);
  });
});

describe('isBottomTab', () => {
  it('accepts known tab ids', () => {
    expect(isBottomTab('live_crawl')).toBe(true);
    expect(isBottomTab('monitors')).toBe(true);
    expect(isBottomTab('bookmarks')).toBe(true);
  });

  it('rejects unknown strings, undefined, and non-strings', () => {
    expect(isBottomTab('settings')).toBe(false);
    expect(isBottomTab('')).toBe(false);
    expect(isBottomTab(undefined)).toBe(false);
    expect(isBottomTab(null)).toBe(false);
    expect(isBottomTab(7)).toBe(false);
    expect(isBottomTab({ id: 'live_crawl' })).toBe(false);
  });
});

describe('orderTabs', () => {
  it('sorts into canonical display order regardless of input order', () => {
    expect(orderTabs(['collection', 'live_crawl', 'flags'])).toEqual([
      'live_crawl',
      'flags',
      'collection',
    ]);
  });

  it('drops unknowns and de-dupes', () => {
    expect(
      orderTabs(['flags', 'flags', 'nope' as BottomTab, 'activity']),
    ).toEqual(['activity', 'flags']);
  });
});

describe('normalizeVisible', () => {
  it('orders, de-dupes, and passes through a valid set', () => {
    expect(normalizeVisible(['monitors', 'activity', 'monitors'])).toEqual([
      'activity',
      'monitors',
    ]);
  });

  it('falls back to the default strip when nothing valid remains', () => {
    expect(normalizeVisible([])).toEqual(DEFAULT_VISIBLE_TABS);
    expect(normalizeVisible(['nope' as BottomTab])).toEqual(DEFAULT_VISIBLE_TABS);
  });
});

describe('neighborAfterRemoval', () => {
  it('prefers the tab to the right of the removed one', () => {
    expect(
      neighborAfterRemoval(['live_crawl', 'activity', 'inventory'], 'activity'),
    ).toBe('inventory');
  });

  it('falls back to the left when the removed tab was last', () => {
    expect(
      neighborAfterRemoval(['live_crawl', 'activity', 'inventory'], 'inventory'),
    ).toBe('activity');
  });

  it('refuses to remove the only remaining tab', () => {
    expect(neighborAfterRemoval(['live_crawl'], 'live_crawl')).toBeNull();
  });

  it('returns null when the tab is not on the strip', () => {
    expect(neighborAfterRemoval(['live_crawl', 'activity'], 'flags')).toBeNull();
  });
});

describe('encodeVisible / decodeVisible', () => {
  it('round-trips a strip through the CSV scalar form', () => {
    const strip: BottomTab[] = ['live_crawl', 'inventory', 'collection'];
    expect(decodeVisible(encodeVisible(strip))).toEqual(strip);
  });

  it('decodes leniently — trims, drops unknowns, normalises order', () => {
    expect(decodeVisible(' flags , live_crawl , bogus ')).toEqual([
      'live_crawl',
      'flags',
    ]);
  });

  it('returns null for non-strings or strings with no known tabs', () => {
    expect(decodeVisible(null)).toBeNull();
    expect(decodeVisible(['live_crawl'])).toBeNull();
    expect(decodeVisible('bogus,nope')).toBeNull();
  });
});
