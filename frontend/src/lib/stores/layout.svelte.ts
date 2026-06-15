// Pane sizes + right-panel collapse, persisted to localStorage under
// `onionhole.pane.*`. Constraints + defaults from app-shell.md. Sizes
// write on drag-end (not every move) to avoid spamming storage.

const KEYS = {
  left: 'onionhole.pane.left',
  right: 'onionhole.pane.right',
  bottom: 'onionhole.pane.bottom',
  leftCollapsed: 'onionhole.pane.leftCollapsed',
  leftLastWidth: 'onionhole.pane.leftLastWidth',
  rightCollapsed: 'onionhole.pane.rightCollapsed',
  rightLastWidth: 'onionhole.pane.rightLastWidth',
  bottomCollapsed: 'onionhole.pane.bottomCollapsed',
  bottomLastHeight: 'onionhole.pane.bottomLastHeight',
} as const;

export const PANE_LIMITS = {
  left: { min: 180, max: 420, default: 260 },
  right: { min: 220, max: 520, default: 320 },
  // Bottom max is 60% of viewport — recomputed on every clamp call so a
  // window resize narrows the saved value rather than leaving it stale.
  bottom: { min: 120, defaultPx: 220, maxFrac: 0.6 },
} as const;

export const COLLAPSED_RIGHT_PX = 24;
export const COLLAPSED_LEFT_PX = 24;
export const COLLAPSED_BOTTOM_PX = 28;

function readNumber(key: string): number | null {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(key);
  if (raw === null) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function readBool(key: string): boolean | null {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(key);
  if (raw === null) return null;
  return raw === 'true';
}

function clampLeft(px: number): number {
  return Math.min(PANE_LIMITS.left.max, Math.max(PANE_LIMITS.left.min, px));
}

function clampRight(px: number): number {
  return Math.min(PANE_LIMITS.right.max, Math.max(PANE_LIMITS.right.min, px));
}

function bottomMax(): number {
  if (typeof window === 'undefined') return PANE_LIMITS.bottom.defaultPx;
  return Math.floor(window.innerHeight * PANE_LIMITS.bottom.maxFrac);
}

function clampBottom(px: number): number {
  return Math.min(bottomMax(), Math.max(PANE_LIMITS.bottom.min, px));
}

interface LayoutState {
  left: number;
  right: number;
  bottom: number;
  leftCollapsed: boolean;
  leftLastWidth: number;
  rightCollapsed: boolean;
  rightLastWidth: number;
  bottomCollapsed: boolean;
  bottomLastHeight: number;
  // Right-pane auto-expand suppression: once the analyst explicitly
  // collapses the right pane during a session, new selections stop
  // auto-expanding it. Per spec the flag does not persist across page
  // loads (the panel always starts collapsed; the suppression resets).
  userCollapsedRightThisSession: boolean;
}

const initial: LayoutState = {
  left: clampLeft(readNumber(KEYS.left) ?? PANE_LIMITS.left.default),
  right: clampRight(readNumber(KEYS.right) ?? PANE_LIMITS.right.default),
  bottom: clampBottom(readNumber(KEYS.bottom) ?? PANE_LIMITS.bottom.defaultPx),
  leftCollapsed: readBool(KEYS.leftCollapsed) ?? false,
  leftLastWidth: clampLeft(readNumber(KEYS.leftLastWidth) ?? PANE_LIMITS.left.default),
  rightCollapsed: readBool(KEYS.rightCollapsed) ?? false,
  rightLastWidth: clampRight(readNumber(KEYS.rightLastWidth) ?? PANE_LIMITS.right.default),
  bottomCollapsed: readBool(KEYS.bottomCollapsed) ?? false,
  bottomLastHeight: clampBottom(
    readNumber(KEYS.bottomLastHeight) ?? PANE_LIMITS.bottom.defaultPx,
  ),
  userCollapsedRightThisSession: false,
};

const state = $state<LayoutState>(initial);

function persist(key: string, value: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Quota or disabled storage — silently drop. Pane sizes will reset
    // on next load, which is preferable to crashing the shell.
  }
}

export const layoutStore = {
  get left() {
    return state.left;
  },
  get right() {
    return state.right;
  },
  get bottom() {
    return state.bottom;
  },
  get leftCollapsed() {
    return state.leftCollapsed;
  },
  get leftLastWidth() {
    return state.leftLastWidth;
  },
  get rightCollapsed() {
    return state.rightCollapsed;
  },
  get rightLastWidth() {
    return state.rightLastWidth;
  },
  get bottomCollapsed() {
    return state.bottomCollapsed;
  },
  get bottomLastHeight() {
    return state.bottomLastHeight;
  },
  /** Effective left column width — collapsed state overrides stored width. */
  get leftEffective() {
    return state.leftCollapsed ? COLLAPSED_LEFT_PX : state.left;
  },
  /** Effective right column width — collapsed state overrides stored width. */
  get rightEffective() {
    return state.rightCollapsed ? COLLAPSED_RIGHT_PX : state.right;
  },
  /** Effective bottom row height — collapsed state overrides stored value. */
  get bottomEffective() {
    return state.bottomCollapsed ? COLLAPSED_BOTTOM_PX : state.bottom;
  },

  /** Live updates during drag — do not persist on every move. */
  setLeftLive(px: number) {
    state.left = clampLeft(px);
  },
  setRightLive(px: number) {
    state.right = clampRight(px);
  },
  setBottomLive(px: number) {
    state.bottom = clampBottom(px);
  },

  /** Commit on pointer-up — persists. */
  commitLeft() {
    persist(KEYS.left, String(state.left));
  },
  commitRight() {
    state.rightLastWidth = state.right;
    persist(KEYS.right, String(state.right));
    persist(KEYS.rightLastWidth, String(state.rightLastWidth));
  },
  commitBottom() {
    persist(KEYS.bottom, String(state.bottom));
  },

  collapseLeft() {
    if (state.leftCollapsed) return;
    state.leftLastWidth = state.left;
    persist(KEYS.leftLastWidth, String(state.leftLastWidth));
    state.leftCollapsed = true;
    persist(KEYS.leftCollapsed, 'true');
  },
  expandLeft() {
    if (!state.leftCollapsed) return;
    state.leftCollapsed = false;
    state.left = clampLeft(state.leftLastWidth);
    persist(KEYS.leftCollapsed, 'false');
    persist(KEYS.left, String(state.left));
  },
  toggleLeft() {
    if (state.leftCollapsed) this.expandLeft();
    else this.collapseLeft();
  },

  collapseRight() {
    if (state.rightCollapsed) return;
    state.rightLastWidth = state.right;
    persist(KEYS.rightLastWidth, String(state.rightLastWidth));
    state.rightCollapsed = true;
    state.userCollapsedRightThisSession = true;
    persist(KEYS.rightCollapsed, 'true');
  },
  expandRight() {
    if (!state.rightCollapsed) return;
    state.rightCollapsed = false;
    state.userCollapsedRightThisSession = false;
    state.right = clampRight(state.rightLastWidth);
    persist(KEYS.rightCollapsed, 'false');
    persist(KEYS.right, String(state.right));
  },
  toggleRight() {
    if (state.rightCollapsed) this.expandRight();
    else this.collapseRight();
  },
  // F6 — auto-expand on new selection unless the analyst collapsed the
  // panel this session. The toggle button explicitly resets the suppression
  // (the user expanding by hand opts back in). Selection-driven expansion
  // uses this entry point so it can be ignored silently.
  expandRightForSelection() {
    if (!state.rightCollapsed) return;
    if (state.userCollapsedRightThisSession) return;
    state.rightCollapsed = false;
    state.right = clampRight(state.rightLastWidth);
    persist(KEYS.rightCollapsed, 'false');
    persist(KEYS.right, String(state.right));
  },

  collapseBottom() {
    if (state.bottomCollapsed) return;
    state.bottomLastHeight = state.bottom;
    persist(KEYS.bottomLastHeight, String(state.bottomLastHeight));
    state.bottomCollapsed = true;
    persist(KEYS.bottomCollapsed, 'true');
  },
  expandBottom() {
    if (!state.bottomCollapsed) return;
    state.bottomCollapsed = false;
    state.bottom = clampBottom(state.bottomLastHeight);
    persist(KEYS.bottomCollapsed, 'false');
    persist(KEYS.bottom, String(state.bottom));
  },
  toggleBottom() {
    if (state.bottomCollapsed) this.expandBottom();
    else this.collapseBottom();
  },

  /** Re-clamp to current viewport — call on window resize. */
  reclamp() {
    state.bottom = clampBottom(state.bottom);
  },
};
