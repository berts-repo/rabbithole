// SSE-backed ring buffer for the Live Crawl sub-tab.
//
// One subscription to /api/crawl/log per page lifetime. The backend
// replays the last 200 entries on (re)connect (`replay_log=True` in
// routes/crawl.py), so a late subscribe still shows recent context.
// The store mirrors that 200-entry cap locally so a long-running tab
// can't grow unbounded.
//
// Subscription is ref-counted: the first subscriber opens the EventSource
// (via $lib/sse manager), subsequent subscribers reuse it, and the last
// unsubscribe tears it down. LiveCrawlTab calls subscribe() in onMount;
// every other consumer of crawl.log (currently none) gets the same
// shared stream.
//
// Buffer entries are typed CrawlLogEntry — already parsed for URL +
// status + severity so the view layer just maps them to rows.

import { sse } from '$lib/sse.svelte';
import { CRAWL_LOG_PATH } from '$lib/api';
import { parseLogMessage, type CrawlLogEntry } from '../../views/bottom/liveCrawl';

const BUFFER_LIMIT = 200;

interface LogEnvelope {
  channel?: string;
  ts?: number;
  message?: string;
  type?: string;
  count?: number;
}

interface CrawlLogState {
  entries: CrawlLogEntry[];
  unsub: (() => void) | null;
  refCount: number;
  nextId: number;
}

const state = $state<CrawlLogState>({
  entries: [],
  unsub: null,
  refCount: 0,
  nextId: 1,
});

function appendEntry(entry: CrawlLogEntry): void {
  const next = state.entries.slice();
  next.push(entry);
  if (next.length > BUFFER_LIMIT) {
    next.splice(0, next.length - BUFFER_LIMIT);
  }
  state.entries = next;
}

function onMessage(e: MessageEvent): void {
  let env: LogEnvelope;
  try {
    env = JSON.parse(e.data);
  } catch {
    return;
  }
  if (env.type === '_dropped') {
    // Bus overflow sentinel — surface it as its own row so the analyst
    // sees the gap rather than wondering why messages stopped landing.
    const id = state.nextId++;
    appendEntry({
      localId: id,
      ts: env.ts ?? Date.now() / 1000,
      message: `[buffer overflow — ${env.count ?? 0} message(s) lost]`,
      url: null,
      status: null,
      severity: 'warn',
      dropped: env.count ?? 0,
    });
    return;
  }
  if (env.channel !== 'crawl.log') return;
  const msg = typeof env.message === 'string' ? env.message : '';
  if (!msg) return;
  const id = state.nextId++;
  appendEntry(parseLogMessage(msg, env.ts ?? Date.now() / 1000, id));
}

export const crawlLogStore = {
  get entries(): readonly CrawlLogEntry[] {
    return state.entries;
  },
  get subscribed(): boolean {
    return state.unsub !== null;
  },

  /**
   * Open (or share) the /api/crawl/log subscription. Returns an
   * unsubscribe callback the caller MUST invoke on teardown — the last
   * call closes the EventSource and lets the SSE manager release it.
   *
   * The buffer itself survives unsubscribe so a tab switch away from
   * Live Crawl and back doesn't lose the recent context.
   */
  subscribe(): () => void {
    state.refCount += 1;
    if (state.unsub === null) {
      state.unsub = sse.subscribe(CRAWL_LOG_PATH, { onMessage });
    }
    let released = false;
    return () => {
      if (released) return;
      released = true;
      state.refCount -= 1;
      if (state.refCount <= 0) {
        state.refCount = 0;
        state.unsub?.();
        state.unsub = null;
      }
    };
  },

  /** Drop every buffered entry. Wired to the "Clear" button in the tab. */
  clear(): void {
    state.entries = [];
  },

  /** Test helper. */
  _reset(): void {
    state.entries = [];
    state.refCount = 0;
    state.unsub?.();
    state.unsub = null;
    state.nextId = 1;
  },
};
