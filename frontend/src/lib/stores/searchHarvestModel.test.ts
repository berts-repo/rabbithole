import { describe, it, expect } from 'vitest';
import type { HarvestUrlEvent } from '$lib/api';
import {
  applyProbe,
  classifyEmpty,
  resultFromUrlEvent,
  sourceBadge,
  type EmptyInput,
  type SourceStatus,
} from './searchHarvestModel';

function urlEvent(over: Partial<HarvestUrlEvent> = {}): HarvestUrlEvent {
  return {
    engine: 'Ahmia',
    url: 'http://example.onion/',
    crawled: false,
    anchor_text: null,
    ...over,
  };
}

describe('resultFromUrlEvent', () => {
  it('maps an uncrawled event to a bare, unprobed row', () => {
    const r = resultFromUrlEvent(urlEvent({ anchor_text: 'click me' }));
    expect(r).toMatchObject({
      url: 'http://example.onion/',
      engineLabel: 'Ahmia',
      crawled: false,
      anchorText: 'click me',
      nodeId: null,
      title: null,
      probed: false,
    });
  });

  it('carries crawled metadata when present', () => {
    const r = resultFromUrlEvent(
      urlEvent({
        crawled: true,
        node_id: 42,
        title: 'Market',
        category: 'market',
        last_seen: '2026-05-12T00:00:00+00:00',
      }),
    );
    expect(r.crawled).toBe(true);
    expect(r.nodeId).toBe(42);
    expect(r.title).toBe('Market');
    expect(r.category).toBe('market');
    expect(r.lastSeen).toBe('2026-05-12T00:00:00+00:00');
  });
});

describe('applyProbe', () => {
  it('fills title/description and marks probed', () => {
    const row = resultFromUrlEvent(urlEvent());
    const next = applyProbe(row, 'Probed Title', 'a description');
    expect(next.title).toBe('Probed Title');
    expect(next.description).toBe('a description');
    expect(next.probed).toBe(true);
  });

  it('keeps an existing title when the probe has none', () => {
    const row = { ...resultFromUrlEvent(urlEvent()), title: 'kept' };
    const next = applyProbe(row, null, null);
    expect(next.title).toBe('kept');
    expect(next.probed).toBe(true);
  });
});

describe('sourceBadge', () => {
  it('renders searching / done / error tones', () => {
    expect(sourceBadge({ kind: 'searching' })).toEqual({ label: '…', tone: 'wait' });
    expect(sourceBadge({ kind: 'done', count: 12 })).toEqual({ label: '12', tone: 'good' });
    expect(sourceBadge({ kind: 'error', reason: 'connection' })).toEqual({
      label: 'error',
      tone: 'bad',
    });
    expect(sourceBadge({ kind: 'error', reason: 'timeout' })).toEqual({
      label: 'timed out',
      tone: 'bad',
    });
  });

  it('is null for an unknown source', () => {
    expect(sourceBadge(undefined)).toBeNull();
  });
});

describe('classifyEmpty', () => {
  const base: EmptyInput = {
    loaded: true,
    engineCount: 2,
    resultCount: 0,
    searching: false,
    ran: false,
    searchedStatuses: [],
  };

  it('no-engines when loaded with none configured', () => {
    expect(classifyEmpty({ ...base, engineCount: 0 })).toBe('no-engines');
  });

  it('before-first-search when nothing has run', () => {
    expect(classifyEmpty(base)).toBe('before');
  });

  it('no empty state while searching or once results exist', () => {
    expect(classifyEmpty({ ...base, searching: true })).toBeNull();
    expect(classifyEmpty({ ...base, resultCount: 3, ran: true })).toBeNull();
  });

  it('no-results when a search ran clean with mixed source outcomes', () => {
    const statuses: (SourceStatus | undefined)[] = [
      { kind: 'done', count: 0 },
      { kind: 'error', reason: 'connection' },
    ];
    expect(
      classifyEmpty({ ...base, ran: true, searchedStatuses: statuses }),
    ).toBe('no-results');
  });

  it('failed-connection when every source failed connectively', () => {
    const statuses: (SourceStatus | undefined)[] = [
      { kind: 'error', reason: 'connection' },
      { kind: 'error', reason: 'timeout' },
    ];
    expect(
      classifyEmpty({ ...base, ran: true, searchedStatuses: statuses }),
    ).toBe('failed-connection');
  });

  it('failed-other when every source failed but not all connectively', () => {
    const statuses: (SourceStatus | undefined)[] = [
      { kind: 'error', reason: 'connection' },
      { kind: 'error', reason: 'unreadable' },
    ];
    expect(
      classifyEmpty({ ...base, ran: true, searchedStatuses: statuses }),
    ).toBe('failed-other');
  });
});
