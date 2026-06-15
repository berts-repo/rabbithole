// Pure helpers for CollectionTab — extracted so vitest (node-only, no
// Svelte compile) can cover the filter / stub-count paths without
// mounting the component.

import type { CollectionItem } from '$lib/api';
import { isUncrawled } from '$lib/nodeState';

/** Case-insensitive substring filter over URL + title + domain. Empty /
 *  whitespace filter returns the input unchanged. */
export function filterItems(
  items: CollectionItem[],
  filter: string,
): CollectionItem[] {
  const q = filter.trim().toLowerCase();
  if (!q) return items;
  return items.filter((it) => {
    if (it.url.toLowerCase().includes(q)) return true;
    if (it.title && it.title.toLowerCase().includes(q)) return true;
    if (it.domain && it.domain.toLowerCase().includes(q)) return true;
    return false;
  });
}

/** Number of stub items in the list — drives the "Send to Crawl (all
 *  uncrawled)" button visibility. */
export function countStubs(items: CollectionItem[]): number {
  let n = 0;
  for (const it of items) if (isUncrawled(it)) n++;
  return n;
}

/** Stub URLs from a collection item list, dedupe-preserving original
 *  order. Used to stage the "Send to Crawl (all uncrawled)" batch. */
export function stubUrls(items: CollectionItem[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const it of items) {
    if (!isUncrawled(it)) continue;
    if (seen.has(it.url)) continue;
    seen.add(it.url);
    out.push(it.url);
  }
  return out;
}
