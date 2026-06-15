// Node routes (CRUD, review/exclusion state, lookup, external launch) plus
// the per-node flag routes.

import { apiFetch } from './core';
import type {
  NodeRow,
  NodeLookupRow,
  FlagRow,
  CreateNodeBody,
  LookupNodesBody,
  CreateFlagBody,
} from './types';

// ---------------- Nodes ----------------

export const getNode = (id: number) => apiFetch<NodeRow>(`/nodes/${id}`);

export const createStubNode = (body: CreateNodeBody) =>
  apiFetch<{ id: number; url: string }>('/nodes', {
    method: 'POST',
    body: JSON.stringify(body),
  });

// Batch sibling of createStubNode — backs "Add all to Graph". Returns the
// landed {id, url} per valid URL plus the rejects, so the caller pins exactly
// the ids that materialized.
export const createStubNodes = (urls: string[]) =>
  apiFetch<{ nodes: { id: number; url: string }[]; invalid: { url: string; message: string }[] }>(
    '/nodes/batch',
    { method: 'POST', body: JSON.stringify({ urls }) },
  );

export const patchNodeReviewed = (id: number, reviewed: boolean) =>
  apiFetch<{ ok: true }>(`/nodes/${id}/reviewed`, {
    method: 'PATCH',
    body: JSON.stringify({ reviewed }),
  });

export const patchNodeAnalysisExcluded = (id: number, excluded: boolean) =>
  apiFetch<{ ok: true }>(`/nodes/${id}/analysis_excluded`, {
    method: 'PATCH',
    body: JSON.stringify({ excluded }),
  });

export const patchNodeOpened = (id: number) =>
  apiFetch<{ ok: true }>(`/nodes/${id}/opened`, { method: 'PATCH' });

export const lookupNodes = (body: LookupNodesBody) =>
  apiFetch<{ results: Record<string, NodeLookupRow> }>('/nodes/lookup', {
    method: 'POST',
    body: JSON.stringify(body),
  });

// ---------------- Node external launch (F4b slice 4) ----------------

export const openNodeInBrowser = (id: number) =>
  apiFetch<{ ok: true; browser: string; opened_at: string }>(
    `/nodes/${id}/open`,
    { method: 'POST' },
  );

// ---------------- Flags ----------------

export const createFlag = (body: CreateFlagBody) =>
  apiFetch<FlagRow>('/flags', {
    method: 'POST',
    body: JSON.stringify(body),
  });

// Clear every flag for a node — backs the right-click "Remove Flag"
// toggle. The graph payload only exposes `flag_status`, not the flag
// id, so the toggle is node-scoped on both ends.
export const clearNodeFlags = (node_id: number) =>
  apiFetch<{ ok: true; cleared: number }>(`/nodes/${node_id}/flags`, {
    method: 'DELETE',
  });
