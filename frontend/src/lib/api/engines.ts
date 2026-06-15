// Search-engine registry routes (Settings → Engines).
//
// CRUD over the project-scoped `search_engines` table. Per-engine enabled
// state is stored separately as the templated setting
// `search.engine.{id}.enabled`, so toggling an engine on/off goes through
// the settings round-trip rather than a column on the engine row.

import { apiFetch } from './core';
import { getSetting, putSetting } from './settings';
import type { EngineBody, SearchEngine } from './types';

export const listEngines = () =>
  apiFetch<{ engines: SearchEngine[] }>('/search-engines');

export const createEngine = (body: EngineBody) =>
  apiFetch<SearchEngine>('/search-engines', {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const updateEngine = (id: number, body: EngineBody) =>
  apiFetch<SearchEngine>(`/search-engines/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });

export const deleteEngine = (id: number) =>
  apiFetch<{ ok: true }>(`/search-engines/${id}`, { method: 'DELETE' });

// --- per-engine enabled flag (templated setting) -------------------------

const enabledKey = (id: number) => `search.engine.${id}.enabled`;

export const getEngineEnabled = (id: number) =>
  getSetting<string>(enabledKey(id));

export const setEngineEnabled = (id: number, enabled: boolean) =>
  putSetting(enabledKey(id), enabled);
