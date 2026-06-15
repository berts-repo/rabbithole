// Per-node notes — list/add live under /api/nodes/:id/notes; delete is
// note-scoped so the caller only needs the note id. Backs the right
// panel Page tab's notes section.

import { apiFetch } from './core';
import type { NoteRow } from './types';

export const listNodeNotes = (nodeId: number) =>
  apiFetch<{ notes: NoteRow[] }>(`/nodes/${nodeId}/notes`);

export const addNodeNote = (nodeId: number, body: string) =>
  apiFetch<NoteRow>(`/nodes/${nodeId}/notes`, {
    method: 'POST',
    body: JSON.stringify({ body }),
  });

export const deleteNote = (noteId: number) =>
  apiFetch<{ ok: true }>(`/notes/${noteId}`, { method: 'DELETE' });
