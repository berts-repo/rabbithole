// Investigation flag list + per-flag patch — backs the Flags sub-tab
// and the right panel Page tab's flag editor.
//
// The per-node mutations (createFlag, clearNodeFlags) live in nodes.ts
// because the right-click menu has carried them since F4.

import { apiFetch } from './core';
import type { FlagListRow, FlagRow, UpdateFlagBody } from './types';

export const listFlags = () =>
  apiFetch<{ flags: FlagListRow[] }>('/flags');

export const patchFlag = (id: number, body: UpdateFlagBody) =>
  apiFetch<FlagRow>(`/flags/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
