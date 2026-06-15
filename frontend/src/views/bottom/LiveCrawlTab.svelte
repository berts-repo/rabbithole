<script lang="ts">
  // Live Crawl sub-tab — Phase 2.1. Streams /api/crawl/log via the shared
  // crawlLogStore (SSE) and renders a 200-line ring buffer color-coded by
  // HTTP status.
  //
  // Selection model: rows with an extracted onion URL are clickable. If
  // the URL resolves to a node in graphStore.payload, we fullSelect it.
  // Otherwise a toast — the page may not have been parsed yet (the URL
  // first appears in the log before the node exists). Rows without a
  // URL are plain text.
  //
  // Subscription lifecycle: subscribe on mount, unsubscribe on destroy.
  // The store's ref-count keeps the EventSource open as long as any
  // consumer holds it; switching tabs and coming back replays the
  // backend's recent buffer so the analyst doesn't lose context.

  import { onMount } from 'svelte';
  import { Trash2 } from 'lucide-svelte';
  import { EmptyState, IconButton } from '$lib/ui';
  import type { GraphNode } from '$lib/api';
  import { crawlLogStore } from '$lib/stores/crawlLog.svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import {
    filterEntries,
    formatTime,
    type CrawlLogEntry,
  } from './liveCrawl';

  let filter = $state('');

  onMount(() => {
    const unsubscribe = crawlLogStore.subscribe();
    return () => unsubscribe();
  });

  const entries = $derived(crawlLogStore.entries);
  const filtered = $derived(filterEntries(entries as CrawlLogEntry[], filter));

  // raw_url → node lookup so a clickable log line can full-select the
  // corresponding node. Rebuilds whenever the payload changes.
  const nodeByUrl = $derived.by<Map<string, GraphNode>>(() => {
    const map = new Map<string, GraphNode>();
    const nodes = graphStore.payload?.nodes;
    if (!nodes) return map;
    for (const n of nodes) map.set(n.raw_url, n);
    return map;
  });

  // Active row marker — every log line whose URL resolves to the
  // currently full-selected node lights up, matching the active-row
  // behavior of the other bottom-pane sub-tabs. Highlight-mode
  // selections (graph click, search result) don't move the marker,
  // per the CLAUDE.md selection model.
  const activeNodeId = $derived(
    selectionStore.selectMode === 'full' ? selectionStore.selectedNodeId : null,
  );

  function onUrlClick(e: CrawlLogEntry): void {
    if (!e.url) return;
    const node = nodeByUrl.get(e.url);
    if (!node) {
      toastStore.show(
        'No graph node for this URL yet — page may still be parsing.',
        'info',
      );
      return;
    }
    selectionStore.fullSelect(node.id);
  }
</script>

<section class="live-crawl">
  <header class="head">
    <input
      type="text"
      class="filter"
      placeholder="Filter URL or message…"
      bind:value={filter}
      aria-label="Filter log lines"
    />
    <span class="count" title="Filtered / total (200 line buffer)">
      {filtered.length}{filtered.length === entries.length
        ? ''
        : ` / ${entries.length}`}
    </span>
    <IconButton label="Clear log" variant="ghost" size="small" onclick={() => crawlLogStore.clear()}>
      <Trash2 size={11} />
    </IconButton>
  </header>

  {#if entries.length === 0}
    <EmptyState title="No log entries yet." body="Start a crawl from the left pane to see live output here." />
  {:else if filtered.length === 0}
    <EmptyState title="No log lines match this filter." />
  {:else}
    <ul class="log">
      {#each filtered as e (e.localId)}
        {@const node = e.url ? nodeByUrl.get(e.url) : undefined}
        {@const active = node !== undefined && node.id === activeNodeId}
        <li class={`sev-${e.severity}`} class:active>
          <span class="ts">{formatTime(e.ts)}</span>
          {#if e.status !== null}
            <span class="status">{e.status}</span>
          {:else}
            <span class="status muted">—</span>
          {/if}
          {#if e.url}
            <button
              type="button"
              class="msg link"
              title="Select node"
              onclick={() => onUrlClick(e)}
            >{e.message}</button>
          {:else}
            <span class="msg" title={e.message}>{e.message}</span>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .live-crawl {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-height: 0;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .filter {
    flex: 1 1 auto;
    min-width: 0;
    background: #17191f;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 4px 7px;
    font-size: 11px;
  }
  .filter:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .count {
    color: var(--muted);
    font-size: 11px;
    padding: 0 4px;
  }
  .log {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 11px;
  }
  .log li {
    display: grid;
    grid-template-columns: 56px 36px 1fr;
    gap: 6px;
    padding: 1px 4px;
    align-items: baseline;
  }
  .log li:hover {
    background: rgba(0, 212, 170, 0.04);
  }
  .log li.active {
    background: rgba(0, 212, 170, 0.14);
  }
  .log li.active:hover {
    background: rgba(0, 212, 170, 0.18);
  }
  .ts {
    color: var(--muted);
  }
  .status {
    text-align: right;
    color: var(--text);
  }
  .status.muted {
    color: var(--muted);
  }
  .msg {
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .msg.link {
    background: transparent;
    border: none;
    padding: 0;
    text-align: left;
    font: inherit;
    cursor: pointer;
    color: var(--accent);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .msg.link:hover {
    text-decoration: underline;
  }
  .sev-ok .status {
    color: var(--accent);
  }
  .sev-warn .status,
  .sev-warn .msg {
    color: #ffb347;
  }
  .sev-error .status,
  .sev-error .msg {
    color: #ff5577;
  }
  .sev-info .status {
    color: var(--text);
  }
</style>
