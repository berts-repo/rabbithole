<script lang="ts">
  // Shared two-element row for every bottom-pane sub-tab. The owning
  // sub-tab supplies the content snippet (label / URL / badges) and
  // wires what "visible" and "active" mean for its data — this component
  // owns only the layout, the visibility-dot button, click-to-full-
  // select plumbing, and the dimmed/active visual states.
  //
  // Selection model (CLAUDE.md):
  //   - Clicking the content button = full select. The owner calls
  //     selectionStore.fullSelect(id) from onSelect.
  //   - The ●/○ button is a separate action and never triggers select —
  //     its click is stopped so the row click handler doesn't also fire.
  //
  // Right-click context menu (spec: bottom-pane "Right-click context
  // menu" section): the owner attaches oncontextmenu to mount the shared
  // ContextMenu with the row-derived MenuTarget. This component just
  // forwards the event.
  //
  // Active marker is "scoped to the owning sub-tab" — the parent decides
  // whether *its* row is active by comparing its row id to whatever
  // selection state it tracks. Switching tabs doesn't dim or move the
  // marker here; the new tab's parent decides afresh.

  import type { Snippet } from 'svelte';
  import { Network } from 'lucide-svelte';

  interface Props {
    // True when the underlying domain / node is currently visible in
    // the graph. False renders the row dimmed and flips the dot to ○.
    visible: boolean;
    // True when this row is the bottom-pane's active full-select row
    // *within its owning sub-tab*. Parent computes this.
    active: boolean;
    // Content for the row body — typically a label, URL, and any badges.
    // Rendered inside the content <button>, so it must be inline-safe
    // (no block elements, no nested interactive controls).
    children: Snippet;
    // Toggle the visibility of whatever this row represents (a domain,
    // a single URL, a fingerprint cluster member). Owner decides the
    // scope and the side effect.
    onToggleVisibility: () => void;
    // Full-select on row click. Owner calls selectionStore.fullSelect
    // (plus anything sub-tab-specific like opening a workspace).
    onSelect: () => void;
    // Right-click handler. Owner mounts ContextMenu at the event coords
    // with a row-derived MenuTarget. If omitted, the browser context
    // menu is left alone.
    oncontextmenu?: (event: MouseEvent) => void;
    // Optional aria label for the visibility button — falls back to a
    // generic "Hide" / "Show" if the owner doesn't supply one.
    visibilityLabel?: string;
    // Optional "open this row's node set as a graph tab" action. When
    // supplied, a trailing graph-icon button appears (NodeSet Workspaces).
    // Its click is stopped so the row's content-button doesn't also fire.
    onOpenAsTab?: () => void;
    // aria/title for the open-as-tab button.
    openAsTabLabel?: string;
  }

  let {
    visible,
    active,
    children,
    onToggleVisibility,
    onSelect,
    oncontextmenu,
    visibilityLabel,
    onOpenAsTab,
    openAsTabLabel,
  }: Props = $props();

  function handleOpenAsTabClick(e: MouseEvent): void {
    e.stopPropagation();
    onOpenAsTab?.();
  }

  function handleVisibilityClick(e: MouseEvent): void {
    // The visibility dot lives inside the row but is its own action;
    // stop the click so the row's content-button doesn't also receive
    // it via bubbling.
    e.stopPropagation();
    onToggleVisibility();
  }
</script>

<div
  class="row"
  class:active
  class:dimmed={!visible}
  oncontextmenu={oncontextmenu}
  role="presentation"
>
  <button
    type="button"
    class="vis"
    class:on={visible}
    aria-label={visibilityLabel ?? (visible ? 'Hide' : 'Show')}
    aria-pressed={visible}
    title={visibilityLabel ?? (visible ? 'Hide' : 'Show')}
    onclick={handleVisibilityClick}
  >
    {visible ? '●' : '○'}
  </button>
  <button
    type="button"
    class="content"
    onclick={onSelect}
  >
    {@render children()}
  </button>
  {#if onOpenAsTab}
    <button
      type="button"
      class="open-tab"
      aria-label={openAsTabLabel ?? 'Open as graph tab'}
      title={openAsTabLabel ?? 'Open as graph tab'}
      onclick={handleOpenAsTabClick}
    >
      <Network size={13} />
    </button>
  {/if}
</div>

<style>
  .row {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 2px 4px;
    border-radius: 2px;
    transition: background 80ms ease;
  }
  .row:hover {
    background: rgba(0, 212, 170, 0.06);
  }
  .row.active {
    background: rgba(0, 212, 170, 0.14);
  }
  .row.active:hover {
    background: rgba(0, 212, 170, 0.18);
  }
  .row.dimmed {
    opacity: 0.45;
  }
  .row.dimmed:hover {
    opacity: 0.7;
  }
  .vis {
    flex: 0 0 auto;
    width: 18px;
    height: 18px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    background: transparent;
    border: none;
    color: var(--muted);
    font-size: 12px;
    line-height: 1;
    cursor: pointer;
    border-radius: 2px;
  }
  .vis.on {
    color: var(--accent);
  }
  .vis:hover {
    background: rgba(0, 212, 170, 0.12);
    color: var(--text);
  }
  .content {
    flex: 1 1 auto;
    min-width: 0;
    display: block;
    text-align: left;
    background: transparent;
    border: none;
    color: var(--text);
    font: inherit;
    padding: 2px 4px;
    cursor: pointer;
    border-radius: 2px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .content:hover {
    color: var(--accent);
  }
  .row.active .content {
    color: var(--accent);
  }
  .open-tab {
    flex: 0 0 auto;
    width: 20px;
    height: 18px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    background: transparent;
    border: none;
    color: var(--muted);
    cursor: pointer;
    border-radius: 2px;
    opacity: 0;
    transition: opacity 80ms ease;
  }
  .row:hover .open-tab,
  .open-tab:focus-visible {
    opacity: 0.7;
  }
  .open-tab:hover {
    opacity: 1;
    color: var(--accent);
    background: rgba(0, 212, 170, 0.12);
  }
</style>
