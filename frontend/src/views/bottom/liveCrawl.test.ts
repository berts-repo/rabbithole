import { describe, it, expect } from 'vitest';
import {
  extractOnionUrl,
  extractStatusCode,
  filterEntries,
  formatTime,
  parseLogMessage,
  severityFor,
  type CrawlLogEntry,
} from './liveCrawl';

const ONION = 'a'.repeat(56) + '.onion';
const URL_OK = `http://${ONION}/`;

describe('liveCrawl helpers', () => {
  it('extracts onion URLs from log lines', () => {
    expect(extractOnionUrl(`crawled: ${URL_OK} status=200 entities=2 links=5`)).toBe(URL_OK);
    expect(extractOnionUrl(`fetch failed: ${URL_OK} (timeout)`)).toBe(URL_OK);
    expect(extractOnionUrl('no url here')).toBeNull();
    // Bad host length is rejected.
    expect(extractOnionUrl('http://shortname.onion/')).toBeNull();
  });

  it('extracts status codes', () => {
    expect(extractStatusCode('crawled: x status=200 entities=0')).toBe(200);
    expect(extractStatusCode('skipped (non-html): x status=404')).toBe(404);
    expect(extractStatusCode('fetch failed: x (timeout)')).toBeNull();
    // The status= token must be 3 digits surrounded by word boundaries.
    expect(extractStatusCode('status=2000')).toBeNull();
  });

  it('maps severity by status code, then heuristic', () => {
    expect(severityFor('crawled: x status=200', 200)).toBe('ok');
    expect(severityFor('crawled: x status=301', 301)).toBe('warn');
    expect(severityFor('crawled: x status=404', 404)).toBe('error');
    expect(severityFor('crawled: x status=503', 503)).toBe('error');
    expect(severityFor('fetch failed: x (boom)', null)).toBe('error');
    expect(severityFor('response too large: x', null)).toBe('error');
    expect(severityFor('skipped (non-html): x', null)).toBe('warn');
    expect(severityFor('redirect rejected: x (loop)', null)).toBe('warn');
    expect(severityFor('something else', null)).toBe('info');
  });

  it('builds an entry from a message + ts + id', () => {
    const e = parseLogMessage(`crawled: ${URL_OK} status=200`, 100, 42);
    expect(e.localId).toBe(42);
    expect(e.ts).toBe(100);
    expect(e.url).toBe(URL_OK);
    expect(e.status).toBe(200);
    expect(e.severity).toBe('ok');
  });

  it('filters entries by message + url substring', () => {
    const entries: CrawlLogEntry[] = [
      parseLogMessage(`crawled: ${URL_OK} status=200`, 100, 1),
      parseLogMessage('fetch failed: http://b.onion/ (timeout)', 101, 2),
    ];
    expect(filterEntries(entries, '').length).toBe(2);
    expect(filterEntries(entries, 'failed').length).toBe(1);
    expect(filterEntries(entries, 'crawled')).toEqual([entries[0]]);
    // URL search works even when the message doesn't include the keyword.
    expect(filterEntries(entries, ONION.slice(0, 8)).length).toBeGreaterThan(0);
  });

  it('formats ts as HH:MM:SS', () => {
    expect(/^\d{2}:\d{2}:\d{2}$/.test(formatTime(1700000000))).toBe(true);
    expect(/^\d{2}:\d{2}:\d{2}$/.test(formatTime(0))).toBe(true);
    // Non-finite falls back to now() — still valid format.
    expect(/^\d{2}:\d{2}:\d{2}$/.test(formatTime(Number.NaN))).toBe(true);
  });
});
