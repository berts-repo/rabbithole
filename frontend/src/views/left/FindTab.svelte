<script lang="ts">
  // Find composer (left pane). A debounced lookup over already-crawled data;
  // results render in the bottom-pane `find` tab. The composer owns only the
  // query + mode controls — findStore owns the debounce, the search call, and
  // the results, so state survives switching away from this sub-tab.
  import { onMount } from 'svelte';
  import { X } from 'lucide-svelte';
  import { findStore, type FindMode } from '$lib/stores/find.svelte';
  import LabelBrowser from './LabelBrowser.svelte';

  // Drain a "Send to Find" query staged by another surface (entity row,
  // bottom-pane "Send to Find", etc.) and run it.
  onMount(() => findStore.drainPending());

  const MODES: { id: FindMode; label: string }[] = [
    { id: 'keyword', label: 'Keyword' },
    { id: 'semantic', label: 'Semantic' },
  ];
</script>

<section class="find">
  <div class="input-wrap">
    <input
      type="text"
      class="input"
      placeholder="Find in crawled data…"
      value={findStore.query}
      oninput={(e) => findStore.setQuery(e.currentTarget.value)}
      aria-label="Find in crawled data"
    />
    {#if findStore.query}
      <button
        type="button"
        class="clear"
        aria-label="Clear find"
        title="Clear"
        onclick={() => findStore.clear()}
      >
        <X size={12} />
      </button>
    {/if}
  </div>

  <div class="modes" role="group" aria-label="Find mode">
    {#each MODES as m (m.id)}
      <button
        type="button"
        class="mode"
        class:active={findStore.mode === m.id}
        aria-pressed={findStore.mode === m.id}
        onclick={() => findStore.setMode(m.id)}
      >
        {m.label}
      </button>
    {/each}
  </div>

  {#if findStore.loading}
    <p class="hint">Searching…</p>
  {:else}
    <p class="hint muted">
      Results appear in the bottom <strong>Find</strong> tab.
    </p>
  {/if}

  <LabelBrowser />
</section>

<style>
  .find {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 10px;
  }
  .input-wrap {
    position: relative;
    display: flex;
    align-items: center;
  }
  .input {
    flex: 1;
    min-width: 0;
    background: #17191f;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 26px 6px 8px;
    font-size: 12px;
  }
  .input:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .clear {
    position: absolute;
    right: 4px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    color: var(--muted);
    cursor: pointer;
    padding: 2px;
    border-radius: 2px;
  }
  .clear:hover {
    color: var(--accent);
  }
  .modes {
    display: flex;
    gap: 4px;
  }
  .mode {
    flex: 1;
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 5px 0;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    cursor: pointer;
    border-radius: 3px;
  }
  .mode:hover {
    color: var(--text);
  }
  .mode.active {
    color: var(--accent);
    border-color: var(--accent);
    background: rgba(0, 212, 170, 0.12);
  }
  .hint {
    margin: 0;
    font-size: 11px;
    color: var(--text);
  }
  .hint.muted {
    color: var(--muted);
  }
</style>
