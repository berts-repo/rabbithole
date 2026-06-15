// Project lifecycle routes plus the active project's stat counts.

import { apiFetch, qs } from './core';
import type { Project, ProjectList, Stats, CreateProjectBody } from './types';

// ---------------- Projects ----------------

export const listProjects = () => apiFetch<ProjectList>('/projects');

export const createProject = (body: CreateProjectBody) =>
  apiFetch<Project>('/projects', { method: 'POST', body: JSON.stringify(body) });

export const switchProject = (id: string, force = false) =>
  apiFetch<{ ok: true; active_id: string }>(
    `/project/switch${qs({ force: force ? true : undefined })}`,
    { method: 'POST', body: JSON.stringify({ id }) },
  );

export const deleteProject = (id: string) =>
  apiFetch<{ ok: true }>(`/projects/${encodeURIComponent(id)}`, { method: 'DELETE' });

// ---------------- Stats ----------------

export const getStats = () => apiFetch<Stats>('/stats');
