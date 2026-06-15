// Prompt-template CRUD (item 7, D3). Project-local named analyzer prompts.
// Built-in presets are hideable but not editable/deletable; the routes enforce
// that (409 on edit/delete of a builtin).

import { apiFetch } from './core';
import type {
  CreatePromptTemplateBody,
  PromptTemplate,
  UpdatePromptTemplateBody,
} from './types';

export const listPromptTemplates = (includeHidden = false) =>
  apiFetch<{ prompts: PromptTemplate[] }>(
    `/prompts${includeHidden ? '?include_hidden=true' : ''}`,
  );

export const getPromptTemplate = (id: number) =>
  apiFetch<PromptTemplate>(`/prompts/${id}`);

export const createPromptTemplate = (body: CreatePromptTemplateBody) =>
  apiFetch<{ id: number }>('/prompts', {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const updatePromptTemplate = (
  id: number,
  body: UpdatePromptTemplateBody,
) =>
  apiFetch<PromptTemplate>(`/prompts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });

export const deletePromptTemplate = (id: number) =>
  apiFetch<{ deleted: number }>(`/prompts/${id}`, { method: 'DELETE' });
