import { describe, expect, it } from 'vitest';

import type { AnalysisRow } from '$lib/api';
import {
  resultPlaceholder,
  shouldPoll,
  statusBadge,
} from './analysisStatus';

function row(overrides: Partial<AnalysisRow> = {}): AnalysisRow {
  return {
    id: 1,
    resource_id: 10,
    analysis_type: 'Summary',
    model: 'qwen2.5:3b',
    status: 'pending',
    job_id: 1,
    result: null,
    question: null,
    priority: 0,
    created_at: '2026-05-27T00:00:00Z',
    updated_at: '2026-05-27T00:00:00Z',
    ...overrides,
  };
}

describe('statusBadge', () => {
  it('done → teal "done" with no tooltip', () => {
    expect(statusBadge('done')).toEqual({
      label: 'done',
      tone: 'good',
      tooltip: '',
    });
  });
  it('pending → amber "pending"', () => {
    expect(statusBadge('pending').tone).toBe('warn');
  });
  it('running → live "running"', () => {
    expect(statusBadge('running').tone).toBe('live');
  });
  it('paused → wait tone', () => {
    expect(statusBadge('paused').tone).toBe('wait');
  });
  it('failed/cancelled → bad tone', () => {
    expect(statusBadge('failed').tone).toBe('bad');
    expect(statusBadge('cancelled').tone).toBe('bad');
  });
});

describe('resultPlaceholder', () => {
  it('returns null when no row is selected', () => {
    expect(resultPlaceholder(null)).toBeNull();
  });
  it('done + result → show body', () => {
    const r = row({ status: 'done', result: 'Two-sentence summary.' });
    expect(resultPlaceholder(r)).toEqual({
      kind: 'show',
      body: 'Two-sentence summary.',
    });
  });
  it('done + empty result → "No result yet." message', () => {
    const r = row({ status: 'done', result: '' });
    expect(resultPlaceholder(r)).toEqual({
      kind: 'message',
      text: 'No result yet.',
    });
  });
  it('pending → "In queue…"', () => {
    expect(resultPlaceholder(row({ status: 'pending' }))?.kind).toBe(
      'message',
    );
  });
  it('running → "Running…"', () => {
    const p = resultPlaceholder(row({ status: 'running' }));
    expect(p).toMatchObject({ kind: 'message', text: 'Running…' });
  });
  it('paused/failed/cancelled → terminal message', () => {
    expect(resultPlaceholder(row({ status: 'paused' }))).toMatchObject({
      kind: 'message',
      text: 'Paused.',
    });
    expect(resultPlaceholder(row({ status: 'failed' }))).toMatchObject({
      kind: 'message',
      text: 'Failed.',
    });
    expect(resultPlaceholder(row({ status: 'cancelled' }))).toMatchObject({
      kind: 'message',
      text: 'Cancelled.',
    });
  });
  it('null status (no linked job) → null', () => {
    expect(resultPlaceholder(row({ status: null }))).toBeNull();
  });
});

describe('shouldPoll', () => {
  it('false when every row is done or terminal', () => {
    expect(
      shouldPoll([row({ status: 'done' }), row({ status: 'cancelled' })]),
    ).toBe(false);
  });
  it('true when any row is pending or running', () => {
    expect(shouldPoll([row({ status: 'pending' })])).toBe(true);
    expect(
      shouldPoll([row({ status: 'done' }), row({ status: 'running' })]),
    ).toBe(true);
  });
});
