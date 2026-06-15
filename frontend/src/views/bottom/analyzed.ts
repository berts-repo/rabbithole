// Pure helpers for AnalyzedTab — filter + display formatting. Kept out of
// the .svelte component so the policy is unit-testable without the Svelte
// runtime, the same split flags.ts / domains.ts use.

import type { AnalyzedNodeRow } from '$lib/api';

// Case-insensitive match over URL and title; empty/whitespace query → all.
export function matchesQuery(row: AnalyzedNodeRow, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  if (row.url.toLowerCase().includes(q)) return true;
  if (row.title && row.title.toLowerCase().includes(q)) return true;
  return false;
}

export function filterAnalyzed(
  rows: AnalyzedNodeRow[],
  query: string,
): AnalyzedNodeRow[] {
  return rows.filter((r) => matchesQuery(r, query));
}

// Row label — the page title when it has one, else the URL.
export function displayLabel(row: AnalyzedNodeRow): string {
  return row.title && row.title.trim() ? row.title : row.url;
}

// Compact analysis-type summary, e.g. "Summary · Category".
export function typesSummary(row: AnalyzedNodeRow): string {
  return row.analysis_types.join(' · ');
}

/** Short "May 26" / "May 26, 2024" style last-analyzed date for the row.
 *  Falls back to the raw string when Date.parse fails, '' when null. */
export function formatAnalyzedAt(
  iso: string | null,
  now: Date = new Date(),
): string {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const d = new Date(t);
  const sameYear = d.getUTCFullYear() === now.getUTCFullYear();
  return d.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: sameYear ? undefined : 'numeric',
  });
}
