// Pure model for the Search tab harvest store. Kept free of runes / DOM so it
// runs under the plain-node vitest config (same split as intelComposeTarget.ts
// vs. intelCompose.svelte.ts): the .svelte.ts store wraps these and owns the
// reactive state + SSE lifecycle; the logic worth testing lives here.

import type { HarvestErrorReason, HarvestUrlEvent } from '$lib/api';

export interface SearchResult {
  url: string;
  /** Engine label that surfaced this URL first. */
  engineLabel: string;
  crawled: boolean;
  anchorText: string | null;
  // Crawled rows carry local DB metadata; uncrawled rows fill title/description
  // from a probe (if one lands).
  nodeId: number | null;
  title: string | null;
  category: string | null;
  lastSeen: string | null;
  description: string | null;
  /** Uncrawled only: a probe has completed for this URL. */
  probed: boolean;
}

export type SourceStatus =
  | { kind: 'searching' }
  | { kind: 'done'; count: number }
  | { kind: 'error'; reason: HarvestErrorReason };

export type SearchEmptyState =
  | 'no-engines'
  | 'before'
  | 'no-results'
  | 'failed-connection'
  | 'failed-other';

/** Build a result row from an incoming URL event. */
export function resultFromUrlEvent(ev: HarvestUrlEvent): SearchResult {
  return {
    url: ev.url,
    engineLabel: ev.engine,
    crawled: ev.crawled,
    anchorText: ev.anchor_text,
    nodeId: ev.node_id ?? null,
    title: ev.title ?? null,
    category: ev.category ?? null,
    lastSeen: ev.last_seen ?? null,
    description: null,
    probed: false,
  };
}

/** Fold a probe result into an existing (uncrawled) row. */
export function applyProbe(
  row: SearchResult,
  title: string | null,
  description: string | null,
): SearchResult {
  return { ...row, title: title ?? row.title, description, probed: true };
}

export interface SourceBadge {
  label: string;
  tone: 'wait' | 'good' | 'bad';
}

/** Per-source status pill content while/after searching. */
export function sourceBadge(s: SourceStatus | undefined): SourceBadge | null {
  if (!s) return null;
  if (s.kind === 'searching') return { label: '…', tone: 'wait' };
  if (s.kind === 'done') return { label: String(s.count), tone: 'good' };
  return {
    label: s.reason === 'timeout' ? 'timed out' : 'error',
    tone: 'bad',
  };
}

export interface EmptyInput {
  loaded: boolean;
  engineCount: number;
  resultCount: number;
  searching: boolean;
  ran: boolean;
  /** Statuses of the engines actually queried by the last/in-flight search. */
  searchedStatuses: (SourceStatus | undefined)[];
}

/**
 * Which empty state (if any) the results pane should show. Encodes the spec's
 * five cases, including the connection-vs-other split when every source failed
 * — keyed off the coarse failure reasons the backend now reports.
 */
export function classifyEmpty(i: EmptyInput): SearchEmptyState | null {
  if (i.loaded && i.engineCount === 0) return 'no-engines';
  if (i.resultCount > 0 || i.searching) return null;
  if (!i.ran) return 'before';
  const errored = i.searchedStatuses.filter((s) => s?.kind === 'error');
  if (
    i.searchedStatuses.length > 0 &&
    errored.length === i.searchedStatuses.length
  ) {
    const allConnective = errored.every(
      (s) =>
        s?.kind === 'error' &&
        (s.reason === 'connection' || s.reason === 'timeout'),
    );
    return allConnective ? 'failed-connection' : 'failed-other';
  }
  return 'no-results';
}
