import { describe, expect, it } from 'vitest';
import type { Seed } from '$lib/api';
import { filterSeeds, formatAddedAt, hostFromUrl } from './bookmarks';

const URL_A = 'http://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaad.onion/';
const URL_B = 'http://bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbd.onion/forum';

const seed = (overrides: Partial<Seed>): Seed => ({
  url: URL_A,
  label: null,
  added_at: '2026-05-26T10:00:00+00:00',
  ...overrides,
});

describe('hostFromUrl', () => {
  it('returns hostname for a valid URL', () => {
    expect(hostFromUrl(URL_A)).toBe(
      'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaad.onion',
    );
  });

  it('returns null for garbage input', () => {
    expect(hostFromUrl('not a url')).toBeNull();
  });
});

describe('filterSeeds', () => {
  const seeds: Seed[] = [
    seed({ url: URL_A, label: 'Forum tip' }),
    seed({ url: URL_B, label: 'Market mirror' }),
    seed({ url: URL_A.replace('aaaa', 'cccc'), label: null }),
  ];

  it('returns input unchanged for empty / whitespace filter', () => {
    expect(filterSeeds(seeds, '')).toBe(seeds);
    expect(filterSeeds(seeds, '   ')).toBe(seeds);
  });

  it('matches label substring case-insensitively', () => {
    const r = filterSeeds(seeds, 'TIP');
    expect(r).toHaveLength(1);
    expect(r[0].label).toBe('Forum tip');
  });

  it('matches URL substring case-insensitively', () => {
    const r = filterSeeds(seeds, '/forum');
    expect(r).toHaveLength(1);
    expect(r[0].url).toBe(URL_B);
  });

  it('excludes seeds with no label and no URL match', () => {
    const r = filterSeeds(seeds, 'unlabeled');
    expect(r).toHaveLength(0);
  });
});

describe('formatAddedAt', () => {
  it('returns raw string when Date.parse fails', () => {
    expect(formatAddedAt('garbage')).toBe('garbage');
  });

  it('omits year when added in the current year', () => {
    const now = new Date('2026-06-01T00:00:00Z');
    const out = formatAddedAt('2026-05-26T10:00:00+00:00', now);
    expect(out).not.toMatch(/2026/);
  });

  it('includes year when added in a prior year', () => {
    const now = new Date('2026-06-01T00:00:00Z');
    const out = formatAddedAt('2024-05-26T10:00:00+00:00', now);
    expect(out).toMatch(/2024/);
  });
});
