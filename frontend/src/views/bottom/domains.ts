// Pure helpers for DomainsTab — substring filter over host + alias.
//
// The backend already sorts list_domains() by page_count DESC, host —
// no client-side sort here. Filter is case-insensitive and matches if
// the query appears in either the alias (when set) or the host.

import type { DomainRow } from '$lib/api';

export function filterDomains(
  rows: DomainRow[],
  query: string,
): DomainRow[] {
  const q = query.trim().toLowerCase();
  if (!q) return rows;
  return rows.filter((r) => {
    if (r.host.toLowerCase().includes(q)) return true;
    if (r.alias && r.alias.toLowerCase().includes(q)) return true;
    return false;
  });
}

// Alias if set, otherwise the raw host. The bottom-pane row content
// surfaces this in the label slot.
export function displayName(r: DomainRow): string {
  return r.alias && r.alias.trim() ? r.alias : r.host;
}
