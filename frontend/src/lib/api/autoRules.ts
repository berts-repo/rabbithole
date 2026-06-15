// Auto-analysis rule CRUD (item 7, D4). The single typed home for
// auto-analysis: 'crawl' rules fire on every newly crawled page, 'collection_add'
// rules fire when a page joins a collection. Managed from the Intel pane.

import { apiFetch, qs } from './core';
import type {
  AutoRule,
  AutoRuleTrigger,
  CreateAutoRuleBody,
  UpdateAutoRuleBody,
} from './types';

export const listAutoRules = (triggerKind?: AutoRuleTrigger) =>
  apiFetch<{ rules: AutoRule[] }>(
    `/auto-analysis-rules${qs({ trigger_kind: triggerKind ?? undefined })}`,
  );

export const createAutoRule = (body: CreateAutoRuleBody) =>
  apiFetch<{ id: number }>('/auto-analysis-rules', {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const updateAutoRule = (id: number, body: UpdateAutoRuleBody) =>
  apiFetch<AutoRule>(`/auto-analysis-rules/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });

export const deleteAutoRule = (id: number) =>
  apiFetch<{ deleted: number }>(`/auto-analysis-rules/${id}`, {
    method: 'DELETE',
  });
