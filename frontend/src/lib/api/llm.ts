// LLM worker lifecycle + status. The worker drains the analysis queue; these
// routes only flip its state and read its snapshot (the loop owns Ollama I/O).
// Kept separate from analyses.ts (analysis CRUD) — worker lifecycle is a
// distinct concern shared by the Intel worker controls and the header.

import { apiFetch } from './core';
import type { LlmStatus } from './types';

export const getLlmStatus = () => apiFetch<LlmStatus>('/llm/status');

export const startLlm = () =>
  apiFetch<LlmStatus>('/llm/start', { method: 'POST' });

export const stopLlm = () =>
  apiFetch<LlmStatus>('/llm/stop', { method: 'POST' });

export const pauseLlm = () =>
  apiFetch<LlmStatus>('/llm/pause', { method: 'POST' });

export const resumeLlm = () =>
  apiFetch<LlmStatus>('/llm/resume', { method: 'POST' });
