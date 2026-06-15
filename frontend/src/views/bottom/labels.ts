// Pure helpers for LabelsTab (item 11, Phase 3a) — display-name resolution.
// Kept store-free so vitest covers them directly; the component owns the fetch
// + selection wiring. The drag-reorder array move lives in the shared
// `$lib/labels/order` (the Settings Labels tab reorders the same list).

import type { LabelDomainMember, LabelResourceMember } from '$lib/api';

// A labeled resource's row name: the analyst's page alias wins (it's the
// rename), then the crawled title, then the bare url as the always-present
// fallback. Mirrors how chips elsewhere prefer the alias.
export function memberDisplayName(r: LabelResourceMember): string {
  return r.alias?.trim() || r.title?.trim() || r.url;
}

// A labeled domain's row name: its alias (rename) when set, else the host.
export function domainDisplayName(d: LabelDomainMember): string {
  return d.alias?.trim() || d.host;
}

// The workspace-tab label for "all resources labeled X".
export function labelTabLabel(name: string): string {
  return `Label: ${name}`;
}
