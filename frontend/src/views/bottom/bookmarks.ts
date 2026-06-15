// Pure helpers for BookmarksTab — extracted so vitest (node-only, no
// Svelte compile) can cover the filter / host derivation paths without
// mounting the component.

import type { Seed } from '$lib/api';

/** Host portion of a URL (no port). Returns null for inputs we can't
 *  parse — the row falls back to the raw URL for display and the
 *  visibility dot becomes a no-op. */
export function hostFromUrl(url: string): string | null {
  try {
    return new URL(url).hostname || null;
  } catch {
    return null;
  }
}

/** Case-insensitive substring filter over label + URL. Empty / whitespace
 *  filter returns the input unchanged. */
export function filterSeeds(seeds: Seed[], filter: string): Seed[] {
  const q = filter.trim().toLowerCase();
  if (!q) return seeds;
  return seeds.filter((s) => {
    if (s.url.toLowerCase().includes(q)) return true;
    if (s.label && s.label.toLowerCase().includes(q)) return true;
    return false;
  });
}

/** Short "May 26" / "May 26, 2024" style added-date for the row.
 *  Falls back to the raw string when Date.parse fails. */
export function formatAddedAt(addedAt: string, now: Date = new Date()): string {
  const t = Date.parse(addedAt);
  if (Number.isNaN(t)) return addedAt;
  const d = new Date(t);
  const sameYear = d.getUTCFullYear() === now.getUTCFullYear();
  return d.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: sameYear ? undefined : 'numeric',
  });
}
