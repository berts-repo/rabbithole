// One-shot pre-filter stash for the bottom-pane sub-tabs.
//
// The right-pane Domain tab needs to send "view all" links into the
// bottom-pane Domains and Fingerprints sub-tabs, with the target tab
// pre-filtered by host. We stage the filter value here and the target
// tab drains it on mount / first activation. Same shape as
// `findPendingStore` — store the value, consume once.

import type { BottomTab } from './workspace.svelte';
import { workspaceStore } from './workspace.svelte';

interface State {
  pending: { tab: BottomTab; filter: string } | null;
}

const state = $state<State>({ pending: null });

export const bottomPanePresetStore = {
  get pending() {
    return state.pending;
  },
  // Stage a filter value and switch the bottom pane to the target tab in
  // one shot. Callers don't have to coordinate the two — that pairing is
  // the whole point of this store.
  send(tab: BottomTab, filter: string): void {
    state.pending = { tab, filter };
    workspaceStore.setBottom(tab);
  },
  // The receiving sub-tab calls this on mount. Returns the filter
  // intended for it and clears the slot; returns null when the pending
  // entry was for a different tab.
  consume(tab: BottomTab): string | null {
    if (state.pending === null) return null;
    if (state.pending.tab !== tab) return null;
    const value = state.pending.filter;
    state.pending = null;
    return value;
  },
};
