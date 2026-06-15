<script lang="ts">
  // The bottom strip's "+" customise control: a trigger button plus a
  // checklist popover of every available tab. Checked = on the strip;
  // toggling calls workspaceStore.toggleTab.
  //
  // The popover opens upward over the graph. It must be `position: fixed`
  // (anchored to the measured trigger position) rather than absolutely
  // positioned, because the bottom pane is `overflow: hidden` and would clip
  // an upward popover that grew past its top edge. The panel stays a DOM
  // descendant of the trigger wrapper, so outside-click detection still works.
  import { Check, Plus } from 'lucide-svelte';
  import { workspaceStore, BOTTOM_TABS } from '$lib/stores/workspace.svelte';
  import { IconButton } from '$lib/ui';

  let open = $state(false);
  let rootEl = $state<HTMLDivElement>();
  // Viewport-relative anchor for the fixed popover: right edge aligned to the
  // trigger, bottom edge sitting just above it, height capped to the space
  // available above so a long list scrolls rather than overflowing the screen.
  let pos = $state({ right: 0, bottom: 0, maxHeight: 0 });

  // The strip must keep at least one tab, so the lone remaining tab's row is
  // disabled (it can't be unchecked).
  const lastOne = $derived(workspaceStore.visibleBottomTabs.length === 1);

  function measure(): void {
    if (!rootEl) return;
    const r = rootEl.getBoundingClientRect();
    pos = {
      right: Math.max(4, window.innerWidth - r.right),
      bottom: window.innerHeight - r.top + 4,
      maxHeight: Math.max(120, r.top - 8),
    };
  }

  function toggle(): void {
    if (!open) measure(); // measure before render so the panel never flashes at 0,0
    open = !open;
  }

  function close(): void {
    open = false;
  }

  $effect(() => {
    if (!open) return;
    function onPointerDown(e: PointerEvent): void {
      if (rootEl && e.target instanceof Node && !rootEl.contains(e.target)) close();
    }
    function onKey(e: KeyboardEvent): void {
      if (e.key === 'Escape') {
        e.preventDefault();
        close();
      }
    }
    document.addEventListener('pointerdown', onPointerDown, true);
    document.addEventListener('keydown', onKey, true);
    window.addEventListener('resize', measure);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown, true);
      document.removeEventListener('keydown', onKey, true);
      window.removeEventListener('resize', measure);
    };
  });
</script>

<div class="wrap" bind:this={rootEl}>
  <IconButton label="Customize tabs" variant="subtle" expanded={open} onclick={toggle}>
    <Plus size={14} />
  </IconButton>

  {#if open}
    <div
      class="menu"
      role="menu"
      aria-label="Customize tabs"
      style:right="{pos.right}px"
      style:bottom="{pos.bottom}px"
      style:max-height="{pos.maxHeight}px"
    >
      <div class="hint">Tabs on the strip</div>
      {#each BOTTOM_TABS as tab (tab.id)}
        {@const on = workspaceStore.isTabVisible(tab.id)}
        <button
          type="button"
          role="menuitemcheckbox"
          aria-checked={on}
          class="item"
          class:on
          disabled={on && lastOne}
          title={on && lastOne ? 'At least one tab must stay on the strip' : ''}
          onclick={() => workspaceStore.toggleTab(tab.id)}
        >
          <span class="box" aria-hidden="true">
            {#if on}<Check size={12} />{/if}
          </span>
          {tab.label}
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .wrap {
    position: relative;
    display: flex;
    align-items: center;
  }
  .menu {
    position: fixed;
    z-index: 40;
    min-width: 180px;
    overflow-y: auto;
    background: rgba(10, 15, 13, 0.97);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 4px 0;
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.45);
    font-size: 11px;
    color: var(--text);
    user-select: none;
  }
  .hint {
    padding: 4px 12px 6px;
    font-size: 9px;
    color: var(--muted);
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    text-align: left;
    padding: 5px 12px;
    background: transparent;
    border: none;
    color: var(--muted);
    font: inherit;
    cursor: pointer;
  }
  .item:hover:not(:disabled) {
    background: rgba(0, 212, 170, 0.12);
    color: var(--text);
  }
  .item.on {
    color: var(--text);
  }
  .item:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }
  .box {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 14px;
    height: 14px;
    border: 1px solid var(--border);
    border-radius: 3px;
    color: var(--accent);
    flex-shrink: 0;
  }
  .item.on .box {
    border-color: var(--accent);
  }
</style>
