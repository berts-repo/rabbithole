// Shared error formatting helper.
//
// Moved from PageTab.svelte → $lib/api/errors.ts so every surface
// that needs a human-readable error string can import from one place.
// The action helpers in $lib/contextMenu/actions.ts already have their
// own explainApiError — this one is intentionally the same implementation
// so the migration can be incremental (callers swap to this as they
// are touched; we do not mass-replace on day 1).

import { ApiError } from './core';

export function explainError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return `${fallback}: ${err.message}`;
  if (err instanceof Error) return `${fallback}: ${err.message}`;
  return fallback;
}
