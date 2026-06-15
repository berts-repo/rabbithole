// Outbound dark-web Search tab — engine harvest SSE.
//
// The backend (`routes/harvest_search.py`) queries each enabled engine's
// result page through Tor, streams discovered `.onion` URLs as they're parsed,
// and (unless passive mode is on) probes each *uncrawled* hit for a live
// title/description. This module is types + the stream path only; the
// EventSource lifecycle is the shared `$lib/sse` manager, driven by the
// searchHarvest store.
//
// Distinct from `$lib/api/search` (the inbound Find lookup over already-crawled
// data). Search = outbound discovery; Find = inbound recall.

import { BASE, qs } from './core';

// --- SSE event union (mirror of the backend's documented shapes) ----------

/** A discovered URL row. `type` is absent on these (the default message). */
export interface HarvestUrlEvent {
  type?: undefined;
  engine: string;
  url: string;
  crawled: boolean;
  anchor_text: string | null;
  // Present only when `crawled` — sourced from the local DB, not a probe.
  node_id?: number;
  title?: string | null;
  category?: string | null;
  last_seen?: string | null;
}

/** A live probe result for a previously-unknown URL. */
export interface HarvestProbeEvent {
  type: 'probe';
  url: string;
  title: string | null;
  description: string | null;
}

/** A source finished; `count` = total URLs it returned. */
export interface HarvestDoneEvent {
  type: 'done';
  engine: string;
  count: number;
}

/** Coarse failure reason driving the badge + "all sources failed" copy. */
export type HarvestErrorReason =
  | 'connection'
  | 'timeout'
  | 'unreadable'
  | 'invalid';

/** A source failed. */
export interface HarvestErrorEvent {
  type: 'error';
  engine: string;
  message: string;
  reason: HarvestErrorReason;
}

/** Early per-engine heartbeat as the request opens. */
export interface HarvestStatusEvent {
  type: 'status';
  engine: string;
  state: string;
}

/** Terminal event; the stream closes after this. `reason: 'no_engines'`
 *  when nothing was queryable. */
export interface HarvestAllDoneEvent {
  type: 'all_done';
  reason?: string;
}

export type HarvestEvent =
  | HarvestUrlEvent
  | HarvestProbeEvent
  | HarvestDoneEvent
  | HarvestErrorEvent
  | HarvestStatusEvent
  | HarvestAllDoneEvent;

/**
 * Build the SSE path for a query + per-session engine selection. `engineIds`
 * empty means "let the backend use every enabled engine"; otherwise it's the
 * analyst's source-selector subset (intersected server-side with enabled).
 */
export function harvestSearchPath(q: string, engineIds: number[]): string {
  return `${BASE}/harvest/search${qs({
    q,
    engines: engineIds.length > 0 ? engineIds.join(',') : undefined,
  })}`;
}
