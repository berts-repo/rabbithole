import { describe, expect, it } from 'vitest';

import type { GraphPayload } from '$lib/api';
import { resolveFromPayload } from './nodeBag';

function payload(
  nodes: Array<Partial<GraphPayload['nodes'][number]> & { id: number }>,
): GraphPayload {
  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      label: n.label ?? `n${n.id}`,
      alias: null,
      title_text: '',
      raw_url: n.raw_url ?? `http://n${n.id}.onion/`,
      color: '#000',
      domain: n.domain ?? `n${n.id}.onion`,
      network: 'tor',
      depth: null,
      flag_status: null,
      is_bridge: false,
      betweenness: 0,
      pagerank: 0,
      cluster_id: null,
      infra_cluster_id: null,
      first_seen: null,
      is_cluster: false,
      state: n.state ?? 'crawled',
      analysis_excluded: false,
      reviewed: false,
      category: null,
      in_degree_count: 0,
      out_degree_count: 0,
      label_ids: [],
      domain_label_ids: [],
    })),
    edges: [],
  };
}

describe('resolveFromPayload', () => {
  it('resolves every id from the payload when all are present', () => {
    const p = payload([{ id: 1 }, { id: 2, state: 'known' }]);
    const { resolved, missing } = resolveFromPayload([1, 2], p);
    expect(missing).toEqual([]);
    expect(resolved.get(1)?.url).toBe('http://n1.onion/');
    expect(resolved.get(2)?.uncrawled).toBe(true);
  });

  it('reports unresolvable ids as missing', () => {
    const p = payload([{ id: 1 }]);
    const { resolved, missing } = resolveFromPayload([1, 7, 9], p);
    expect(resolved.size).toBe(1);
    expect(missing.sort()).toEqual([7, 9]);
  });

  it('treats a null payload as everything missing', () => {
    const { resolved, missing } = resolveFromPayload([3, 4], null);
    expect(resolved.size).toBe(0);
    expect(missing.sort()).toEqual([3, 4]);
  });
});
