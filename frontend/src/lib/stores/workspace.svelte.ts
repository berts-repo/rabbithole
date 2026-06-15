// Center tab (Search / Explore), bottom-pane active sub-tab, and which
// graph workspace tab is in focus. The 'global' workspace id is the
// default tab — collection workspaces use the collection's id (as a
// string) for `activeWorkspaceId` so the model is uniformly stringy.

import { listCollections, getSetting, putSetting, type Collection } from '$lib/api';
import { toastStore } from '$lib/stores/toast.svelte';
import { nodeSetSignature, type NodeSetSource } from '$lib/graph/nodeSetScope';
import {
  BOTTOM_TABS,
  DEFAULT_VISIBLE_TABS,
  decodeVisible,
  encodeVisible,
  isBottomTab,
  neighborAfterRemoval,
  orderTabs,
  tabDef,
  type BottomTab,
  type BottomTabDef,
} from './bottomTabs';

export type CenterTab = 'search' | 'explore';

export { BOTTOM_TABS, isBottomTab };
export type { BottomTab, BottomTabDef };
export type { NodeSetSource };

export type WorkspaceKind = 'global' | 'collection' | 'nodeset';

export interface OpenTab {
  id: string;
  kind: WorkspaceKind;
  collectionId: number | null;
  label: string;
  // Set only when kind === 'nodeset'; the source the visibilityController
  // builds its scope predicate from.
  source: NodeSetSource | null;
}

const GLOBAL_TAB: OpenTab = {
  id: 'global',
  kind: 'global',
  collectionId: null,
  label: 'Global',
  source: null,
};

function tabId(collectionId: number): string {
  return String(collectionId);
}

// NodeSet tab id — derived from the source signature so reopening the same
// source focuses (and refreshes) its existing tab instead of duplicating it.
function nodeSetTabId(source: NodeSetSource): string {
  return `ns:${nodeSetSignature(source)}`;
}

interface WorkspaceState {
  centerTab: CenterTab;
  bottomTab: BottomTab;
  // The analyst's customised tab strip — canonical-ordered, de-duped,
  // non-empty, and always containing `bottomTab` (the active tab is forced
  // onto the strip so it's never selected-but-hidden).
  visibleBottomTabs: BottomTab[];
  activeWorkspaceId: string;
  openTabs: OpenTab[];
}

const state = $state<WorkspaceState>({
  centerTab: 'explore',
  bottomTab: 'live_crawl',
  visibleBottomTabs: [...DEFAULT_VISIBLE_TABS],
  activeWorkspaceId: 'global',
  openTabs: [GLOBAL_TAB],
});

async function persistBottomTab(tab: BottomTab): Promise<void> {
  try {
    await putSetting('workspace.bottomTab', tab);
  } catch {
    // Fire-and-forget — last-tab persistence is a convenience, not state
    // we surface failures for.
  }
}

async function persistVisibleTabs(tabs: BottomTab[]): Promise<void> {
  try {
    // Stored as a CSV scalar — the settings store persists values via
    // `str()`, so a JSON array wouldn't round-trip; a CSV string does.
    await putSetting('workspace.bottomTabs', encodeVisible(tabs));
  } catch {
    // Fire-and-forget — strip customisation is a convenience, not state
    // we surface failures for.
  }
}

// Persisted tab shapes. Collection tabs store their id; nodeset tabs store the
// full source (derived sources re-derive on reload, captured sources restore
// their literal members) plus the label so a renamed tab survives a reload.
type StoredTab =
  | { kind: 'collection'; collection_id: number }
  | { kind: 'nodeset'; source: NodeSetSource; label: string };

async function persistWorkspace(s: WorkspaceState): Promise<void> {
  const storedTabs: StoredTab[] = [];
  for (const t of s.openTabs) {
    if (t.kind === 'collection' && t.collectionId !== null) {
      storedTabs.push({ kind: 'collection', collection_id: t.collectionId });
    } else if (t.kind === 'nodeset' && t.source) {
      storedTabs.push({ kind: 'nodeset', source: t.source, label: t.label });
    }
  }
  try {
    await Promise.all([
      putSetting('workspace.tabs', storedTabs),
      putSetting('workspace.active', s.activeWorkspaceId),
    ]);
  } catch {
    // Fire-and-forget — don't surface settings-write failures here.
  }
}

// Reconstruct a nodeset OpenTab from its persisted shape. Light validation —
// a malformed stored entry is skipped rather than throwing.
function restoreNodeSetTab(item: { source?: unknown; label?: unknown }): OpenTab | null {
  const source = item.source as NodeSetSource | undefined;
  if (!source || typeof source !== 'object' || typeof (source as NodeSetSource).kind !== 'string') {
    return null;
  }
  const id = nodeSetTabId(source);
  const label = typeof item.label === 'string' && item.label.trim() ? item.label : id;
  return { id, kind: 'nodeset', collectionId: null, label, source };
}

export const workspaceStore = {
  /**
   * Restore persisted open tabs from settings. Reconciles against the
   * current collection list — drops tabs whose collection no longer exists.
   * Falls back gracefully to the default (Global only) on any failure.
   */
  async load(): Promise<void> {
    try {
      const [tabsSetting, activeSetting, bottomSetting, visibleSetting, collectionsRes] =
        await Promise.all([
          getSetting<Record<string, unknown>[]>('workspace.tabs').catch(() => null),
          getSetting<string>('workspace.active').catch(() => null),
          getSetting<string>('workspace.bottomTab').catch(() => null),
          getSetting<string>('workspace.bottomTabs').catch(() => null),
          listCollections().catch(() => null),
        ]);
      // Restore the customised strip, then the active tab; the active tab is
      // force-added to the strip below so it's always reachable.
      const restoredVisible = decodeVisible(visibleSetting?.value);
      if (restoredVisible) state.visibleBottomTabs = restoredVisible;
      if (isBottomTab(bottomSetting?.value)) {
        state.bottomTab = bottomSetting.value;
      }
      if (!state.visibleBottomTabs.includes(state.bottomTab)) {
        state.visibleBottomTabs = orderTabs([...state.visibleBottomTabs, state.bottomTab]);
      }
      const knownIds = new Set((collectionsRes?.collections ?? []).map((c) => c.id));
      const storedTabs = Array.isArray(tabsSetting?.value) ? tabsSetting.value : [];
      const restoredTabs: OpenTab[] = [];
      for (const item of storedTabs) {
        if (item.kind === 'nodeset') {
          const tab = restoreNodeSetTab(item);
          if (tab && !restoredTabs.some((t) => t.id === tab.id)) restoredTabs.push(tab);
          continue;
        }
        if (item.kind !== 'collection' || typeof item.collection_id !== 'number') continue;
        if (!knownIds.has(item.collection_id)) continue;
        const col = collectionsRes!.collections.find((c) => c.id === item.collection_id);
        if (!col) continue;
        const id = tabId(col.id);
        if (!restoredTabs.some((t) => t.id === id)) {
          restoredTabs.push({ id, kind: 'collection', collectionId: col.id, label: col.name, source: null });
        }
      }
      if (restoredTabs.length > 0) {
        state.openTabs = [GLOBAL_TAB, ...restoredTabs];
      }
      const activeId = typeof activeSetting?.value === 'string' ? activeSetting.value : 'global';
      if (state.openTabs.some((t) => t.id === activeId)) {
        state.activeWorkspaceId = activeId;
      }
    } catch {
      // Fall through — default state (Global tab, global active) is already set.
    }
  },

  get centerTab() {
    return state.centerTab;
  },
  get bottomTab() {
    return state.bottomTab;
  },
  get visibleBottomTabs(): BottomTab[] {
    return state.visibleBottomTabs;
  },
  // The strip's tab defs in canonical order — BottomPane feeds these to PaneTabs.
  get visibleTabDefs(): BottomTabDef[] {
    return state.visibleBottomTabs.map(tabDef);
  },
  isTabVisible(tab: BottomTab): boolean {
    return state.visibleBottomTabs.includes(tab);
  },
  get activeWorkspaceId() {
    return state.activeWorkspaceId;
  },
  get openTabs() {
    return state.openTabs;
  },
  setCenter(tab: CenterTab) {
    state.centerTab = tab;
  },
  setBottom(tab: BottomTab) {
    state.bottomTab = tab;
    // Selecting a tab implies it belongs on the strip — reveal it if a
    // caller (e.g. a "view in Domains" link) targets a hidden tab.
    if (!state.visibleBottomTabs.includes(tab)) {
      state.visibleBottomTabs = orderTabs([...state.visibleBottomTabs, tab]);
      void persistVisibleTabs(state.visibleBottomTabs);
    }
    void persistBottomTab(tab);
  },
  // Add a tab to the strip, or drop it. Dropping the active tab shifts focus
  // to a neighbour; the last remaining tab can't be dropped (the strip never
  // goes empty).
  toggleTab(tab: BottomTab) {
    if (state.visibleBottomTabs.includes(tab)) {
      const neighbor = neighborAfterRemoval(state.visibleBottomTabs, tab);
      if (neighbor === null) return; // last tab — refuse the drop
      state.visibleBottomTabs = state.visibleBottomTabs.filter((t) => t !== tab);
      if (state.bottomTab === tab) {
        state.bottomTab = neighbor;
        void persistBottomTab(neighbor);
      }
    } else {
      state.visibleBottomTabs = orderTabs([...state.visibleBottomTabs, tab]);
    }
    void persistVisibleTabs(state.visibleBottomTabs);
  },
  setWorkspace(id: string) {
    // Guard: refuse ids that aren't currently open. Falls back to 'global'.
    if (!state.openTabs.some((t) => t.id === id)) {
      state.activeWorkspaceId = 'global';
      void persistWorkspace(state);
      return;
    }
    state.activeWorkspaceId = id;
    void persistWorkspace(state);
  },
  tabId,

  activeCollectionId(): number | null {
    const tab = state.openTabs.find((t) => t.id === state.activeWorkspaceId);
    return tab?.collectionId ?? null;
  },
  activeLabel(): string {
    const tab = state.openTabs.find((t) => t.id === state.activeWorkspaceId);
    return tab?.label ?? 'Global';
  },

  async openCollectionTabById(id: number): Promise<void> {
    const tid = tabId(id);
    if (state.openTabs.some((t) => t.id === tid)) {
      state.activeWorkspaceId = tid;
      return;
    }
    try {
      const res = await listCollections();
      const row = res.collections.find((c) => c.id === id);
      if (!row) return; // silent — caller may be reacting to a stale id
      this.openCollectionTab(row);
    } catch {
      // Don't toast — this is a passive open path (chip click, post-start).
    }
  },

  openCollectionTab(c: Collection): void {
    const id = tabId(c.id);
    const existing = state.openTabs.find((t) => t.id === id);
    if (existing) {
      state.activeWorkspaceId = id;
      void persistWorkspace(state);
      return;
    }
    state.openTabs = [
      ...state.openTabs,
      { id, kind: 'collection', collectionId: c.id, label: c.name, source: null },
    ];
    state.activeWorkspaceId = id;
    void persistWorkspace(state);
  },

  /**
   * Open (or focus) a graph tab scoped to a node set. Reopening the same
   * source — same domain, same fingerprint cluster, the singleton hidden /
   * bookmarks sets, an identical selection — focuses the existing tab and
   * re-captures its members rather than stacking a duplicate.
   */
  openNodeSetTab(source: NodeSetSource, label: string): void {
    const id = nodeSetTabId(source);
    const trimmed = label.trim() || id;
    const idx = state.openTabs.findIndex((t) => t.id === id);
    if (idx !== -1) {
      // Refresh members + label in place (a derived source keeps its
      // descriptor; a captured source picks up the latest member set).
      const next = [...state.openTabs];
      next[idx] = { ...next[idx], source, label: trimmed };
      state.openTabs = next;
      state.activeWorkspaceId = id;
      void persistWorkspace(state);
      return;
    }
    state.openTabs = [
      ...state.openTabs,
      { id, kind: 'nodeset', collectionId: null, label: trimmed, source },
    ];
    state.activeWorkspaceId = id;
    void persistWorkspace(state);
  },

  // The active tab's node-set source, or null for Global / collection tabs.
  // GraphCanvas reads this to install the visibility scope predicate.
  activeNodeSetSource(): NodeSetSource | null {
    const tab = state.openTabs.find((t) => t.id === state.activeWorkspaceId);
    return tab?.source ?? null;
  },

  // Update a tab's display label without touching its id or active
  // state. Used by the Collection sub-tab after a successful rename so
  // the workspace strip and the sub-tab header stay in sync without an
  // extra fetch.
  renameTab(id: string, label: string): void {
    const trimmed = label.trim();
    if (!trimmed) return;
    const idx = state.openTabs.findIndex((t) => t.id === id);
    if (idx === -1) return;
    if (state.openTabs[idx].label === trimmed) return;
    const next = [...state.openTabs];
    next[idx] = { ...next[idx], label: trimmed };
    state.openTabs = next;
  },

  closeTab(id: string): void {
    if (id === 'global') return; // Global cannot close.
    const next = state.openTabs.filter((t) => t.id !== id);
    if (next.length === state.openTabs.length) return;
    state.openTabs = next;
    if (state.activeWorkspaceId === id) {
      state.activeWorkspaceId = 'global';
    }
    void persistWorkspace(state);
  },

  reconcileCollections(known: Collection[]): void {
    // Drop collection tabs whose id is no longer in the known set —
    // e.g. another window deleted the collection between picker opens.
    // Fires a toast per drop so the analyst sees why their tab vanished.
    const knownIds = new Set(known.map((c) => c.id));
    let activeDropped = false;
    const surviving: OpenTab[] = [];
    for (const t of state.openTabs) {
      // Only collection tabs are reconciled against the collection list;
      // global and nodeset tabs are independent of it.
      if (t.kind !== 'collection') {
        surviving.push(t);
        continue;
      }
      if (t.collectionId !== null && knownIds.has(t.collectionId)) {
        surviving.push(t);
      } else {
        if (t.id === state.activeWorkspaceId) activeDropped = true;
        toastStore.show(`Collection "${t.label}" — workspace closed.`, 'info');
      }
    }
    if (surviving.length !== state.openTabs.length) {
      state.openTabs = surviving;
    }
    if (activeDropped) {
      state.activeWorkspaceId = 'global';
    }
  },
};
