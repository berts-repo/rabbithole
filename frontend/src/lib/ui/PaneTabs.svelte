<script lang="ts">
  // Shared tab strip primitive.
  //
  // Implements role="tablist" + role="tab" + full arrow-key navigation:
  //   ArrowLeft / ArrowRight — cycle through tabs (wraps at ends).
  //   Home / End              — jump to first / last tab.
  //
  // Props:
  //   tabs      — array of { id: string, label: string }
  //   active    — id of the currently active tab
  //   onSelect  — callback invoked with the new tab id on selection
  //   ariaLabel — accessible label for the tablist (defaults to 'Tabs')
  //
  // Usage:
  //   <PaneTabs {tabs} {active} onSelect={(id) => (activeTab = id)} />

  interface Tab {
    id: string;
    label: string;
    // Optional count chip after the label. Falsy values (0, undefined) are
    // not rendered — callers pass `count || undefined` to hide empty badges.
    badge?: number;
  }

  interface Props {
    tabs: Tab[];
    active: string;
    onSelect: (id: string) => void;
    ariaLabel?: string;
  }

  const { tabs, active, onSelect, ariaLabel = 'Tabs' }: Props = $props();

  // Keep refs to each tab button so we can programmatically focus on
  // arrow-key navigation.
  let tabEls = $state<(HTMLButtonElement | null)[]>([]);

  function handleKeydown(e: KeyboardEvent, idx: number): void {
    const count = tabs.length;
    let next = -1;
    if (e.key === 'ArrowRight') {
      next = (idx + 1) % count;
    } else if (e.key === 'ArrowLeft') {
      next = (idx - 1 + count) % count;
    } else if (e.key === 'Home') {
      next = 0;
    } else if (e.key === 'End') {
      next = count - 1;
    }
    if (next >= 0) {
      e.preventDefault();
      onSelect(tabs[next].id);
      // Move DOM focus to the newly selected tab button.
      tabEls[next]?.focus();
    }
  }
</script>

<div
  role="tablist"
  aria-label={ariaLabel}
  class="pane-tabs"
>
  {#each tabs as tab, i (tab.id)}
    <button
      role="tab"
      type="button"
      class="tab"
      class:active={active === tab.id}
      aria-selected={active === tab.id}
      tabindex={active === tab.id ? 0 : -1}
      bind:this={tabEls[i]}
      onclick={() => onSelect(tab.id)}
      onkeydown={(e) => handleKeydown(e, i)}
    >
      {tab.label}{#if tab.badge}<span class="badge">{tab.badge}</span>{/if}
    </button>
  {/each}
</div>

<style>
  .pane-tabs {
    display: flex;
    align-items: flex-end;
    flex: 1;
    gap: 2px;
    padding: 0 4px;
    min-width: 0;
  }
  .tab {
    display: inline-flex;
    align-items: center;
    height: 26px;
    padding: 0 10px;
    background: transparent;
    border: 1px solid transparent;
    border-bottom: none;
    border-radius: 6px 6px 0 0;
    color: var(--muted);
    font: inherit;
    font-size: 11px;
    white-space: nowrap;
    cursor: pointer;
    outline: none;
  }
  .tab:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  .tab:hover {
    background: rgba(255, 255, 255, 0.03);
    color: var(--text);
  }
  .tab.active {
    background: var(--bg);
    border-color: var(--border);
    color: var(--accent);
    /* Overlap the parent's bottom border so active tab appears attached */
    margin-bottom: -1px;
    padding-bottom: 1px;
    z-index: 1;
  }
  .tab.active:hover {
    background: var(--bg);
    color: var(--accent);
  }
  .badge {
    margin-left: 6px;
    padding: 0 5px;
    border-radius: 8px;
    background: var(--border);
    color: var(--text);
    font-size: 10px;
    line-height: 15px;
    min-width: 15px;
    text-align: center;
  }
  .tab.active .badge {
    background: var(--accent);
    color: var(--bg);
  }
</style>
