<script lang="ts">
  // The app's Settings modal (item 8). Replaces SettingsStubModal — the
  // single discoverable home for project configuration (gear icon in
  // AppHeader / LeftSidebar). Wide left-rail layout: a vertical tab list
  // selects the active section, rendered on the right.
  //
  // Save model: every control autosaves on change via the per-key
  // PUT /api/settings/<key> seam (or the dedicated CRUD route for the
  // Engines / Watchlist list tabs). There is no Save button and no dirty
  // state — closing the modal never discards anything.
  //
  // Wave 1 shipped Graph/Labels/Engines/Watchlist/Browser/Embedding. Wave 2
  // Slice 1 added Tor/Privacy, Crawl & Queue, and LLM/Ollama (surfacing keys
  // that already have live consumers); Slice 2 added Retention (job-history
  // only — its own pruning enforcement in db.jobs.prune_terminal_jobs).

  import { X } from 'lucide-svelte';
  import GraphTab from './settings/GraphTab.svelte';
  import LabelsTab from './settings/LabelsTab.svelte';
  import EnginesTab from './settings/EnginesTab.svelte';
  import WatchlistTab from './settings/WatchlistTab.svelte';
  import TorPrivacyTab from './settings/TorPrivacyTab.svelte';
  import CrawlQueueTab from './settings/CrawlQueueTab.svelte';
  import BrowserTab from './settings/BrowserTab.svelte';
  import LlmOllamaTab from './settings/LlmOllamaTab.svelte';
  import EmbeddingTab from './settings/EmbeddingTab.svelte';
  import RetentionTab from './settings/RetentionTab.svelte';

  type Props = { onClose: () => void };
  const { onClose }: Props = $props();

  type TabId =
    | 'graph'
    | 'labels'
    | 'engines'
    | 'watchlist'
    | 'tor'
    | 'crawl'
    | 'browser'
    | 'llm'
    | 'embedding'
    | 'retention';

  const TABS: ReadonlyArray<{ id: TabId; label: string }> = [
    { id: 'graph', label: 'Graph' },
    { id: 'labels', label: 'Labels' },
    { id: 'engines', label: 'Engines' },
    { id: 'watchlist', label: 'Watchlist' },
    { id: 'tor', label: 'Tor / Privacy' },
    { id: 'crawl', label: 'Crawl & Queue' },
    { id: 'browser', label: 'Browser' },
    { id: 'llm', label: 'LLM / Ollama' },
    { id: 'embedding', label: 'Embedding' },
    { id: 'retention', label: 'Retention' },
  ];

  let active = $state<TabId>('graph');

  // Rail buttons get refs so arrow keys can move DOM focus, matching the
  // PaneTabs keyboard model but on a vertical axis.
  let railEls = $state<(HTMLButtonElement | null)[]>([]);

  function onRailKey(e: KeyboardEvent, idx: number): void {
    const n = TABS.length;
    let next = -1;
    if (e.key === 'ArrowDown') next = (idx + 1) % n;
    else if (e.key === 'ArrowUp') next = (idx - 1 + n) % n;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = n - 1;
    if (next >= 0) {
      e.preventDefault();
      active = TABS[next].id;
      railEls[next]?.focus();
    }
  }

  function onKey(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onClose();
    }
  }
</script>

<svelte:window onkeydown={onKey} />

<div
  class="backdrop"
  role="presentation"
  onclick={(e) => {
    if (e.target === e.currentTarget) onClose();
  }}
>
  <div class="modal" role="dialog" aria-modal="true" aria-label="Settings">
    <header>
      <h2>Settings</h2>
      <button type="button" class="x" aria-label="Close" onclick={onClose}>
        <X size={15} />
      </button>
    </header>

    <div class="body">
      <div class="rail" role="tablist" aria-label="Settings sections" aria-orientation="vertical">
        {#each TABS as tab, i (tab.id)}
          <button
            role="tab"
            type="button"
            class="rail-tab"
            class:active={active === tab.id}
            aria-selected={active === tab.id}
            tabindex={active === tab.id ? 0 : -1}
            bind:this={railEls[i]}
            onclick={() => (active = tab.id)}
            onkeydown={(e) => onRailKey(e, i)}
          >
            {tab.label}
          </button>
        {/each}
      </div>

      <div class="content" role="tabpanel" aria-label={active}>
        {#if active === 'graph'}
          <GraphTab />
        {:else if active === 'labels'}
          <LabelsTab />
        {:else if active === 'engines'}
          <EnginesTab />
        {:else if active === 'watchlist'}
          <WatchlistTab />
        {:else if active === 'tor'}
          <TorPrivacyTab />
        {:else if active === 'crawl'}
          <CrawlQueueTab />
        {:else if active === 'browser'}
          <BrowserTab />
        {:else if active === 'llm'}
          <LlmOllamaTab />
        {:else if active === 'embedding'}
          <EmbeddingTab />
        {:else if active === 'retention'}
          <RetentionTab />
        {/if}
      </div>
    </div>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 950;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.55);
  }
  .modal {
    width: min(880px, calc(100vw - 32px));
    height: min(640px, calc(100vh - 64px));
    display: flex;
    flex-direction: column;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
    flex: 0 0 auto;
  }
  h2 {
    margin: 0;
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
  }
  .x {
    background: transparent;
    border: none;
    color: var(--muted);
    cursor: pointer;
    display: inline-flex;
    padding: 2px;
  }
  .x:hover {
    color: var(--accent);
  }
  .body {
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
  }
  .rail {
    flex: 0 0 160px;
    display: flex;
    flex-direction: column;
    gap: 1px;
    padding: 8px;
    border-right: 1px solid var(--border);
    overflow-y: auto;
  }
  .rail-tab {
    text-align: left;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    color: var(--muted);
    font: inherit;
    font-size: 12px;
    padding: 6px 10px;
    cursor: pointer;
    outline: none;
  }
  .rail-tab:hover {
    background: rgba(255, 255, 255, 0.03);
    color: var(--text);
  }
  .rail-tab:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }
  .rail-tab.active {
    background: rgba(0, 212, 170, 0.1);
    border-color: var(--border);
    color: var(--accent);
  }
  .content {
    flex: 1 1 auto;
    min-width: 0;
    overflow-y: auto;
    padding: 14px 16px;
  }
</style>
