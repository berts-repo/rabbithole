<script lang="ts" module>
  // The menu shape lives with the section builders in $lib/contextMenu —
  // those produce it, this component renders it. Imported for local use
  // and re-exported so existing
  // `import { type MenuItem } from '$lib/contextMenu/ContextMenu.svelte'`
  // sites resolve.
  import type { MenuItem, MenuSection } from './sections';
  export type { MenuItem, MenuSection };
</script>

<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';

  interface Props {
    sections: MenuSection[];
    // Coords are relative to the menu's positioned ancestor. The menu
    // auto-flips left/up if it would overflow that container's
    // right/bottom edge.
    x: number;
    y: number;
    onClose: () => void;
  }

  let { sections, x, y, onClose }: Props = $props();

  let rootEl: HTMLDivElement | undefined = $state();
  // Snapshot x/y as the opening position. The parent re-creates this
  // component on every right-click, so the props are effectively
  // immutable for our lifetime; `pos` then mutates in onMount if the
  // menu needs to flip away from a viewport edge.
  let pos = $state(untrack(() => ({ x, y })));

  // Flatten sections to a single navigable list of enabled items so
  // ArrowUp/Down skip past dividers and disabled rows.
  const enabledIndex = $derived.by(() => {
    const list: Array<{ section: number; item: number }> = [];
    sections.forEach((section, si) => {
      section.items.forEach((it, ii) => {
        if (!it.disabled) list.push({ section: si, item: ii });
      });
    });
    return list;
  });

  let focusedNav = $state<number>(-1);

  function activate(item: MenuItem): void {
    if (item.disabled) return;
    // Close first so the caller's side-effects (e.g. graphStore.setEgoFocus
    // triggering a refresh) don't race with the menu DOM unmount.
    onClose();
    void item.onSelect();
  }

  function onKey(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
      return;
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (enabledIndex.length === 0) return;
      const delta = e.key === 'ArrowDown' ? 1 : -1;
      const next = focusedNav < 0
        ? (e.key === 'ArrowDown' ? 0 : enabledIndex.length - 1)
        : (focusedNav + delta + enabledIndex.length) % enabledIndex.length;
      focusedNav = next;
      return;
    }
    if (e.key === 'Enter' || e.key === ' ') {
      if (focusedNav < 0) return;
      e.preventDefault();
      const pick = enabledIndex[focusedNav];
      activate(sections[pick.section].items[pick.item]);
    }
  }

  function onDocPointerDown(e: PointerEvent): void {
    if (!rootEl) return;
    if (e.target instanceof Node && rootEl.contains(e.target)) return;
    onClose();
  }

  onMount(() => {
    document.addEventListener('keydown', onKey, true);
    document.addEventListener('pointerdown', onDocPointerDown, true);
    // After the first paint, measure and nudge the menu back inside the
    // positioned ancestor if it would overflow. We position relative to
    // that ancestor, so the bounds we care about are the offsetParent's.
    void tick().then(() => {
      if (!rootEl) return;
      const parent = rootEl.offsetParent as HTMLElement | null;
      if (!parent) return;
      const pw = parent.clientWidth;
      const ph = parent.clientHeight;
      const r = rootEl.getBoundingClientRect();
      let nx = pos.x;
      let ny = pos.y;
      if (pos.x + r.width > pw) nx = Math.max(0, pw - r.width - 4);
      if (pos.y + r.height > ph) ny = Math.max(0, pos.y - r.height);
      if (nx !== pos.x || ny !== pos.y) pos = { x: nx, y: ny };
    });
    return () => {
      document.removeEventListener('keydown', onKey, true);
      document.removeEventListener('pointerdown', onDocPointerDown, true);
    };
  });

  function isFocused(si: number, ii: number): boolean {
    if (focusedNav < 0) return false;
    const pick = enabledIndex[focusedNav];
    return pick.section === si && pick.item === ii;
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<div
  bind:this={rootEl}
  class="menu"
  role="menu"
  tabindex="-1"
  style:left="{pos.x}px"
  style:top="{pos.y}px"
  oncontextmenu={(e) => e.preventDefault()}
>
  {#each sections as section, si (si)}
    {#if section.label}
      <div class="divider"><span>{section.label}</span></div>
    {:else if si > 0}
      <div class="divider bare"></div>
    {/if}
    {#each section.items as item, ii (ii)}
      <button
        type="button"
        role="menuitem"
        class="item"
        class:disabled={item.disabled}
        class:focused={isFocused(si, ii)}
        title={item.disabled ? item.disabledReason ?? '' : ''}
        aria-disabled={item.disabled ? 'true' : undefined}
        onclick={() => activate(item)}
        onmouseenter={() => {
          if (item.disabled) return;
          const idx = enabledIndex.findIndex(
            (e) => e.section === si && e.item === ii,
          );
          if (idx >= 0) focusedNav = idx;
        }}
      >
        {item.label}
      </button>
    {/each}
  {/each}
</div>

<style>
  .menu {
    position: absolute;
    z-index: 8;
    min-width: 200px;
    background: rgba(10, 15, 13, 0.97);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 4px 0;
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.45);
    font-size: 11px;
    color: var(--text);
    user-select: none;
  }
  .divider {
    padding: 6px 10px 2px;
    font-size: 9px;
    color: var(--muted);
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .divider span::before {
    content: '— ';
  }
  .divider span::after {
    content: ' —';
  }
  .divider.bare {
    padding: 0;
    margin: 4px 0;
    border-top: 1px solid var(--border);
  }
  .item {
    display: block;
    width: 100%;
    text-align: left;
    padding: 5px 12px;
    background: transparent;
    border: none;
    color: var(--text);
    font: inherit;
    cursor: pointer;
  }
  .item.focused:not(.disabled) {
    background: rgba(0, 212, 170, 0.12);
    color: var(--accent);
  }
  .item.disabled {
    color: var(--muted);
    cursor: not-allowed;
  }
</style>
