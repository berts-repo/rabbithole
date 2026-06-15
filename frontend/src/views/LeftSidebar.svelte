<script lang="ts">
  import { ChevronLeft, ChevronRight } from 'lucide-svelte';
  import { navigationStore, type LeftTab } from '$lib/stores/navigation.svelte';
  import { layoutStore } from '$lib/stores/layout.svelte';
  import { IconButton } from '$lib/ui';
  import CrawlSidebar from '../components/CrawlSidebar.svelte';
  import FindTab from './left/FindTab.svelte';
  import IntelTab from './left/IntelTab.svelte';

  type Props = { onOpenSettings: () => void };
  const { onOpenSettings }: Props = $props();

  const tabs: { id: LeftTab; label: string }[] = [
    { id: 'find', label: 'Find' },
    { id: 'intel', label: 'Intel' },
    { id: 'crawl', label: 'Crawl' },
  ];
</script>

{#if layoutStore.leftCollapsed}
  <aside class="collapsed" aria-label="Left sidebar (collapsed)">
    <IconButton
      label="Expand left sidebar"
      variant="subtle"
      onclick={() => layoutStore.expandLeft()}
    >
      <ChevronRight size={14} />
    </IconButton>
    <span class="vlabel">Controls</span>
  </aside>
{:else}
  <aside class="sidebar">
    <header class="head">
      <nav class="tabs" aria-label="Left pane">
        {#each tabs as tab (tab.id)}
          <button
            type="button"
            class="tab"
            class:active={navigationStore.leftTab === tab.id}
            onclick={() => navigationStore.setLeft(tab.id)}
          >
            {tab.label}
          </button>
        {/each}
      </nav>
      <div class="collapse">
        <IconButton
          label="Collapse left sidebar"
          variant="subtle"
          onclick={() => layoutStore.collapseLeft()}
        >
          <ChevronLeft size={14} />
        </IconButton>
      </div>
    </header>
    <div class="body">
      {#if navigationStore.leftTab === 'crawl'}
        <CrawlSidebar {onOpenSettings} />
      {:else if navigationStore.leftTab === 'intel'}
        <IntelTab />
      {:else}
        <FindTab />
      {/if}
    </div>
  </aside>
{/if}

<style>
  .sidebar,
  .collapsed {
    display: flex;
    flex-direction: column;
    height: 100%;
    border-right: 1px solid var(--border);
    overflow: hidden;
  }
  .collapsed {
    align-items: center;
    padding: 6px 0;
    gap: 8px;
    width: 24px;
  }
  .vlabel {
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  .head {
    display: flex;
    align-items: flex-end;
    border-bottom: 1px solid var(--border);
    height: 30px;
  }
  .tabs {
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
    font-size: 11px;
    white-space: nowrap;
    cursor: pointer;
  }
  .tab:hover {
    background: rgba(255, 255, 255, 0.03);
    color: var(--text);
  }
  .tab.active {
    background: var(--bg);
    border-color: var(--border);
    color: var(--accent);
    margin-bottom: -1px;
    padding-bottom: 1px;
    z-index: 1;
  }
  .tab.active:hover {
    background: var(--bg);
    color: var(--accent);
  }
  .collapse {
    display: flex;
    align-items: center;
    padding: 0 6px 2px;
  }
  .body {
    flex: 1;
    padding: 12px;
    overflow: auto;
  }
</style>
