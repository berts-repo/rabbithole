import { describe, it, expect } from 'vitest';
import type { FlagListRow, FlagStatus } from '$lib/api';
import {
  filterFlags,
  hostFromUrl,
  matchesPriority,
  matchesStatus,
  matchesUrl,
  priorityBadgeClass,
  priorityLabel,
  statusLabel,
} from './flags';

const F = (
  id: number,
  url: string,
  status: FlagStatus,
  priority: number,
  title: string | null = null,
): FlagListRow => ({
  id,
  node_id: id,
  status,
  source: 'analyst',
  priority,
  note: null,
  url,
  title,
});

describe('flags helpers', () => {
  it('matchesStatus all passes everything', () => {
    expect(matchesStatus(F(1, 'http://x/', 'pending', 1), 'all')).toBe(true);
    expect(matchesStatus(F(1, 'http://x/', 'dismissed', 1), 'all')).toBe(true);
  });

  it('matchesStatus pending covers both `pending` and `flagged`', () => {
    expect(matchesStatus(F(1, 'http://x/', 'pending', 1), 'pending')).toBe(true);
    expect(matchesStatus(F(1, 'http://x/', 'flagged', 1), 'pending')).toBe(true);
    expect(
      matchesStatus(F(1, 'http://x/', 'investigating', 1), 'pending'),
    ).toBe(false);
  });

  it('matchesPriority filters by integer priority', () => {
    expect(matchesPriority(F(1, 'http://x/', 'pending', 1), 1)).toBe(true);
    expect(matchesPriority(F(1, 'http://x/', 'pending', 2), 1)).toBe(false);
    expect(matchesPriority(F(1, 'http://x/', 'pending', 3), 'all')).toBe(true);
  });

  it('matchesUrl is case-insensitive over URL and title', () => {
    const r = F(1, 'http://abc.onion/path', 'pending', 1, 'Hidden Market');
    expect(matchesUrl(r, 'ABC')).toBe(true);
    expect(matchesUrl(r, 'market')).toBe(true);
    expect(matchesUrl(r, 'nope')).toBe(false);
    expect(matchesUrl(r, '   ')).toBe(true);
  });

  it('filterFlags combines all three filters', () => {
    const rows = [
      F(1, 'http://a.onion/', 'pending', 1, 'Alpha'),
      F(2, 'http://b.onion/', 'investigating', 2, 'Beta'),
      F(3, 'http://c.onion/', 'done', 3, 'Gamma'),
      F(4, 'http://d.onion/', 'dismissed', 1, 'Delta'),
      F(5, 'http://e.onion/', 'flagged', 1, 'Epsilon'),
    ];
    // High-priority and pending → flagged + pending rows match
    expect(filterFlags(rows, 'pending', 1, '').map((r) => r.id)).toEqual([
      1, 5,
    ]);
    // Done + low priority + matching URL
    expect(filterFlags(rows, 'done', 3, 'c.onion').map((r) => r.id)).toEqual([
      3,
    ]);
    // No matches → empty
    expect(filterFlags(rows, 'dismissed', 2, '').map((r) => r.id)).toEqual([]);
  });

  it('priorityLabel and priorityBadgeClass cover all three buckets', () => {
    expect(priorityLabel(1)).toBe('High');
    expect(priorityLabel(2)).toBe('Med');
    expect(priorityLabel(3)).toBe('Low');
    expect(priorityBadgeClass(1)).toBe('prio-high');
    expect(priorityBadgeClass(2)).toBe('prio-med');
    expect(priorityBadgeClass(3)).toBe('prio-low');
  });

  it('statusLabel folds `flagged` into "Pending"', () => {
    expect(statusLabel('pending')).toBe('Pending');
    expect(statusLabel('flagged')).toBe('Pending');
    expect(statusLabel('investigating')).toBe('Investigating');
    expect(statusLabel('done')).toBe('Done');
    expect(statusLabel('dismissed')).toBe('Dismissed');
  });

  it('hostFromUrl extracts hostname, null on garbage', () => {
    expect(hostFromUrl('http://abc.onion/path')).toBe('abc.onion');
    expect(hostFromUrl('https://a.b.onion')).toBe('a.b.onion');
    expect(hostFromUrl('not a url')).toBeNull();
  });
});
