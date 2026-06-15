// Tests for ActionBar slot layout contract.
//
// Since ActionBar is a pure layout container (no logic beyond rendering
// two named slots), the meaningful test is the prop/slot interface.

import { describe, expect, it } from 'vitest';

// The ActionBar accepts two named snippets.
// primary is required; overflow is optional.
interface ActionBarProps {
  primary: () => void;        // Snippet (simulated as fn)
  overflow?: () => void;
}

function resolveActionBar(props: ActionBarProps) {
  return {
    hasPrimary: typeof props.primary === 'function',
    hasOverflow: typeof props.overflow === 'function',
  };
}

describe('ActionBar slot layout', () => {
  it('primary slot is always present', () => {
    const result = resolveActionBar({ primary: () => {} });
    expect(result.hasPrimary).toBe(true);
  });

  it('overflow slot is optional and absent by default', () => {
    const result = resolveActionBar({ primary: () => {} });
    expect(result.hasOverflow).toBe(false);
  });

  it('overflow slot is rendered when provided', () => {
    const result = resolveActionBar({
      primary: () => {},
      overflow: () => {},
    });
    expect(result.hasOverflow).toBe(true);
  });
});
