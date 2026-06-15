// Cross-node entity queries. The cluster workspace Common tab uses this
// to surface entity values that appear on ≥ 2 of the selected crawled
// nodes — see backend/backend/db/entities.py::list_common.

import { apiFetch, qs } from './core';

export interface CommonEntity {
  type: string;
  value: string;
  // How many of the input crawled nodes share this entity.
  matches: number;
  // Denominator — how many of the input ids resolved to crawled nodes.
  total: number;
}

export const listCommonEntities = (nodeIds: readonly number[]) =>
  apiFetch<{ entities: CommonEntity[] }>(
    `/entities/common${qs({ node_ids: nodeIds.join(',') })}`,
  );
