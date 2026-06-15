// Pure compose-target derivation — the rune/DOM-free core the Intel compose
// form and the queueAnalysis funnel both build on. The .svelte.ts store and
// the components are out of vitest scope (plain-node config); this locks the
// logic they depend on.

import { describe, expect, it } from 'vitest';
import type { GraphNode } from '$lib/api';
import {
  targetCount,
  targetFromNodes,
  type ComposeTarget,
} from './intelComposeTarget';

function node(id: number): GraphNode {
  // Only `id` matters to the target model; cast keeps the fixture minimal.
  return { id } as GraphNode;
}

describe('targetFromNodes', () => {
  it('extracts ids in order and carries the label', () => {
    const t = targetFromNodes([node(3), node(1), node(2)], 'Graph selection');
    expect(t).toEqual({
      kind: 'nodes',
      nodeIds: [3, 1, 2],
      label: 'Graph selection',
    });
  });

  it('handles an empty selection', () => {
    expect(targetFromNodes([])).toEqual({
      kind: 'nodes',
      nodeIds: [],
      label: undefined,
    });
  });
});

describe('targetCount', () => {
  it('counts node targets', () => {
    expect(targetCount({ kind: 'nodes', nodeIds: [1, 2, 3] })).toBe(3);
  });

  it('is zero for an empty node selection (drives the disabled Queue button)', () => {
    const empty: ComposeTarget = { kind: 'nodes', nodeIds: [] };
    expect(targetCount(empty)).toBe(0);
  });
});
