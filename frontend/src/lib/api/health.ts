// Health + Tor status routes.

import { apiFetch } from './core';
import type { Health, TorStatus } from './types';

export const getHealth = () => apiFetch<Health>('/health');

export const getTorStatus = () => apiFetch<TorStatus>('/tor/status');

export const probeTor = () =>
  apiFetch<TorStatus>('/tor/probe', { method: 'POST' });
