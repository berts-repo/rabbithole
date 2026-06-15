// Open-state store for the shared row-style right-click context menu.
//
// One menu can be open at a time across every surface that uses it —
// bottom-pane sub-tabs and the Search tab today, any future row list
// tomorrow. Opening a new menu replaces the old one. The actual rendering
// (ContextMenu plus the rename / monitor / collection modals that menu
// items open) lives in `RowContextMenu.svelte`, mounted once in
// `AppShell.svelte`. Rows just call `openAt()` from their oncontextmenu
// handler with a row-derived target.
//
// This is the DOM-row counterpart to the graph's canvas-coord menu
// (contextMenuAdapter + GraphCanvas mount): same builders + actions, but
// triggered from row right-clicks and positioned in viewport space.

import type { GraphNode } from '$lib/api';
import type { MenuCapability } from './sections';

// What the menu needs to know about the right-clicked row. Surfaces
// build this from their own row data — typically by looking up the node
// in graphStore.payload when an id is known, or constructing the minimum
// URL-only shape for a row that pre-exists any crawl (Bookmarks, an
// uncrawled Search result).
export interface RowMenuTarget {
  url: string;
  // Optional — present when the row maps to a real node in the current
  // graph payload. Carries the lifecycle flags the section builder gates
  // on (state / flag_status / reviewed / domain).
  node?: GraphNode;
  // Known node id even when the full node isn't in the current payload
  // (e.g. a crawled Search result whose node isn't in the loaded graph).
  // id-bound actions resolve an id from `node?.id ?? nodeId ?? a fresh
  // stub`, so a URL-only row still acts — it just mints a stub first.
  nodeId?: number;
  // True when the menu opens from a collection-scoped surface (the
  // Collection sub-tab, or future cluster workspace). Surfaces an extra
  // "Remove from Collection" item.
  inCollection?: boolean;
  // Collection-scoped surface passes its remove handler in so the menu
  // doesn't need to know the active collection id or the API call.
  onRemoveFromCollection?: () => void | Promise<void>;
  // Which menu verbs this row offers. Omit for the full menu (bottom-pane
  // rows). The Search tab narrows it per row — graph-only verbs (Focus /
  // Hide / Rename / Reviewed) only on a row that already maps to a node.
  capabilities?: ReadonlySet<MenuCapability>;
}

interface OpenState {
  target: RowMenuTarget;
  // Viewport coords — the RowContextMenu mount uses a fixed overlay so
  // x/y land in client space directly.
  x: number;
  y: number;
}

const state = $state<{ open: OpenState | null }>({ open: null });

export const rowContextMenu = {
  get current(): OpenState | null {
    return state.open;
  },
  // Open the menu at the given viewport coords. Replaces any previously-
  // open menu (the renderer's outside-click handler closes the prior one
  // before this fires anyway, but the explicit replace is defensive).
  open(target: RowMenuTarget, x: number, y: number): void {
    state.open = { target, x, y };
  },
  // Open at an event's viewport coords. Convenience wrapper for the
  // common oncontextmenu(event) → open path.
  openAt(target: RowMenuTarget, event: MouseEvent): void {
    event.preventDefault();
    state.open = { target, x: event.clientX, y: event.clientY };
  },
  close(): void {
    state.open = null;
  },
};
