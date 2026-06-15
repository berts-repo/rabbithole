// Per-workspace-tab graph collapse state (item 11, Phase 3d / D8).
//
// Collapse is a *view arrangement*, not a durable fact — but it persists, per
// workspace tab, saved with the project. A "Markets overview" tab folded by
// label and a "NightMarket deep-dive" tab folded by domain each remember their
// own folds across a restart. The renames and labels the folds reference stay
// durable in the DB regardless; only the folding is tab-scoped.
//
// State is keyed by `workspaceStore.activeWorkspaceId` (Global included, which
// `workspace.tabs` omits) and persisted to the `graph.collapse` JSON setting.
// The apply paths read the active tab's sets via `graph.svelte.ts`'s
// `currentClusterOptions`; the canvas rebuilds when they change.

import { getSetting, putSetting } from '$lib/api';
import { workspaceStore } from './workspace.svelte';

interface TabCollapse {
  domains: Set<string>;
  labels: Set<number>;
}

interface CollapseState {
  // Only non-empty tabs are kept — an expanded tab leaves no residue.
  byTab: Record<string, TabCollapse>;
  loaded: boolean;
}

const state = $state<CollapseState>({ byTab: {}, loaded: false });

const EMPTY: TabCollapse = { domains: new Set(), labels: new Set() };

function activeId(): string {
  return workspaceStore.activeWorkspaceId;
}

function entryOf(tab: string): TabCollapse {
  return state.byTab[tab] ?? EMPTY;
}

// Serialize to the persisted shape, dropping empty tabs (the backend does too).
async function persist(): Promise<void> {
  const payload: Record<string, { domains: string[]; labels: number[] }> = {};
  for (const [tab, e] of Object.entries(state.byTab)) {
    if (e.domains.size === 0 && e.labels.size === 0) continue;
    payload[tab] = { domains: [...e.domains], labels: [...e.labels] };
  }
  try {
    await putSetting('graph.collapse', payload);
  } catch {
    // Fire-and-forget — collapse persistence is a convenience, not state we
    // surface failures for (the in-memory folds still apply this session).
  }
}

// Copy-on-write mutate of the active tab, then persist. Reassigns `byTab` and
// the tab's Sets so rune readers (the canvas rebuild effect) re-run.
function mutateActive(fn: (e: TabCollapse) => void): void {
  const tab = activeId();
  const cur = state.byTab[tab];
  const next: TabCollapse = {
    domains: new Set(cur?.domains),
    labels: new Set(cur?.labels),
  };
  fn(next);
  const byTab = { ...state.byTab };
  if (next.domains.size === 0 && next.labels.size === 0) delete byTab[tab];
  else byTab[tab] = next;
  state.byTab = byTab;
  void persist();
}

export const graphCollapseStore = {
  get loaded() {
    return state.loaded;
  },
  // The active tab's folded domains / labels — what `currentClusterOptions`
  // feeds the fold resolver. Reading these tracks both `byTab` and the active
  // workspace id, so a tab switch or a fold toggle re-runs the canvas rebuild.
  get domains(): ReadonlySet<string> {
    return entryOf(activeId()).domains;
  },
  get labels(): ReadonlySet<number> {
    return entryOf(activeId()).labels;
  },
  // Any fold active on the current tab — drives the "Expand all" affordance.
  get active(): boolean {
    const e = entryOf(activeId());
    return e.domains.size > 0 || e.labels.size > 0;
  },

  isDomainCollapsed(host: string): boolean {
    return entryOf(activeId()).domains.has(host);
  },
  isLabelCollapsed(id: number): boolean {
    return entryOf(activeId()).labels.has(id);
  },

  collapseDomain(host: string): void {
    if (!host || this.isDomainCollapsed(host)) return;
    mutateActive((e) => e.domains.add(host));
  },
  expandDomain(host: string): void {
    if (!this.isDomainCollapsed(host)) return;
    mutateActive((e) => e.domains.delete(host));
  },
  toggleDomain(host: string): void {
    if (!host) return;
    mutateActive((e) => (e.domains.has(host) ? e.domains.delete(host) : e.domains.add(host)));
  },

  collapseLabel(id: number): void {
    if (this.isLabelCollapsed(id)) return;
    mutateActive((e) => e.labels.add(id));
  },
  expandLabel(id: number): void {
    if (!this.isLabelCollapsed(id)) return;
    mutateActive((e) => e.labels.delete(id));
  },
  toggleLabel(id: number): void {
    mutateActive((e) => (e.labels.has(id) ? e.labels.delete(id) : e.labels.add(id)));
  },

  // Expand everything on the current tab in one shot.
  clear(): void {
    const tab = activeId();
    if (!state.byTab[tab]) return;
    const byTab = { ...state.byTab };
    delete byTab[tab];
    state.byTab = byTab;
    void persist();
  },

  async load(): Promise<void> {
    try {
      const r = await getSetting<string | Record<string, unknown>>('graph.collapse');
      const raw = r.value;
      let parsed: Record<string, { domains?: unknown; labels?: unknown }> = {};
      if (typeof raw === 'string' && raw.trim()) parsed = JSON.parse(raw);
      else if (raw && typeof raw === 'object') parsed = raw as typeof parsed;
      const byTab: Record<string, TabCollapse> = {};
      for (const [tab, e] of Object.entries(parsed)) {
        const domains = Array.isArray(e.domains) ? e.domains.filter((d): d is string => typeof d === 'string') : [];
        const labels = Array.isArray(e.labels)
          ? e.labels.map(Number).filter((n) => Number.isInteger(n) && n > 0)
          : [];
        if (domains.length === 0 && labels.length === 0) continue;
        byTab[tab] = { domains: new Set(domains), labels: new Set(labels) };
      }
      state.byTab = byTab;
      state.loaded = true;
    } catch {
      // Fall through — default (no folds) is already set.
      state.loaded = true;
    }
  },
};
