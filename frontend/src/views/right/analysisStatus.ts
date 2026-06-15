// Pure helpers for the right pane Analysis tab — status badge mapping
// and result-pane placeholder selection. Kept separate from the .svelte
// component so the policy is unit-testable without mounting the view.

import type { AnalysisRow, AnalysisStatus } from '$lib/api';

export type StatusTone = 'good' | 'warn' | 'live' | 'wait' | 'bad';

export interface StatusBadge {
  label: string;
  tone: StatusTone;
  // Reserved for status-specific tooltips; empty so the template can bind
  // unconditionally.
  tooltip: string;
}

export function statusBadge(status: AnalysisStatus): StatusBadge {
  switch (status) {
    case 'done':
      return { label: 'done', tone: 'good', tooltip: '' };
    case 'pending':
      return { label: 'pending', tone: 'warn', tooltip: '' };
    case 'running':
      return { label: 'running', tone: 'live', tooltip: '' };
    case 'paused':
      return { label: 'paused', tone: 'wait', tooltip: '' };
    case 'failed':
      return { label: 'failed', tone: 'bad', tooltip: '' };
    case 'cancelled':
      return { label: 'cancelled', tone: 'bad', tooltip: '' };
  }
}

// What to show in the result pane body when there's no full result text
// to render. The component still owns layout — this just picks the line.
export type ResultPlaceholder =
  | { kind: 'show'; body: string }
  | { kind: 'message'; text: string };

export function resultPlaceholder(
  row: AnalysisRow | null,
): ResultPlaceholder | null {
  if (row === null) return null;
  switch (row.status) {
    case 'pending':
      return { kind: 'message', text: 'In queue…' };
    case 'running':
      return { kind: 'message', text: 'Running…' };
    case 'paused':
      return { kind: 'message', text: 'Paused.' };
    case 'failed':
      return { kind: 'message', text: 'Failed.' };
    case 'cancelled':
      return { kind: 'message', text: 'Cancelled.' };
    case 'done':
      if (row.result && row.result.length > 0) {
        return { kind: 'show', body: row.result };
      }
      return { kind: 'message', text: 'No result yet.' };
    default:
      // Null status (no linked job row) — nothing to render.
      return null;
  }
}

// True if any row is in a non-terminal state — used to decide whether
// the polling timer should still be ticking.
export function shouldPoll(rows: AnalysisRow[]): boolean {
  return rows.some((r) => r.status === 'pending' || r.status === 'running');
}
