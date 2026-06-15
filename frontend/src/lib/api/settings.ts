// Key/value settings routes.

import { apiFetch } from './core';
import type { Setting } from './types';

export const getSetting = <T = unknown>(key: string) =>
  apiFetch<Setting<T>>(`/settings/${encodeURIComponent(key)}`);

export const putSetting = <T = unknown>(key: string, value: T) =>
  apiFetch<Setting<T>>(`/settings/${encodeURIComponent(key)}`, {
    method: 'PUT',
    body: JSON.stringify({ value }),
  });
