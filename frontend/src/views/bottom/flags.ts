// Pure helpers for FlagsTab — filter + badge formatting.
//
// Status dropdown surfaces every value the backend supports
// (All / Pending / Investigating / Done / Dismissed). `flagged` is
// folded into the Pending bucket because the schema's "pending" /
// "flagged" / "investigating" tri-state is finer-grained than the UI
// spec; from the analyst's perspective both pre-investigation states
// are "pending action."
//
// Priority dropdown is the lifecycle priority (1=High, 2=Medium,
// 3=Low) the backend persists. Badge labels and colours derive from
// the integer.

import type { FlagListRow, FlagStatus } from '$lib/api';

export type StatusFilterValue =
  | 'all'
  | 'pending'
  | 'investigating'
  | 'done'
  | 'dismissed';

export const STATUS_FILTER_OPTIONS: {
  value: StatusFilterValue;
  label: string;
}[] = [
  { value: 'all', label: 'All' },
  { value: 'pending', label: 'Pending' },
  { value: 'investigating', label: 'Investigating' },
  { value: 'done', label: 'Done' },
  { value: 'dismissed', label: 'Dismissed' },
];

export type PriorityFilterValue = 'all' | 1 | 2 | 3;

export const PRIORITY_FILTER_OPTIONS: {
  value: PriorityFilterValue;
  label: string;
}[] = [
  { value: 'all', label: 'All' },
  { value: 1, label: 'High' },
  { value: 2, label: 'Medium' },
  { value: 3, label: 'Low' },
];

export function matchesStatus(
  row: FlagListRow,
  value: StatusFilterValue,
): boolean {
  if (value === 'all') return true;
  if (value === 'pending')
    return row.status === 'pending' || row.status === 'flagged';
  return row.status === value;
}

export function matchesPriority(
  row: FlagListRow,
  value: PriorityFilterValue,
): boolean {
  if (value === 'all') return true;
  return row.priority === value;
}

export function matchesUrl(row: FlagListRow, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  if (row.url.toLowerCase().includes(q)) return true;
  if (row.title && row.title.toLowerCase().includes(q)) return true;
  return false;
}

export function filterFlags(
  rows: FlagListRow[],
  status: StatusFilterValue,
  priority: PriorityFilterValue,
  query: string,
): FlagListRow[] {
  return rows.filter(
    (r) =>
      matchesStatus(r, status) &&
      matchesPriority(r, priority) &&
      matchesUrl(r, query),
  );
}

export function priorityLabel(priority: number): string {
  switch (priority) {
    case 1:
      return 'High';
    case 2:
      return 'Med';
    case 3:
      return 'Low';
    default:
      return String(priority);
  }
}

// CSS class hook — actual colours live in the component's <style>.
export function priorityBadgeClass(priority: number): string {
  switch (priority) {
    case 1:
      return 'prio-high';
    case 2:
      return 'prio-med';
    case 3:
      return 'prio-low';
    default:
      return 'prio-unknown';
  }
}

// Human-readable status label. `flagged` is the watchlist auto-flag
// state; surfacing it as "Pending" keeps the UI vocabulary aligned
// with the dropdown.
export function statusLabel(status: FlagStatus): string {
  switch (status) {
    case 'pending':
    case 'flagged':
      return 'Pending';
    case 'investigating':
      return 'Investigating';
    case 'done':
      return 'Done';
    case 'dismissed':
      return 'Dismissed';
  }
}

export function hostFromUrl(url: string): string | null {
  try {
    const u = new URL(url);
    return u.hostname || null;
  } catch {
    return null;
  }
}
