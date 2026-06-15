// Pure helpers for FingerprintsTab — node-only so vitest can cover the
// filter + threshold paths without mounting the component.

import type { FingerprintCluster, FingerprintMember } from '$lib/api';

/** Stable cluster identity used as the Svelte each-key. The (key, value)
 *  pair is unique per backend response. */
export function clusterKey(c: FingerprintCluster): string {
  return c.key + ' ' + c.value;
}

/** Clamp the min-sites threshold to the backend's accepted range. The
 *  backend rejects min_sites < 1 with HTTP 400; the input element clamps
 *  too, but the helper is the canonical source for both paths. */
export function clampMinSites(value: number): number {
  if (!Number.isFinite(value)) return 2;
  return Math.max(1, Math.min(1000, Math.trunc(value)));
}

/** Case-insensitive substring filter over key + value. */
export function filterClusters(
  clusters: FingerprintCluster[],
  filter: string,
): FingerprintCluster[] {
  const q = filter.trim().toLowerCase();
  if (!q) return clusters;
  return clusters.filter((c) => {
    if (c.key.toLowerCase().includes(q)) return true;
    if (c.value.toLowerCase().includes(q)) return true;
    return false;
  });
}

/** Case-insensitive substring filter over member URL + title. */
export function filterMembers(
  members: FingerprintMember[],
  filter: string,
): FingerprintMember[] {
  const q = filter.trim().toLowerCase();
  if (!q) return members;
  return members.filter((m) => {
    if (m.url.toLowerCase().includes(q)) return true;
    if (m.title && m.title.toLowerCase().includes(q)) return true;
    return false;
  });
}

/** Two-decimal IDF for the row. */
export function formatIdf(idf: number): string {
  if (!Number.isFinite(idf)) return '—';
  return idf.toFixed(2);
}
