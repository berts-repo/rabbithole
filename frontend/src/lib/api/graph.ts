// Graph routes — the payload fetch, the Hidden-tab filter terms, the
// analyst edges, and the binary export endpoint paths.

import { apiFetch, qs, BASE } from './core';
import type { GraphPayload, CreateEdgeBody } from './types';

// ---------------- Graph ----------------

export const getGraph = (collectionId?: number | null) =>
  apiFetch<GraphPayload>(
    `/graph${qs({ collection_id: collectionId ?? undefined })}`,
  );

// ---------------- Graph filters (Hidden sub-tab) ----------------

export const listGraphFilters = () =>
  apiFetch<{ terms: string[] }>('/graph-filters');

export const addGraphFilter = (term: string) =>
  apiFetch<{ term: string }>('/graph-filters', {
    method: 'POST',
    body: JSON.stringify({ term }),
  });

export const deleteGraphFilter = (term: string) =>
  apiFetch<{ ok: true }>(
    `/graph-filters/${encodeURIComponent(term)}`,
    { method: 'DELETE' },
  );

// ---------------- Edges ----------------

export const createEdge = (body: CreateEdgeBody) =>
  apiFetch<{ ok: true }>('/edges', { method: 'POST', body: JSON.stringify(body) });

export const deleteEdge = (from_id: number, to_id: number) =>
  apiFetch<{ ok: true }>(`/edges${qs({ from_id, to_id })}`, { method: 'DELETE' });

// Export endpoints return binary streams — consumers use these paths
// directly with <a download> rather than apiFetch.
export const EXPORT_GEXF_PATH = `${BASE}/export/gexf`;
export const EXPORT_NODES_CSV_PATH = `${BASE}/export/nodes-csv`;
