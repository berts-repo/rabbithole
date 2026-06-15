<script lang="ts">
  // Find results (bottom pane). Renders the findStore result set for the
  // active mode. Clicking a row is HIGHLIGHT-ONLY per the CLAUDE.md selection
  // model — graph highlight + right panel, never the bottom active row — so
  // the analyst can look something up without losing their place. Right-click
  // opens the shared bottom-pane menu (URL/node actions).
  import { navigationStore } from '$lib/stores/navigation.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { findStore } from '$lib/stores/find.svelte';
  import type { GraphNode } from '$lib/api';
  import { rowContextMenu } from '$lib/contextMenu/rowMenu.svelte';
  import { parseSnippet, resultKey } from './findResults';

  // node_id → GraphNode, for the right-click menu's id-bound actions. A result
  // may not be in the current graph payload; then the menu falls back to its
  // URL-only items.
  const nodeById = $derived.by<Map<number, GraphNode>>(() => {
    const map = new Map<number, GraphNode>();
    for (const n of graphStore.payload?.nodes ?? []) map.set(n.id, n);
    return map;
  });

  function isActive(nodeId: number): boolean {
    return (
      selectionStore.selectMode === 'highlight' &&
      selectionStore.selectedNodeId === nodeId
    );
  }

  function onSelect(nodeId: number): void {
    selectionStore.highlight(nodeId);
    navigationStore.setRight('page');
  }

  function onContextMenu(url: string, nodeId: number, event: MouseEvent): void {
    rowContextMenu.openAt(
      { url, node: nodeById.get(nodeId), inCollection: false },
      event,
    );
  }
</script>

<section class="find-results">
  {#if findStore.error}
    <p class="empty error">{findStore.error}</p>
  {:else if findStore.mode === 'keyword'}
    {#if findStore.keywordResults.length === 0}
      <p class="empty">{findStore.ran ? 'No results.' : 'Type to search crawled data.'}</p>
    {:else}
      <ul class="list">
        {#each findStore.keywordResults as r, i (resultKey(r, i))}
          <li>
            <button
              type="button"
              class="row"
              class:active={isActive(r.node_id)}
              onclick={() => onSelect(r.node_id)}
              oncontextmenu={(e) => onContextMenu(r.url, r.node_id, e)}
            >
              <span class="line">
                <span class="type">{r.type}</span>
                <span class="url" title={r.url}>{r.url}</span>
                {#if r.type === 'page' && r.title}
                  <span class="title">{r.title}</span>
                {/if}
              </span>
              {#if r.type === 'page'}
                <span class="snippet">
                  {#each parseSnippet(r.snippet) as seg}{#if seg.mark}<mark>{seg.text}</mark>{:else}{seg.text}{/if}{/each}
                </span>
              {:else if r.type === 'entity'}
                <span class="snippet">
                  {#if r.entity_type}<span class="etype">{r.entity_type}</span>{/if}
                  {r.value}
                </span>
              {:else}
                <span class="snippet">{r.snippet}</span>
              {/if}
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  {:else if findStore.embedUnavailable}
    <p class="empty">
      Semantic search is unavailable — start the embedding service in Settings →
      Embedding.
    </p>
  {:else if findStore.semanticResults.length === 0}
    <p class="empty">{findStore.ran ? 'No semantic matches.' : 'Type to search crawled data.'}</p>
  {:else}
    <ul class="list">
      {#each findStore.semanticResults as r, i (`${r.node_id}:${i}`)}
        <li>
          <button
            type="button"
            class="row"
            class:active={isActive(r.node_id)}
            onclick={() => onSelect(r.node_id)}
            oncontextmenu={(e) => onContextMenu(r.url, r.node_id, e)}
          >
            <span class="line">
              <span class="score" title="Similarity (0–1, higher = closer)">
                {r.score.toFixed(3)}
              </span>
              <span class="url" title={r.url}>{r.url}</span>
              {#if r.title}<span class="title">{r.title}</span>{/if}
            </span>
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .find-results {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .empty {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
    padding: 6px 4px;
  }
  .empty.error {
    color: #ff8899;
  }
  .list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .row {
    display: flex;
    flex-direction: column;
    gap: 2px;
    width: 100%;
    text-align: left;
    background: transparent;
    border: none;
    border-left: 2px solid transparent;
    color: var(--text);
    font: inherit;
    padding: 4px 8px;
    cursor: pointer;
  }
  .row:hover {
    background: rgba(255, 255, 255, 0.03);
  }
  .row.active {
    background: rgba(0, 212, 170, 0.1);
    border-left-color: var(--accent);
  }
  .line {
    display: flex;
    align-items: baseline;
    gap: 6px;
    min-width: 0;
  }
  .type {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    flex-shrink: 0;
  }
  .score {
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    color: var(--accent);
    flex-shrink: 0;
  }
  .url {
    color: var(--accent);
    font-size: 11px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .title {
    color: var(--text);
    font-size: 11px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex-shrink: 1;
  }
  .snippet {
    font-size: 11px;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .snippet :global(mark) {
    background: rgba(0, 212, 170, 0.25);
    color: var(--text);
    border-radius: 2px;
  }
  .etype {
    text-transform: uppercase;
    font-size: 9px;
    letter-spacing: 0.05em;
    color: var(--accent);
    margin-right: 4px;
  }
</style>
