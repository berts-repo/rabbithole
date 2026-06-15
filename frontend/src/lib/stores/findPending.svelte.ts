// Tiny staging buffer for the left pane Find sub-tab.
//
// The right pane / bottom pane fire "Send to Find" on entity rows and
// search results long before the FindSidebar is mounted (or even
// implemented — F5 owns the sidebar). We stash the value here so the
// sidebar can drain it on mount, identical to how batchConfirmStore
// loads URLs into CrawlControls before that component exists.

interface State {
  pendingQuery: string | null;
}

const state = $state<State>({ pendingQuery: null });

export const findPendingStore = {
  get pendingQuery() {
    return state.pendingQuery;
  },
  load(query: string) {
    state.pendingQuery = query;
  },
  // Drain — caller takes ownership. Returning the value (instead of
  // exposing a getter the consumer reads then clears) keeps the
  // "consumed once" semantics obvious at the call site.
  consume(): string | null {
    const q = state.pendingQuery;
    state.pendingQuery = null;
    return q;
  },
};
