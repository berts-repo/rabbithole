// Client-side visibility for bottom-pane sub-tabs.
//
// Distinct from the server-backed graph_filters table (Hidden sub-tab),
// which permanently excludes URLs/titles matching a substring. This store
// is ephemeral — it lives for the page session only.
//
// Two scopes:
//   - hidden hosts  → Bookmarks / Collection / Domains sub-tabs toggle a
//                     whole .onion host on or off.
//   - hidden nodes  → Fingerprints sub-tab members toggle a single node.
//
// GraphCanvas's computeVisibility pass reads `isHidden(host)` and
// `isNodeHidden(id)`; a node is hidden if either matches. The
// `domainVisibilityStore` name is kept for backward compatibility with
// existing import sites — the host path is still the primary use.
//
// Defaults to "everything visible". `clear()` resets both sets.

interface DomainVisibilityState {
  hidden: Set<string>;
  hiddenNodes: Set<number>;
}

const state = $state<DomainVisibilityState>({
  hidden: new Set(),
  hiddenNodes: new Set(),
});

function nextSet<T>(src: Set<T>, mutate: (s: Set<T>) => void): Set<T> {
  // Fresh Set so Svelte 5 rune diffing (by reference) re-runs consumers.
  const next = new Set(src);
  mutate(next);
  return next;
}

export const domainVisibilityStore = {
  get hidden(): ReadonlySet<string> {
    return state.hidden;
  },
  get hiddenNodes(): ReadonlySet<number> {
    return state.hiddenNodes;
  },

  isHidden(host: string | null | undefined): boolean {
    if (!host) return false;
    return state.hidden.has(host);
  },

  isVisible(host: string | null | undefined): boolean {
    return !this.isHidden(host);
  },

  hide(host: string): void {
    if (state.hidden.has(host)) return;
    state.hidden = nextSet(state.hidden, (s) => s.add(host));
  },

  show(host: string): void {
    if (!state.hidden.has(host)) return;
    state.hidden = nextSet(state.hidden, (s) => s.delete(host));
  },

  toggle(host: string): void {
    state.hidden = nextSet(state.hidden, (s) => {
      if (s.has(host)) s.delete(host);
      else s.add(host);
    });
  },

  isNodeHidden(id: number | null | undefined): boolean {
    if (id === null || id === undefined) return false;
    return state.hiddenNodes.has(id);
  },

  isNodeVisible(id: number | null | undefined): boolean {
    return !this.isNodeHidden(id);
  },

  toggleNode(id: number): void {
    state.hiddenNodes = nextSet(state.hiddenNodes, (s) => {
      if (s.has(id)) s.delete(id);
      else s.add(id);
    });
  },

  clear(): void {
    if (state.hidden.size === 0 && state.hiddenNodes.size === 0) return;
    state.hidden = new Set();
    state.hiddenNodes = new Set();
  },
};
