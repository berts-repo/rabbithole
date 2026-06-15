import { describe, it, expect } from 'vitest';
import type { AnalyzedNodeRow } from '$lib/api';
import {
  displayLabel,
  filterAnalyzed,
  formatAnalyzedAt,
  matchesQuery,
  typesSummary,
} from './analyzed';

const A = (
  node_id: number,
  url: string,
  types: string[] = ['Summary'],
  title: string | null = null,
  last_analyzed: string | null = '2026-05-12T00:00:00+00:00',
): AnalyzedNodeRow => ({
  node_id,
  url,
  title,
  state: 'crawled',
  analysis_types: types,
  last_analyzed,
});

describe('analyzed helpers', () => {
  it('matchesQuery is case-insensitive over URL and title; empty → all', () => {
    const r = A(1, 'http://abc.onion/path', ['Summary'], 'Hidden Market');
    expect(matchesQuery(r, 'ABC')).toBe(true);
    expect(matchesQuery(r, 'market')).toBe(true);
    expect(matchesQuery(r, 'nope')).toBe(false);
    expect(matchesQuery(r, '   ')).toBe(true);
  });

  it('filterAnalyzed narrows by query', () => {
    const rows = [
      A(1, 'http://alpha.onion/', ['Summary'], 'Alpha'),
      A(2, 'http://beta.onion/', ['Category'], 'Beta'),
    ];
    expect(filterAnalyzed(rows, 'beta').map((r) => r.node_id)).toEqual([2]);
    expect(filterAnalyzed(rows, '').map((r) => r.node_id)).toEqual([1, 2]);
  });

  it('displayLabel prefers a non-blank title, else URL', () => {
    expect(displayLabel(A(1, 'http://x.onion/', ['Summary'], 'Title'))).toBe(
      'Title',
    );
    expect(displayLabel(A(1, 'http://x.onion/', ['Summary'], null))).toBe(
      'http://x.onion/',
    );
    expect(displayLabel(A(1, 'http://x.onion/', ['Summary'], '   '))).toBe(
      'http://x.onion/',
    );
  });

  it('typesSummary joins analysis types with a middot', () => {
    expect(typesSummary(A(1, 'http://x.onion/', ['Summary', 'Category']))).toBe(
      'Summary · Category',
    );
    expect(typesSummary(A(1, 'http://x.onion/', ['Summary']))).toBe('Summary');
  });

  it('formatAnalyzedAt drops the year for the current year, keeps it otherwise', () => {
    // Assert the year-dropping behaviour rather than a localized day, so the
    // test is stable across the runner's timezone (toLocaleDateString renders
    // in local time). Use a mid-month UTC time that can't cross a year boundary.
    const now = new Date('2026-08-01T12:00:00Z');
    expect(formatAnalyzedAt('2026-05-12T12:00:00+00:00', now)).not.toMatch(
      /\d{4}/,
    );
    expect(formatAnalyzedAt('2024-05-12T12:00:00+00:00', now)).toContain('2024');
  });

  it('formatAnalyzedAt: null → empty, garbage → raw passthrough', () => {
    expect(formatAnalyzedAt(null)).toBe('');
    expect(formatAnalyzedAt('not-a-date')).toBe('not-a-date');
  });
});
