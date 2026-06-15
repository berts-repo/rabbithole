// Crawl-intake HTTP surface — the `POST /api/crawl/queue` enqueue endpoint on
// backend/backend/routes/crawl_queue.py. Listing, editing, cancelling and the
// live stream of crawl jobs are owned by the unified jobs API (`$lib/api/jobs`)
// and surfaced in the bottom-pane Activity tab.

import { apiFetch } from './core';
import type { ResourceState } from './types';

// --- Shared shapes ----------------------------------------------------------

export type CrawlQueueMode =
  | 'Cross-site'
  | 'BFS'
  | 'DFS'
  | 'Diverse'
  | 'Focused';

export type CrawlQueueSource =
  | 'manual'
  | 'bulk'
  | 'bookmark'
  | 'collection'
  | 'bottom_pane'
  | 'search'
  | 'graph_menu'
  | 'right_pane'
  | 'schedule';

export interface EnqueueResult {
  url: string;
  inserted: boolean;
  job_id?: number | null;
  // The resource's current lifecycle state at intake (`unknown` when never seen).
  state: ResourceState;
  reason: 'ok' | 'duplicate_active' | 'duplicate_in_batch' | 'bad_url';
  message?: string;
}

// --- Request body -----------------------------------------------------------

export interface EnqueueBody {
  url?: string;
  urls?: string[];
  mode: CrawlQueueMode;
  source: CrawlQueueSource;
  stay_on_domain?: boolean;
  // Omit to let the backend apply the default cap of 3, or pass `null`
  // for "unlimited" (which the UI must surface to the analyst). When
  // `use_default_max_depth` is true the helper ignores `max_depth`.
  max_depth?: number | null;
  use_default_max_depth?: boolean;
  collection_id?: number | null;
  collection_name_pending?: string | null;
  priority?: number;
}

// --- Calls ------------------------------------------------------------------

export const enqueueCrawl = (body: EnqueueBody) =>
  apiFetch<{ results: EnqueueResult[] }>('/crawl/queue', {
    method: 'POST',
    body: JSON.stringify(body),
  });
