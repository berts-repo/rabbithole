// Embedding worker — Intel exposes pause/resume + status/progress only.
// Lifecycle (start/stop) lives in Settings → Embedding (spec line 344): the
// embed worker auto-starts with the backend, so day-to-day throttling here is
// pause/resume, not full stop.

import { apiFetch } from './core';
import type { EmbedModel, EmbedProgress, EmbedStatus } from './types';

export const getEmbedStatus = () => apiFetch<EmbedStatus>('/embed/status');

// Settings → Embedding model picker + recompute. `start` re-arms the worker
// over the existing corpus (it auto-starts with the backend, but a model
// change or a manual recompute kicks it explicitly).
export const listEmbedModels = () =>
  apiFetch<{ models: EmbedModel[] }>('/embed/models');

export const startEmbed = () =>
  apiFetch<EmbedStatus>('/embed/start', { method: 'POST' });

export const getEmbedProgress = () =>
  apiFetch<EmbedProgress>('/embed/progress');

export const pauseEmbed = () =>
  apiFetch<EmbedStatus>('/embed/pause', { method: 'POST' });

export const resumeEmbed = () =>
  apiFetch<EmbedStatus>('/embed/resume', { method: 'POST' });
