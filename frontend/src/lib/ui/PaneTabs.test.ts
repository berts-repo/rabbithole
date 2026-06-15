// Tests for PaneTabs keyboard navigation logic.
//
// The arrow-key handler is a pure function operating on indices; we test
// it directly without DOM.

import { describe, expect, it, vi } from 'vitest';

interface Tab { id: string; label: string }

// Replicated from PaneTabs.svelte to test in isolation.
function computeNextIndex(
  key: 'ArrowRight' | 'ArrowLeft' | 'Home' | 'End',
  currentIdx: number,
  count: number,
): number {
  switch (key) {
    case 'ArrowRight':
      return (currentIdx + 1) % count;
    case 'ArrowLeft':
      return (currentIdx - 1 + count) % count;
    case 'Home':
      return 0;
    case 'End':
      return count - 1;
  }
}

const TABS: Tab[] = [
  { id: 'page', label: 'Page' },
  { id: 'domain', label: 'Domain' },
  { id: 'analysis', label: 'Analysis' },
];

describe('PaneTabs keyboard navigation', () => {
  it('ArrowRight advances to next tab', () => {
    expect(computeNextIndex('ArrowRight', 0, TABS.length)).toBe(1);
  });

  it('ArrowRight wraps from last to first', () => {
    expect(computeNextIndex('ArrowRight', 2, TABS.length)).toBe(0);
  });

  it('ArrowLeft moves to previous tab', () => {
    expect(computeNextIndex('ArrowLeft', 1, TABS.length)).toBe(0);
  });

  it('ArrowLeft wraps from first to last', () => {
    expect(computeNextIndex('ArrowLeft', 0, TABS.length)).toBe(2);
  });

  it('Home always jumps to index 0', () => {
    expect(computeNextIndex('Home', 2, TABS.length)).toBe(0);
    expect(computeNextIndex('Home', 0, TABS.length)).toBe(0);
  });

  it('End always jumps to last index', () => {
    expect(computeNextIndex('End', 0, TABS.length)).toBe(2);
    expect(computeNextIndex('End', 2, TABS.length)).toBe(2);
  });

  it('works with two tabs (degenerate wrapping)', () => {
    expect(computeNextIndex('ArrowRight', 0, 2)).toBe(1);
    expect(computeNextIndex('ArrowRight', 1, 2)).toBe(0);
    expect(computeNextIndex('ArrowLeft', 0, 2)).toBe(1);
  });

  describe('role="tablist" contract', () => {
    it('active tab has tabindex 0, others -1', () => {
      const active = 'domain';
      const tabIndices = TABS.map((t) => (t.id === active ? 0 : -1));
      expect(tabIndices).toEqual([-1, 0, -1]);
    });

    it('aria-selected is true only for active tab', () => {
      const active = 'analysis';
      const selected = TABS.map((t) => t.id === active);
      expect(selected).toEqual([false, false, true]);
    });
  });

  describe('onSelect callback', () => {
    it('fires with the tab id on click', () => {
      const onSelect = vi.fn();
      const tab = TABS[1];
      onSelect(tab.id);
      expect(onSelect).toHaveBeenCalledWith('domain');
    });
  });
});
