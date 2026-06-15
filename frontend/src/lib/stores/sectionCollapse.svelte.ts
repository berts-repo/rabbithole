// Generic collapse-state store for collapsible sections (left/right/crawl
// panes). Each pane creates one store under its own localStorage key; the
// store maps a section id → collapsed boolean and persists on every toggle.
//
// Pairs with `lib/ui/CollapsibleSection.svelte`, which is a controlled
// component — the consumer reads `isCollapsed(id)` and calls `toggle(id)`.

export interface CollapseStore {
  isCollapsed(id: string): boolean;
  toggle(id: string): void;
}

export function createCollapseStore(storageKey: string): CollapseStore {
  function load(): Record<string, boolean> {
    if (typeof window === 'undefined') return {};
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch {
      return {};
    }
  }

  const state = $state<{ map: Record<string, boolean> }>({ map: load() });

  function persist(): void {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(state.map));
    } catch {
      // Persistence is a convenience; ignore quota / privacy-mode failures.
    }
  }

  return {
    isCollapsed(id: string): boolean {
      return state.map[id] === true;
    },
    toggle(id: string): void {
      state.map = { ...state.map, [id]: !state.map[id] };
      persist();
    },
  };
}
