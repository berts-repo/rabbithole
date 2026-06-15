// Pure helpers for LiveCrawlTab — log-line parsing + color mapping.
// Vitest covers these so the SSE store and the Svelte component don't
// have to instantiate to test the parsing rules.

// Loose .onion URL extractor for log messages. Backend log lines aren't
// required to put the URL anywhere particular, so we scan the whole line.
// Case-insensitive (v3 onions are base32; the host is lowercase in
// practice but tolerant matching avoids surprises).
const ONION_URL_IN_LINE =
  /https?:\/\/[a-z2-7]{56}\.onion(?::\d{1,5})?(?:\/[^\s,)]*)?/i;

// `status=NNN` token inside the message — the crawler emits this on every
// success / skip line. Failure lines don't have it; we fall back to null.
const STATUS_TOKEN = /\bstatus=(\d{3})\b/;

export type LogSeverity = 'ok' | 'warn' | 'error' | 'info';

export interface CrawlLogEntry {
  // Monotonic local id — buffer needs a stable each-key. SSE envelopes
  // don't ship an id, so we assign here.
  localId: number;
  // Timestamp from the SSE envelope (`ts`, seconds float). When the
  // envelope is missing one (e.g. the dropped sentinel), we fall back
  // to Date.now()/1000 at receive time.
  ts: number;
  message: string;
  // Extracted from the message body; null when neither pattern matches.
  url: string | null;
  status: number | null;
  severity: LogSeverity;
  // `_dropped` sentinel envelopes come through as their own entry so the
  // analyst notices a buffer overflow rather than silently losing lines.
  dropped?: number;
}

export function extractOnionUrl(message: string): string | null {
  const m = ONION_URL_IN_LINE.exec(message);
  return m ? m[0] : null;
}

export function extractStatusCode(message: string): number | null {
  const m = STATUS_TOKEN.exec(message);
  if (!m) return null;
  const n = parseInt(m[1], 10);
  return Number.isFinite(n) ? n : null;
}

export function severityFor(
  message: string,
  status: number | null,
): LogSeverity {
  if (status !== null) {
    if (status >= 500) return 'error';
    if (status >= 400) return 'error';
    if (status >= 300) return 'warn';
    if (status >= 200) return 'ok';
  }
  // Heuristic: known failure-leading messages map to error/warn even
  // when no status code is present (the crawler emits these on transport
  // errors that never produced a response).
  const low = message.toLowerCase();
  if (low.startsWith('fetch failed') || low.startsWith('response too large')) {
    return 'error';
  }
  if (
    low.startsWith('redirect rejected') ||
    low.startsWith('skipped')
  ) {
    return 'warn';
  }
  return 'info';
}

export function parseLogMessage(
  message: string,
  ts: number,
  localId: number,
): CrawlLogEntry {
  const url = extractOnionUrl(message);
  const status = extractStatusCode(message);
  return {
    localId,
    ts,
    message,
    url,
    status,
    severity: severityFor(message, status),
  };
}

/** Case-insensitive substring filter over message + URL. */
export function filterEntries(
  entries: CrawlLogEntry[],
  filter: string,
): CrawlLogEntry[] {
  const q = filter.trim().toLowerCase();
  if (!q) return entries;
  return entries.filter((e) => {
    if (e.message.toLowerCase().includes(q)) return true;
    if (e.url && e.url.toLowerCase().includes(q)) return true;
    return false;
  });
}

/** `HH:MM:SS` from a float-seconds timestamp. */
export function formatTime(ts: number): string {
  const ms = Number.isFinite(ts) ? ts * 1000 : Date.now();
  const d = new Date(ms);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  const ss = String(d.getSeconds()).padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
}
