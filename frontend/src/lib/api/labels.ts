// Label taxonomy routes (item 11) — CRUD, reorder, and attach/detach for the
// two typed join tables (resources keyed by INTEGER id, domains by TEXT host).
// Backs the labels store, picker popover, and chips. The page-rename half of
// item 11 lives in pages.ts (`patchPageAlias`); domain rename in domains.ts.

import { apiFetch, qs } from './core';
import type {
  CreateLabelBody,
  Label,
  LabelMembers,
  UpdateLabelBody,
} from './types';

export const listLabels = (includeHidden = true) =>
  apiFetch<{ labels: Label[] }>(`/labels${qs({ include_hidden: includeHidden })}`);

// The resources + domains carrying one label — backs the bottom-pane Labels
// tab's expand row. Fetched lazily on first expand, not part of the catalog.
export const listLabelMembers = (labelId: number) =>
  apiFetch<LabelMembers>(`/labels/${labelId}/members`);

export const createLabel = (body: CreateLabelBody) =>
  apiFetch<Label>('/labels', { method: 'POST', body: JSON.stringify(body) });

export const updateLabel = (id: number, body: UpdateLabelBody) =>
  apiFetch<Label>(`/labels/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });

export const deleteLabel = (id: number) =>
  apiFetch<{ ok: true }>(`/labels/${id}`, { method: 'DELETE' });

// Reorder writes `rank` by list position; any ids omitted keep their prior
// relative order appended after. Returns the full re-ranked list.
export const reorderLabels = (ids: number[]) =>
  apiFetch<{ labels: Label[] }>('/labels/order', {
    method: 'PATCH',
    body: JSON.stringify({ ids }),
  });

// Attach/detach are idempotent server-side (INSERT OR IGNORE / DELETE). The
// `attached`/`detached` flag reports whether a row actually changed.
export const attachResourceLabel = (labelId: number, resourceId: number) =>
  apiFetch<{ ok: true; attached: boolean }>(
    `/labels/${labelId}/resources/${resourceId}`,
    { method: 'POST' },
  );

export const detachResourceLabel = (labelId: number, resourceId: number) =>
  apiFetch<{ ok: true; detached: boolean }>(
    `/labels/${labelId}/resources/${resourceId}`,
    { method: 'DELETE' },
  );

export const attachDomainLabel = (labelId: number, host: string) =>
  apiFetch<{ ok: true; attached: boolean }>(
    `/labels/${labelId}/domains/${encodeURIComponent(host)}`,
    { method: 'POST' },
  );

export const detachDomainLabel = (labelId: number, host: string) =>
  apiFetch<{ ok: true; detached: boolean }>(
    `/labels/${labelId}/domains/${encodeURIComponent(host)}`,
    { method: 'DELETE' },
  );
