// Resolve a set of selected node ids into a {url, uncrawled} bag for the
// cluster workspace. Prefers the live graph payload (zero-cost) and
// falls back to per-id `getNode` for ids that aren't currently rendered
// (filtered, hidden, in another workspace). Results are cached on the
// returned object so re-resolving the same set across renders is free.

import { getNode, type GraphPayload } from '$lib/api';
import { isUncrawled } from '$lib/nodeState';

export interface NodeBagEntry {
  id: number;
  url: string;
  uncrawled: boolean;
  domain: string | null;
}

export type NodeBag = Map<number, NodeBagEntry>;

// Pure helper — given a payload and a set of ids, returns the entries
// resolvable from the payload alone. Anything missing is reported in
// the returned `missing` array. Caller hands `missing` to
// `fetchMissingNodes` to fill them.
export function resolveFromPayload(
  ids: Iterable<number>,
  payload: GraphPayload | null,
): { resolved: NodeBag; missing: number[] } {
  const resolved: NodeBag = new Map();
  const missing: number[] = [];
  const byId = new Map<number, GraphPayload['nodes'][number]>();
  for (const n of payload?.nodes ?? []) byId.set(n.id, n);
  for (const id of ids) {
    const hit = byId.get(id);
    if (hit) {
      resolved.set(id, {
        id,
        url: hit.raw_url,
        uncrawled: isUncrawled(hit),
        domain: hit.domain,
      });
    } else {
      missing.push(id);
    }
  }
  return { resolved, missing };
}

// Fetch every missing id in parallel and merge into the bag. Errors per
// id are swallowed — a missing entry just means the row renders with a
// placeholder URL, which is preferable to blanking the whole list.
export async function fetchMissingNodes(
  ids: readonly number[],
): Promise<NodeBag> {
  const merged: NodeBag = new Map();
  await Promise.all(
    ids.map(async (id) => {
      try {
        const n = await getNode(id);
        merged.set(id, {
          id,
          url: n.url,
          uncrawled: isUncrawled(n),
          domain: n.domain,
        });
      } catch {
        // Leave unresolved — the cluster Nodes tab shows the bare id in
        // that case so the row stays interactable (✕ removes by id).
      }
    }),
  );
  return merged;
}
