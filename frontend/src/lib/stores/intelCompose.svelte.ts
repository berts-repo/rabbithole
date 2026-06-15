// Intel compose-form state: the staged target buffer + per-section collapse.
//
// Two concerns, both small:
//
//  1. Staged compose target — surfaces that "Queue Analysis" (graph context
//     menu, right-pane action bar, keyboard shortcuts) stage a target here and
//     switch the left pane to Intel; ComposeForm drains it on mount. Identical
//     to findPendingStore / batchConfirmStore: the producer fires long before
//     (or independent of) the consumer being mounted, so we buffer.
//
//  2. Section collapse — pure view-state, persisted to localStorage exactly
//     like pane sizes in layout.svelte.ts (not the settings table; this is
//     ephemeral presentation, single-user, no cross-device need).

import {
  targetCount,
  targetFromIds,
  targetFromNodes,
  type ComposeTarget,
} from './intelComposeTarget';
import { createCollapseStore } from './sectionCollapse.svelte';

// Pure target model lives in intelComposeTarget.ts (unit-tested); re-export so
// callers keep importing the compose vocabulary from one specifier.
export { targetCount, targetFromIds, targetFromNodes, type ComposeTarget };

interface ComposeState {
  staged: ComposeTarget | null;
}

const state = $state<ComposeState>({ staged: null });

export const intelComposeStore = {
  get staged() {
    return state.staged;
  },
  /** Producer side — stage a target for the form to pick up. */
  stage(target: ComposeTarget) {
    state.staged = target;
  },
  /** Consumer side — drain once; returning makes "consumed once" obvious. */
  consume(): ComposeTarget | null {
    const t = state.staged;
    state.staged = null;
    return t;
  },
};

// --- section collapse (localStorage) ---------------------------------------

export const intelSectionsStore = createCollapseStore('rabbithole.intel.collapsed');
