// Page-version routes — single-snapshot fetch + on-demand two-version diff.
// Backs the right-pane Phase-5 versioning UI. Current-version detail still
// comes from getNode (GET /api/nodes/:id); these pull *older* snapshots and
// diff any two versions of the same page.

import { apiFetch } from './core';
import type { PageVersion, VersionDiff } from './types';

export const getPageVersion = (id: number) =>
  apiFetch<PageVersion>(`/pages/versions/${id}`);

export const getVersionDiff = (aId: number, bId: number) =>
  apiFetch<VersionDiff>(`/pages/versions/${aId}/diff/${bId}`);

// Set or clear a page's display alias (item 11, decision D1) — the page half
// of rename, keyed by resource id, on the same target-agnostic seam the
// frontend `renameTarget()` routes through. Whitespace-only clears it.
export const patchPageAlias = (resourceId: number, alias: string | null) =>
  apiFetch<{ resource_id: number; alias: string | null }>(
    `/pages/${resourceId}/alias`,
    { method: 'PATCH', body: JSON.stringify({ alias }) },
  );
