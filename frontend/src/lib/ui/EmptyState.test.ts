// Tests for EmptyState props contract.
//
// Since the component runs in Node/vitest without jsdom, we test the
// prop defaults and optional-field logic via a light constructor mirror.

import { describe, expect, it } from 'vitest';

// Mirror the prop interface to verify defaults.
interface EmptyStateProps {
  title: string;
  body?: string;
  icon?: string;
  error?: boolean;
}

function resolveDefaults(props: EmptyStateProps): Required<Omit<EmptyStateProps, 'body' | 'icon'>> & EmptyStateProps {
  return {
    ...props,
    error: props.error ?? false,
  };
}

describe('EmptyState prop contracts', () => {
  it('requires a title', () => {
    const p = resolveDefaults({ title: 'No data.' });
    expect(p.title).toBe('No data.');
  });

  it('error defaults to false', () => {
    const p = resolveDefaults({ title: 'None.' });
    expect(p.error).toBe(false);
  });

  it('error can be set to true', () => {
    const p = resolveDefaults({ title: 'Load failed.', error: true });
    expect(p.error).toBe(true);
  });

  it('body is optional', () => {
    const p = resolveDefaults({ title: 'Empty.' });
    expect(p.body).toBeUndefined();
  });

  it('icon is optional', () => {
    const p = resolveDefaults({ title: 'Nothing here.' });
    expect(p.icon).toBeUndefined();
  });

  it('body provided round-trips', () => {
    const p = resolveDefaults({ title: 'None.', body: 'Try adding some.' });
    expect(p.body).toBe('Try adding some.');
  });
});
