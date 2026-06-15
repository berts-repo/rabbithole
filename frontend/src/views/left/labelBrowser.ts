// Pure helpers for the left-pane label browser (item 11, Phase 3b). The
// browser lists labels with a per-label count of how many nodes in the CURRENT
// graph workspace carry that label, and highlights those nodes on click.
// Membership unions the directly-attached labels and those inherited via the
// node's domain — the same union the chips and color mode read. Kept store-free
// so vitest covers the set math directly; the component owns the payload read
// and the selection wiring.

import type { GraphNode } from '$lib/api';

// One pass over the payload's nodes maps each label id present to the set of
// node ids carrying it (direct ∪ via-domain), so the browser counts and
// highlights without rescanning per label. A node listing the same id in both
// arrays is harmless — the Set dedupes it.
export function labelMemberNodeIds(
  nodes: readonly GraphNode[],
): Map<number, Set<number>> {
  const out = new Map<number, Set<number>>();
  for (const n of nodes) {
    for (const id of n.label_ids) add(out, id, n.id);
    for (const id of n.domain_label_ids) add(out, id, n.id);
  }
  return out;
}

function add(
  map: Map<number, Set<number>>,
  labelId: number,
  nodeId: number,
): void {
  const set = map.get(labelId);
  if (set) set.add(nodeId);
  else map.set(labelId, new Set([nodeId]));
}

// Two id sets hold the same members. Marks a label row "active" when the
// current highlight selection is exactly that label's in-graph member set, so
// the browser reflects a highlight it owns and a second click can clear it.
export function sameIdSet(
  a: ReadonlySet<number>,
  b: ReadonlySet<number>,
): boolean {
  if (a.size !== b.size) return false;
  for (const id of a) if (!b.has(id)) return false;
  return true;
}
