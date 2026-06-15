// Domain list, profile, pages, entities + alias rename. Backs both the
// bottom-pane Domains sub-tab (list) and the right-pane Domain tab
// (profile + pages + entities).

import { apiFetch, qs } from './core';
import type {
  DomainComparison,
  DomainEntity,
  DomainPage,
  DomainProfile,
  DomainRow,
} from './types';

export const listDomains = () =>
  apiFetch<{ domains: DomainRow[] }>('/domains');

export const getDomainProfile = (host: string) =>
  apiFetch<DomainProfile>(`/domains/${encodeURIComponent(host)}`);

export const listDomainPages = (host: string) =>
  apiFetch<{ pages: DomainPage[] }>(
    `/domains/${encodeURIComponent(host)}/pages`,
  );

export const listDomainEntities = (host: string) =>
  apiFetch<{ entities: DomainEntity[] }>(
    `/domains/${encodeURIComponent(host)}/entities`,
  );

export const listDomainSnapshots = (host: string) =>
  apiFetch<{ dates: string[] }>(
    `/domains/${encodeURIComponent(host)}/snapshots`,
  );

export const compareDomainSnapshots = (host: string, a: string, b: string) =>
  apiFetch<DomainComparison>(
    `/domains/${encodeURIComponent(host)}/compare${qs({ a, b })}`,
  );

export const patchDomainAlias = (host: string, alias: string | null) =>
  apiFetch<{ host: string; alias: string | null }>(
    `/domains/${encodeURIComponent(host)}`,
    { method: 'PATCH', body: JSON.stringify({ alias }) },
  );
