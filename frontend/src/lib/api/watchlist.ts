// Watchlist term routes.

import { apiFetch } from './core';
import type { WatchlistTerm, AddWatchlistTermBody } from './types';

export const listWatchlist = () => apiFetch<{ terms: WatchlistTerm[] }>('/watchlist');

export const addWatchlistTerm = (body: AddWatchlistTermBody) =>
  apiFetch<WatchlistTerm>('/watchlist', { method: 'POST', body: JSON.stringify(body) });

export const updateWatchlistTerm = (id: number, body: AddWatchlistTermBody) =>
  apiFetch<WatchlistTerm>(`/watchlist/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });

export const deleteWatchlistTerm = (id: number) =>
  apiFetch<{ ok: true }>(`/watchlist/${id}`, { method: 'DELETE' });
