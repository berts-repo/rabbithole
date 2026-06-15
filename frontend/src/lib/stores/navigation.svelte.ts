// Left-pane sub-tab (Find / Intel / Crawl) and right-panel tab
// (Page / Preview / Domain / Analysis). Right-panel collapse state lives
// here too; F2 will layer localStorage persistence over it.

import { getSetting, putSetting } from '$lib/api';

export type LeftTab = 'find' | 'intel' | 'crawl';
export type RightTab = 'page' | 'preview' | 'domain' | 'analysis';

interface NavigationState {
  leftTab: LeftTab;
  rightTab: RightTab;
  rightCollapsed: boolean;
}

const state = $state<NavigationState>({
  leftTab: 'crawl',
  rightTab: 'page',
  rightCollapsed: false,
});

const LEFT_TABS: LeftTab[] = ['find', 'intel', 'crawl'];

async function persistLeftTab(tab: LeftTab): Promise<void> {
  try {
    await putSetting('nav.leftTab', tab);
  } catch {
    // Fire-and-forget — sub-tab persistence is a convenience.
  }
}

export const navigationStore = {
  // Restore the last-used left sub-tab so reopening the app keeps the
  // analyst's composer context. Called from app bootstrap.
  async load(): Promise<void> {
    try {
      const s = await getSetting<string>('nav.leftTab');
      if (s.value && (LEFT_TABS as string[]).includes(s.value)) {
        state.leftTab = s.value as LeftTab;
      }
    } catch {
      // Default (crawl) already set.
    }
  },
  get leftTab() {
    return state.leftTab;
  },
  get rightTab() {
    return state.rightTab;
  },
  get rightCollapsed() {
    return state.rightCollapsed;
  },
  setLeft(tab: LeftTab) {
    state.leftTab = tab;
    void persistLeftTab(tab);
  },
  setRight(tab: RightTab) {
    state.rightTab = tab;
  },
  setRightCollapsed(collapsed: boolean) {
    state.rightCollapsed = collapsed;
  },
};
