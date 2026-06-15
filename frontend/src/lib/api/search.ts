// Find sub-tab lookup over already-crawled data — keyword (FTS5 + findings)
// and semantic (vector ANN). Distinct from the outbound engine Search tab.
//
// Keyword results are a discriminated union of page / entity / note rows, the
// three things the analyst may have stashed text in. Semantic results carry a
// 0–1 `score` (higher = closer): the backend speaks vec0 `distance` (lower =
// closer), so we convert at the boundary here and the rest of the app sees the
// spec's similarity vocabulary.

import { ApiError, apiFetch, qs } from './core';

export interface KeywordPageResult {
  type: 'page';
  node_id: number;
  url: string;
  title: string | null;
  snippet: string;
}

export interface KeywordEntityResult {
  type: 'entity';
  node_id: number;
  url: string;
  entity_type: string | null;
  value: string;
}

export interface KeywordNoteResult {
  type: 'note';
  node_id: number;
  url: string;
  snippet: string;
}

export type KeywordResult =
  | KeywordPageResult
  | KeywordEntityResult
  | KeywordNoteResult;

export interface SemanticResult {
  node_id: number;
  url: string;
  title: string | null;
  // 0–1, higher = closer (derived from the backend's vec0 distance).
  score: number;
}

// Raised so the Find store can show the spec's "start the embedding service"
// empty state rather than a generic error toast.
export class EmbedUnavailableError extends Error {
  constructor(message = 'embedding service unavailable') {
    super(message);
    this.name = 'EmbedUnavailableError';
  }
}

export async function keywordSearch(
  q: string,
  limit = 50,
): Promise<KeywordResult[]> {
  const res = await apiFetch<{ results: KeywordResult[] }>(
    `/search/keyword${qs({ q, limit })}`,
  );
  return res.results;
}

// vec0 cosine distance (lower = closer) → similarity score (0–1, higher =
// closer). Clamped so float noise can't escape the unit interval.
export function distanceToScore(distance: number): number {
  return Math.max(0, Math.min(1, 1 - distance));
}

export async function semanticSearch(
  q: string,
  limit = 50,
): Promise<SemanticResult[]> {
  let res: { results: { node_id: number; url: string; title: string | null; distance: number }[] };
  try {
    res = await apiFetch(`/search/semantic${qs({ q, limit })}`);
  } catch (err) {
    // 503 embed_unavailable → typed so the UI can branch on it.
    if (err instanceof ApiError && err.status === 503) {
      throw new EmbedUnavailableError();
    }
    throw err;
  }
  return res.results.map((r) => ({
    node_id: r.node_id,
    url: r.url,
    title: r.title,
    score: distanceToScore(r.distance),
  }));
}
