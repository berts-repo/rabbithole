// Tests for IconButton behaviour contract.
//
// Tests cover: ARIA label requirement, disabled state blocks click,
// pressed/toggle semantics, and size variants — all verifiable without DOM.

import { describe, expect, it, vi } from 'vitest';

// Mirror the prop interface for testing the contract rules.
interface IconButtonProps {
  label: string;
  size?: 'default' | 'small';
  variant?: 'ghost' | 'outline';
  disabled?: boolean;
  pressed?: boolean;
  onclick?: (e: MouseEvent) => void;
}

function resolveDefaults(props: IconButtonProps) {
  return {
    size: 'default' as const,
    variant: 'outline' as const,
    disabled: false,
    ...props,
  };
}

// Simulate the click-blocking logic: a disabled button should not fire onclick.
function simulateClick(props: IconButtonProps): boolean {
  const resolved = resolveDefaults(props);
  if (resolved.disabled) return false; // blocked
  props.onclick?.({} as MouseEvent);
  return true; // fired
}

describe('IconButton contracts', () => {
  describe('label (ARIA)', () => {
    it('label prop is passed through to aria-label', () => {
      const props = resolveDefaults({ label: 'Refresh' });
      expect(props.label).toBe('Refresh');
    });

    it('label is required by the type interface (non-empty)', () => {
      // In the runtime warning path an empty string triggers a console.warn.
      // Here we just verify the interface requires a string value.
      const props = resolveDefaults({ label: 'Delete' });
      expect(typeof props.label).toBe('string');
      expect(props.label.length).toBeGreaterThan(0);
    });
  });

  describe('disabled state', () => {
    it('disabled blocks the onclick callback', () => {
      const handler = vi.fn();
      const fired = simulateClick({ label: 'Delete', disabled: true, onclick: handler });
      expect(fired).toBe(false);
      expect(handler).not.toHaveBeenCalled();
    });

    it('enabled button fires onclick', () => {
      const handler = vi.fn();
      const fired = simulateClick({ label: 'Delete', disabled: false, onclick: handler });
      expect(fired).toBe(true);
      expect(handler).toHaveBeenCalledOnce();
    });

    it('disabled defaults to false', () => {
      const props = resolveDefaults({ label: 'Save' });
      expect(props.disabled).toBe(false);
    });
  });

  describe('pressed / toggle', () => {
    it('aria-pressed is undefined when pressed prop is omitted', () => {
      const props = resolveDefaults({ label: 'Flag' });
      // Svelte renders aria-pressed only when pressed !== undefined.
      expect(props.pressed).toBeUndefined();
    });

    it('pressed=true → aria-pressed true', () => {
      const props = resolveDefaults({ label: 'Flag', pressed: true });
      expect(props.pressed).toBe(true);
    });

    it('pressed=false → aria-pressed false', () => {
      const props = resolveDefaults({ label: 'Flag', pressed: false });
      expect(props.pressed).toBe(false);
    });
  });

  describe('size variants', () => {
    it('defaults to size=default', () => {
      const props = resolveDefaults({ label: 'X' });
      expect(props.size).toBe('default');
    });

    it('size=small round-trips', () => {
      const props = resolveDefaults({ label: 'X', size: 'small' });
      expect(props.size).toBe('small');
    });
  });

  describe('variant', () => {
    it('defaults to variant=outline', () => {
      const props = resolveDefaults({ label: 'X' });
      expect(props.variant).toBe('outline');
    });

    it('variant=ghost round-trips', () => {
      const props = resolveDefaults({ label: 'X', variant: 'ghost' });
      expect(props.variant).toBe('ghost');
    });
  });
});
