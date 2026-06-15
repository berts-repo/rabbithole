// Pure data + helpers for the bottom-pane's customizable single-row tab
// strip. The analyst picks which tabs sit on the strip; everything not on
// it is reachable from the "+" customise menu. Kept in a plain `.ts` so
// vitest can run against the helpers without the Svelte runtime — the
// workspace store re-exports the public names from here.

export type BottomTab =
  | 'collection'
  | 'bookmarks'
  | 'live_crawl'
  | 'activity'
  | 'scheduled_crawls'
  | 'monitors'
  | 'inventory'
  | 'domains'
  | 'flags'
  | 'fingerprints'
  | 'labels'
  | 'analyzed'
  | 'find';

export interface BottomTabDef {
  id: BottomTab;
  label: string;
}

// Every available bottom-pane tab, in canonical display order. The strip
// and the "+" customise menu both render from this; the analyst's chosen
// subset is filtered out of it so tabs always show in this order
// regardless of the order they were added.
export const BOTTOM_TABS: BottomTabDef[] = [
  { id: 'live_crawl', label: 'Live Crawl' },
  { id: 'activity', label: 'Activity' },
  { id: 'scheduled_crawls', label: 'Scheduled Crawls' },
  { id: 'monitors', label: 'Monitors' },
  { id: 'inventory', label: 'Inventory' },
  { id: 'domains', label: 'Domains' },
  { id: 'flags', label: 'Flags' },
  { id: 'fingerprints', label: 'Fingerprints' },
  { id: 'labels', label: 'Labels' },
  { id: 'analyzed', label: 'Analyzed' },
  { id: 'collection', label: 'Collection' },
  { id: 'bookmarks', label: 'Bookmarks' },
  // Find results — the lookup surface's result list. Not in the default strip;
  // running a Find auto-reveals it via workspaceStore.setBottom.
  { id: 'find', label: 'Find' },
];

// The strip an analyst sees before they've customised anything — a compact
// cross-section (live crawl is also the default active tab) rather than all
// ten, so the strip starts uncluttered. The rest are one "+" click away.
export const DEFAULT_VISIBLE_TABS: BottomTab[] = [
  'live_crawl',
  'activity',
  'inventory',
  'collection',
];

const ORDER: BottomTab[] = BOTTOM_TABS.map((t) => t.id);
const BY_ID = new Map<BottomTab, BottomTabDef>(BOTTOM_TABS.map((t) => [t.id, t]));

export function isBottomTab(v: unknown): v is BottomTab {
  return typeof v === 'string' && BY_ID.has(v as BottomTab);
}

export function tabDef(id: BottomTab): BottomTabDef {
  // Safe: callers only pass ids that came from BOTTOM_TABS / isBottomTab.
  return BY_ID.get(id)!;
}

// Sort an arbitrary set of tab ids into canonical display order, dropping
// unknowns and de-duping. The single source of truth for strip order — the
// strip is always a canonical-ordered subset of BOTTOM_TABS.
export function orderTabs(tabs: BottomTab[]): BottomTab[] {
  const set = new Set(tabs);
  return ORDER.filter((id) => set.has(id));
}

// Sanitize a persisted/incoming visible set: canonical order, de-duped, and
// never empty — an empty input falls back to the default strip so the pane
// can't render with zero tabs.
export function normalizeVisible(tabs: BottomTab[]): BottomTab[] {
  const ordered = orderTabs(tabs);
  return ordered.length > 0 ? ordered : [...DEFAULT_VISIBLE_TABS];
}

// The tab to make active after `removed` leaves the strip: the neighbour to
// its right in canonical order, else the one to its left. Returns null when
// removal isn't allowed — `removed` isn't on the strip, or it's the last
// remaining tab (the strip must never go empty).
export function neighborAfterRemoval(
  visible: BottomTab[],
  removed: BottomTab,
): BottomTab | null {
  const idx = visible.indexOf(removed);
  if (idx === -1 || visible.length <= 1) return null;
  return visible[idx + 1] ?? visible[idx - 1];
}

// Encode/decode the visible strip for the key/value settings store. The
// backend persists scalars as plain strings (`str(value)`), so a CSV string
// round-trips cleanly where a JSON array would not. Decoding is lenient:
// unknown/blank entries are dropped, and a usable result is normalised.
export function encodeVisible(tabs: BottomTab[]): string {
  return tabs.join(',');
}

export function decodeVisible(raw: unknown): BottomTab[] | null {
  if (typeof raw !== 'string') return null;
  const tabs = raw
    .split(',')
    .map((s) => s.trim())
    .filter(isBottomTab);
  return tabs.length > 0 ? normalizeVisible(tabs) : null;
}
