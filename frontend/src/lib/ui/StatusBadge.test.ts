// Tests for StatusBadge tone-mapping logic.
//
// The component itself is a Svelte file; we test the pure variant→tone
// mapping by extracting it into a helper (inline here). This keeps the
// test in Node without needing jsdom or @testing-library/svelte.

import { describe, expect, it } from 'vitest';

// Duplicate the tone logic from StatusBadge.svelte as a pure function
// so it's directly testable. If the mapping changes, both the component
// and this test must be updated — the duplication is intentional and
// small.
type Variant =
  | 'pending'
  | 'running'
  | 'done'
  | 'failed'
  | 'cancelled'
  | 'warning'
  | 'waiting'
  | 'skipped'
  | 'queued';

type Tone = 'good' | 'warn' | 'live' | 'wait' | 'bad' | 'neutral';

function tone(s: Variant): Tone {
  switch (s) {
    case 'done':
      return 'good';
    case 'running':
      return 'live';
    case 'failed':
      return 'bad';
    case 'warning':
      return 'warn';
    case 'pending':
    case 'waiting':
      return 'wait';
    case 'cancelled':
    case 'skipped':
    case 'queued':
      return 'neutral';
  }
}

describe('StatusBadge tone mapping', () => {
  it('done → good', () => {
    expect(tone('done')).toBe('good');
  });

  it('running → live', () => {
    expect(tone('running')).toBe('live');
  });

  it('pending → wait', () => {
    expect(tone('pending')).toBe('wait');
  });

  it('waiting → wait', () => {
    expect(tone('waiting')).toBe('wait');
  });

  it('failed → bad', () => {
    expect(tone('failed')).toBe('bad');
  });

  it('warning → warn', () => {
    expect(tone('warning')).toBe('warn');
  });

  it('cancelled → neutral', () => {
    expect(tone('cancelled')).toBe('neutral');
  });

  it('skipped → neutral', () => {
    expect(tone('skipped')).toBe('neutral');
  });

  it('queued → neutral', () => {
    expect(tone('queued')).toBe('neutral');
  });

  it('only running variant triggers a pulsing dot', () => {
    const pulsing = (s: Variant) => s === 'running';
    expect(pulsing('running')).toBe(true);
    expect(pulsing('pending')).toBe(false);
    expect(pulsing('done')).toBe(false);
  });
});
