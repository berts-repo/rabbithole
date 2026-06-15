// Uptime monitor routes. Backs the right pane Domain tab's monitors
// section — optional `host` filter on list scopes to one .onion.

import { apiFetch, qs } from './core';
import type { CreateMonitorBody, Monitor, UpdateMonitorBody } from './types';

export const listMonitors = (host?: string | null) =>
  apiFetch<{ monitors: Monitor[] }>(`/monitors${qs({ host: host ?? null })}`);

export const createMonitor = (body: CreateMonitorBody) =>
  apiFetch<Monitor>('/monitors', {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const patchMonitor = (id: number, body: UpdateMonitorBody) =>
  apiFetch<Monitor>(`/monitors/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });

export const deleteMonitor = (id: number) =>
  apiFetch<{ ok: true }>(`/monitors/${id}`, { method: 'DELETE' });
