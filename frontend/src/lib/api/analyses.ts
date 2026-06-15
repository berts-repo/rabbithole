// Per-node analysis queue routes + collection synthesis + cluster analyses.

import { apiFetch, qs } from './core';
import type {
  AnalysesBatchResult,
  AnalysisQueueCounts,
  AnalysisRow,
  AnalyzedNodeRow,
  ClusterAnalysisRow,
  CollectionAnalysisRow,
  CreateAnalysesBatchBody,
  CreateAnalysisBody,
  CreateClusterAnalysisBody,
  CreateCollectionAnalysisBody,
} from './types';

export interface ListAnalysesOptions {
  status?: string | null;
  nodeId?: number | null;
  limit?: number;
}

export const listAnalyses = (opts: ListAnalysesOptions = {}) =>
  apiFetch<{ analyses: AnalysisRow[]; counts: AnalysisQueueCounts }>(
    `/analyses${qs({
      status_filter: opts.status ?? undefined,
      node_id: opts.nodeId ?? undefined,
      limit: opts.limit ?? undefined,
    })}`,
  );

// Nodes with ≥1 successful completed analysis — backs the "Analyzed" tab.
export const listAnalyzedNodes = (limit = 200) =>
  apiFetch<{ nodes: AnalyzedNodeRow[] }>(`/analyzed-nodes${qs({ limit })}`);

export const createAnalysis = (body: CreateAnalysisBody) =>
  apiFetch<{ id: number; status: string }>('/analyses', {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const createAnalysesBatch = (body: CreateAnalysesBatchBody) =>
  apiFetch<AnalysesBatchResult>('/analyses/batch', {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const deleteAnalysis = (id: number) =>
  apiFetch<{ ok: true; id: number }>(`/analyses/${id}`, { method: 'DELETE' });

export const rerunAnalysis = (id: number) =>
  apiFetch<{ ok: true; id: number; status: string }>(
    `/analyses/${id}/rerun`,
    { method: 'POST' },
  );

// --- collection synthesis ---------------------------------------------------

export const listCollectionAnalyses = (collectionId: number) =>
  apiFetch<{ collection_id: number; analyses: CollectionAnalysisRow[] }>(
    `/collections/${collectionId}/analyses`,
  );

export const createCollectionAnalysis = (
  collectionId: number,
  body: CreateCollectionAnalysisBody,
) =>
  apiFetch<{ id: number; status: string }>(
    `/collections/${collectionId}/analyses`,
    { method: 'POST', body: JSON.stringify(body) },
  );

// --- cluster analyses (item 7, D1) -----------------------------------------
// The server derives the fingerprint from resource_ids, so callers pass the
// live cluster membership and never compute the key themselves.

export const listClusterAnalyses = (fingerprint: string) =>
  apiFetch<{ fingerprint: string; analyses: ClusterAnalysisRow[] }>(
    `/clusters/${encodeURIComponent(fingerprint)}/analyses`,
  );

export const createClusterAnalysis = (body: CreateClusterAnalysisBody) =>
  apiFetch<{ id: number; fingerprint: string; status: string }>(
    '/clusters/analyses',
    { method: 'POST', body: JSON.stringify(body) },
  );

export const getClusterAnalysis = (id: number) =>
  apiFetch<ClusterAnalysisRow>(`/cluster-analyses/${id}`);

export const deleteClusterAnalysis = (id: number) =>
  apiFetch<{ deleted: number }>(`/cluster-analyses/${id}`, {
    method: 'DELETE',
  });
