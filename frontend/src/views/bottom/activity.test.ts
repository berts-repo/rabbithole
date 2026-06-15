import { describe, it, expect } from 'vitest';
import type { Job, JobKind, JobStatus, JobTargetType } from '$lib/api';
import {
  batchUrlCount,
  canCancel,
  canOpenTarget,
  canPause,
  canResume,
  canRetry,
  canRunBatch,
  extractProgress,
  filterByKind,
  formatJobTime,
  groupJobs,
  isTerminal,
  parseJobsChange,
  probeContentChanged,
  recencyKey,
  sortJobsByRecency,
  toActivityRow,
} from './activity';

function makeJob(over: Partial<Job> = {}): Job {
  return {
    id: 1,
    kind: 'crawl' as JobKind,
    target_type: 'url' as JobTargetType,
    target_id: 100,
    status: 'pending' as JobStatus,
    payload: null,
    result: null,
    error: null,
    created_at: null,
    started_at: null,
    finished_at: null,
    ...over,
  };
}

describe('parseJobsChange', () => {
  it('parses a well-formed jobs.changed envelope', () => {
    const raw = JSON.stringify({
      channel: 'jobs.changed',
      ts: 1717459200.5,
      job_id: 42,
      kind: 'crawl',
      status: 'running',
    });
    expect(parseJobsChange(raw)).toEqual({
      job_id: 42,
      kind: 'crawl',
      status: 'running',
    });
  });

  it('ignores extra envelope fields (source/url) workers may attach', () => {
    const raw = JSON.stringify({
      channel: 'jobs.changed',
      job_id: 7,
      kind: 'crawl',
      status: 'pending',
      source: 'schedule',
      url: 'http://x.onion/',
    });
    expect(parseJobsChange(raw)).toEqual({
      job_id: 7,
      kind: 'crawl',
      status: 'pending',
    });
  });

  it('rejects envelopes on a different channel', () => {
    const raw = JSON.stringify({
      channel: 'crawl.log',
      job_id: 1,
      kind: 'crawl',
      status: 'running',
    });
    expect(parseJobsChange(raw)).toBeNull();
  });

  it('rejects non-JSON payloads', () => {
    expect(parseJobsChange('not json')).toBeNull();
    expect(parseJobsChange('')).toBeNull();
  });

  it('rejects envelopes missing or mistyping the required trio', () => {
    // job_id must be a number (SSE never quotes it, but guard anyway)
    expect(
      parseJobsChange(
        JSON.stringify({ channel: 'jobs.changed', job_id: '5', kind: 'crawl', status: 'done' }),
      ),
    ).toBeNull();
    // missing kind
    expect(
      parseJobsChange(JSON.stringify({ channel: 'jobs.changed', job_id: 5, status: 'done' })),
    ).toBeNull();
    // missing status
    expect(
      parseJobsChange(JSON.stringify({ channel: 'jobs.changed', job_id: 5, kind: 'probe' })),
    ).toBeNull();
    // no channel
    expect(
      parseJobsChange(JSON.stringify({ job_id: 5, kind: 'probe', status: 'done' })),
    ).toBeNull();
  });
});

describe('action gating (mirrors routes/jobs.py)', () => {
  it('treats done/failed/cancelled as terminal', () => {
    expect(isTerminal('done')).toBe(true);
    expect(isTerminal('failed')).toBe(true);
    expect(isTerminal('cancelled')).toBe(true);
    expect(isTerminal('pending')).toBe(false);
    expect(isTerminal('running')).toBe(false);
    expect(isTerminal('paused')).toBe(false);
  });

  it('cancel offered only on non-terminal jobs', () => {
    expect(canCancel('pending')).toBe(true);
    expect(canCancel('running')).toBe(true);
    expect(canCancel('paused')).toBe(true);
    expect(canCancel('done')).toBe(false);
    expect(canCancel('failed')).toBe(false);
    expect(canCancel('cancelled')).toBe(false);
  });

  it('retry offered only on terminal jobs', () => {
    expect(canRetry('done')).toBe(true);
    expect(canRetry('failed')).toBe(true);
    expect(canRetry('cancelled')).toBe(true);
    expect(canRetry('pending')).toBe(false);
    expect(canRetry('running')).toBe(false);
    expect(canRetry('paused')).toBe(false);
  });

  it('pause only pending, resume only paused', () => {
    expect(canPause('pending')).toBe(true);
    expect(canPause('running')).toBe(false);
    expect(canPause('paused')).toBe(false);
    expect(canResume('paused')).toBe(true);
    expect(canResume('pending')).toBe(false);
  });
});

describe('filterByKind', () => {
  const jobs = [
    makeJob({ id: 1, kind: 'crawl' }),
    makeJob({ id: 2, kind: 'analysis' }),
    makeJob({ id: 3, kind: 'probe' }),
  ];

  it('passes everything through for "all"', () => {
    expect(filterByKind(jobs, 'all')).toHaveLength(3);
  });

  it('keeps only the matching kind', () => {
    expect(filterByKind(jobs, 'analysis').map((j) => j.id)).toEqual([2]);
  });
});

describe('recency sort', () => {
  it('keys on finished → started → created, in that order', () => {
    expect(recencyKey(makeJob({ created_at: 'c', started_at: 's', finished_at: 'f' }))).toBe('f');
    expect(recencyKey(makeJob({ created_at: 'c', started_at: 's' }))).toBe('s');
    expect(recencyKey(makeJob({ created_at: 'c' }))).toBe('c');
    expect(recencyKey(makeJob())).toBe('');
  });

  it('orders newest-first and is stable against the input', () => {
    const input = [
      makeJob({ id: 1, created_at: '2026-06-04T10:00:00Z' }),
      makeJob({ id: 2, started_at: '2026-06-04T12:00:00Z' }),
      makeJob({ id: 3, finished_at: '2026-06-04T11:00:00Z' }),
    ];
    expect(sortJobsByRecency(input).map((j) => j.id)).toEqual([2, 3, 1]);
    expect(input.map((j) => j.id)).toEqual([1, 2, 3]); // not mutated
  });
});

describe('extractProgress', () => {
  it('reads an explicit {current,total}, result winning over payload', () => {
    expect(
      extractProgress(
        makeJob({ payload: { current: 1, total: 9 }, result: { current: 4, total: 5 } }),
      ),
    ).toEqual({ current: 4, total: 5 });
  });

  it('derives crawl progress from pages_crawled + pages_queued', () => {
    expect(
      extractProgress(makeJob({ payload: { pages_crawled: 7, pages_queued: 3 } })),
    ).toEqual({ current: 7, total: 10 });
  });

  it('returns undefined when no usable shape is present', () => {
    expect(extractProgress(makeJob())).toBeUndefined();
    expect(extractProgress(makeJob({ result: { total: 0, current: 0 } }))).toBeUndefined();
    expect(extractProgress(makeJob({ payload: { note: 'x' } }))).toBeUndefined();
  });
});

describe('toActivityRow', () => {
  it('projects a Job onto the ActivityRow shape', () => {
    const row = toActivityRow(
      makeJob({
        id: 42,
        kind: 'analysis',
        target_type: 'url',
        target_id: 7,
        status: 'failed',
        started_at: 's',
        finished_at: 'f',
        error: 'boom',
        result: { current: 2, total: 4 },
      }),
      'http://x.onion/',
    );
    expect(row).toEqual({
      id: 'job:42',
      kind: 'analysis',
      target: { type: 'url', label: 'http://x.onion/' },
      status: 'failed',
      startedAt: 's',
      finishedAt: 'f',
      progress: { current: 2, total: 4 },
      error: 'boom',
    });
  });

  it('omits optional fields when the job carries no values', () => {
    const row = toActivityRow(makeJob({ id: 1 }), 'url #100');
    expect(row.startedAt).toBeUndefined();
    expect(row.finishedAt).toBeUndefined();
    expect(row.progress).toBeUndefined();
    expect(row.error).toBeUndefined();
    expect(row.contentChanged).toBeUndefined();
  });

  it('flags contentChanged for a probe whose payload reports a change', () => {
    const row = toActivityRow(
      makeJob({ kind: 'probe', payload: { content_changed: true } }),
      'url #1',
    );
    expect(row.contentChanged).toBe(true);
  });
});

describe('probeContentChanged', () => {
  it('is true only for probe jobs with payload.content_changed === true', () => {
    expect(
      probeContentChanged(makeJob({ kind: 'probe', payload: { content_changed: true } })),
    ).toBe(true);
    expect(
      probeContentChanged(makeJob({ kind: 'probe', payload: { content_changed: false } })),
    ).toBe(false);
    expect(
      probeContentChanged(makeJob({ kind: 'probe', payload: { content_changed: null } })),
    ).toBe(false);
    // Not a probe, or no payload → false.
    expect(
      probeContentChanged(makeJob({ kind: 'crawl', payload: { content_changed: true } })),
    ).toBe(false);
    expect(probeContentChanged(makeJob({ kind: 'probe', payload: null }))).toBe(false);
  });
});

describe('groupJobs', () => {
  const label = (j: Job) => `${j.target_type} #${j.target_id}`;
  const jobs = [
    makeJob({ id: 1, status: 'done', target_id: 100 }),
    makeJob({ id: 2, status: 'running', target_id: 100 }),
    makeJob({ id: 3, status: 'done', target_id: 200 }),
  ];

  it('returns a single anonymous group for "none"', () => {
    const groups = groupJobs(jobs, 'none', label);
    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe('');
    expect(groups[0].jobs).toHaveLength(3);
    expect(groupJobs([], 'none', label)).toEqual([]);
  });

  it('groups by status in active-first order', () => {
    const groups = groupJobs(jobs, 'status', label);
    expect(groups.map((g) => g.key)).toEqual(['running', 'done']);
    expect(groups[1].jobs.map((j) => j.id)).toEqual([1, 3]);
  });

  it('groups by target, labelling from the first member', () => {
    const groups = groupJobs(jobs, 'target', label);
    expect(groups.map((g) => g.key)).toEqual(['url:100', 'url:200']);
    expect(groups[0].label).toBe('url #100');
    expect(groups[0].jobs.map((j) => j.id)).toEqual([1, 2]);
  });
});

describe('batch intake gating', () => {
  it('canRunBatch only for a pending batch job', () => {
    expect(canRunBatch(makeJob({ kind: 'batch', status: 'pending' }))).toBe(true);
    expect(canRunBatch(makeJob({ kind: 'batch', status: 'done' }))).toBe(false);
    expect(canRunBatch(makeJob({ kind: 'batch', status: 'running' }))).toBe(false);
    expect(canRunBatch(makeJob({ kind: 'crawl', status: 'pending' }))).toBe(false);
  });

  it('batchUrlCount reads payload.count, falls back to urls length', () => {
    expect(batchUrlCount(makeJob({ payload: { count: 5 } }))).toBe(5);
    expect(batchUrlCount(makeJob({ payload: { urls: ['a', 'b'] } }))).toBe(2);
    expect(batchUrlCount(makeJob({ payload: null }))).toBeNull();
    expect(batchUrlCount(makeJob({ payload: { other: 1 } }))).toBeNull();
  });
});

describe('canOpenTarget', () => {
  it('opens only a url target with a real resource id', () => {
    expect(canOpenTarget(makeJob({ target_type: 'url', target_id: 7 }))).toBe(true);
  });

  it('rejects placeholder/zero ids, non-url targets, and batches', () => {
    expect(canOpenTarget(makeJob({ target_type: 'url', target_id: 0 }))).toBe(false);
    expect(canOpenTarget(makeJob({ target_type: 'domain', target_id: 7 }))).toBe(false);
    expect(canOpenTarget(makeJob({ target_type: 'collection', target_id: 7 }))).toBe(false);
    expect(
      canOpenTarget(makeJob({ kind: 'batch', target_type: 'url', target_id: 7 })),
    ).toBe(false);
  });
});

describe('formatJobTime', () => {
  it('returns an em dash for missing or unparseable input', () => {
    expect(formatJobTime(null)).toBe('—');
    expect(formatJobTime(undefined)).toBe('—');
    expect(formatJobTime('not a date')).toBe('—');
  });

  it('formats a valid ISO timestamp to a time string', () => {
    expect(formatJobTime('2026-06-04T12:34:56Z')).toMatch(/\d/);
  });
});
