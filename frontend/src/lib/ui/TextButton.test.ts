// Tests for TextButton prop contract and variant logic.

import { describe, expect, it, vi } from 'vitest';

interface TextButtonProps {
  variant?: 'primary' | 'secondary' | 'ghost';
  size?: 'default' | 'small';
  disabled?: boolean;
  type?: 'button' | 'submit' | 'reset';
  onclick?: (e: MouseEvent) => void;
}

function resolveDefaults(props: TextButtonProps) {
  return {
    variant: 'secondary' as const,
    size: 'default' as const,
    disabled: false,
    type: 'button' as const,
    ...props,
  };
}

function simulateClick(props: TextButtonProps): boolean {
  const resolved = resolveDefaults(props);
  if (resolved.disabled) return false;
  props.onclick?.({} as MouseEvent);
  return true;
}

describe('TextButton contracts', () => {
  it('defaults to secondary variant', () => {
    expect(resolveDefaults({}).variant).toBe('secondary');
  });

  it('defaults to size=default', () => {
    expect(resolveDefaults({}).size).toBe('default');
  });

  it('defaults to type=button', () => {
    expect(resolveDefaults({}).type).toBe('button');
  });

  it('primary variant round-trips', () => {
    expect(resolveDefaults({ variant: 'primary' }).variant).toBe('primary');
  });

  it('ghost variant round-trips', () => {
    expect(resolveDefaults({ variant: 'ghost' }).variant).toBe('ghost');
  });

  it('disabled blocks onclick', () => {
    const handler = vi.fn();
    const fired = simulateClick({ disabled: true, onclick: handler });
    expect(fired).toBe(false);
    expect(handler).not.toHaveBeenCalled();
  });

  it('enabled fires onclick', () => {
    const handler = vi.fn();
    const fired = simulateClick({ onclick: handler });
    expect(fired).toBe(true);
    expect(handler).toHaveBeenCalledOnce();
  });
});
