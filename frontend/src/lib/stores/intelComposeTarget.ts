// Pure compose-target model for the Intel pane. Kept free of runes / DOM so
// it runs under the plain-node vitest config (the .svelte.ts store that wraps
// it is out of test scope, same split as lib/graph/interactions/*).

import type { GraphNode } from '$lib/api';

// A staged compose target pre-populates the Intel node compose form. Nodes are
// the only kind staged: collection and cluster analyses compose in their own
// sections (Collection Analysis, cluster Q&A), each writing to its own table.
// The `kind` discriminator is retained so a future funnel-all mode can extend
// this union without touching every construction site.
export type ComposeTarget = { kind: 'nodes'; nodeIds: number[]; label?: string };

/** Build a `nodes` compose target from raw node ids. */
export function targetFromIds(nodeIds: number[], label?: string): ComposeTarget {
  return { kind: 'nodes', nodeIds, label };
}

/** Build a `nodes` compose target from graph nodes. */
export function targetFromNodes(
  nodes: GraphNode[],
  label?: string,
): ComposeTarget {
  return targetFromIds(
    nodes.map((n) => n.id),
    label,
  );
}

/** How many distinct items the target queues against. */
export function targetCount(target: ComposeTarget): number {
  return target.nodeIds.length;
}
