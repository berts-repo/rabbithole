<script lang="ts">
  // Outbound Search tab — discover new .onion URLs by querying dark-web search
  // engines through Tor, results streaming in over SSE. Peer of the Graph tab
  // (a center tab), not a bottom-pane sub-tab. The inbound counterpart is the
  // left-pane Find sub-tab (recall over already-crawled data).
  //
  // Row click is highlight-only (CLAUDE.md selection model): a crawled row
  // highlights its graph node + opens the right Page tab; an uncrawled row has
  // no node yet, so it only marks the local row selection. All engine/probe
  // text is attacker-controlled and rendered as auto-escaped text — never via
  // Svelte's raw-HTML directive.
  //
  // Per-row actions live in the shared row right-click menu (the same menu
  // every bottom-pane sub-tab and the graph use). A crawled row carries its
  // node into the menu; an uncrawled row carries just its URL and the menu's
  // id-bound actions (Open in Tor, Flag, Queue Analysis, Add to Collection)
  // mint a stub node on demand. Each row keeps ONE inline button for the
  // primary verb — `→ Graph` once crawled, `Send to Crawl` before then.

  import { onMount, onDestroy } from 'svelte';
  import { Search } from 'lucide-svelte';
  import {
    searchHarvest,
    sourceBadge,
    type SearchResult,
  } from '$lib/stores/searchHarvest.svelte';
  import { EmptyState, TextButton } from '$lib/ui';
  import { workspaceStore } from '$lib/stores/workspace.svelte';
  import { navigationStore } from '$lib/stores/navigation.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { actQueueCrawl, actAddAllToGraph } from '$lib/contextMenu/actions';
  import type { MenuCapability } from '$lib/contextMenu';
  import { rowContextMenu, type RowMenuTarget } from '$lib/contextMenu/rowMenu.svelte';

  let selectedUrl = $state<string | null>(null);

  // Which menu verbs a Search result offers. Both states share the URL-
  // based intake verbs — copy / open / crawl / bookmark / flag / monitor /
  // analysis / collection all act on a URL (minting a stub on demand).
  const BASE_CAPS: MenuCapability[] = [
    'copy',
    'openInTor',
    'crawl',
    'bookmark',
    'flag',
    'monitor',
    'analysis',
    'collection',
  ];
  // Uncrawled hit → also "Add to Graph" (pin it as an uncrawled node). The
  // graph- and content-bound verbs (Focus, Hide, Rename, Reviewed) don't
  // apply — there's no node yet.
  const INTAKE_CAPS: ReadonlySet<MenuCapability> = new Set([
    ...BASE_CAPS,
    'addToGraph',
  ]);
  // Crawled hit → already a node, so "Add to Graph" is moot; offer the
  // graph- and content-bound verbs instead.
  const CRAWLED_CAPS: ReadonlySet<MenuCapability> = new Set([
    ...BASE_CAPS,
    'rename',
    'review',
    'focus',
    'hide',
  ]);

  onMount(() => searchHarvest.init());
  // Stop any in-flight stream when the analyst navigates away — no background
  // Tor fan-out once the Search tab is unmounted. Results persist in the store.
  onDestroy(() => searchHarvest.stop());

  const empty = $derived(searchHarvest.emptyState());

  function onSubmit(e: Event): void {
    e.preventDefault();
    searchHarvest.start();
  }

  function onRowClick(r: SearchResult): void {
    selectedUrl = r.url;
    if (r.crawled && r.nodeId !== null) {
      selectionStore.highlight(r.nodeId);
      navigationStore.setRight('page');
    }
  }

  // Right-click → shared row menu. A crawled row hands its node over (looked
  // up in the loaded graph payload when present) plus its known id so id-
  // bound actions work even if the node isn't in the current payload. An
  // uncrawled row hands over just its URL; the menu mints a stub on demand.
  function onRowContextMenu(r: SearchResult, event: MouseEvent): void {
    const target: RowMenuTarget =
      r.crawled && r.nodeId !== null
        ? {
            url: r.url,
            node: graphStore.payload?.nodes.find((n) => n.id === r.nodeId),
            nodeId: r.nodeId,
            capabilities: CRAWLED_CAPS,
          }
        : { url: r.url, capabilities: INTAKE_CAPS };
    rowContextMenu.openAt(target, event);
  }

  // The single inline button per row. Crawled → jump to the node on the
  // graph; uncrawled → stage the URL in the Crawl tab.
  function toGraph(r: SearchResult): void {
    if (r.nodeId === null) return;
    workspaceStore.setCenter('explore');
    selectionStore.highlight(r.nodeId);
    navigationStore.setRight('page');
  }

  function sendToCrawl(r: SearchResult): void {
    actQueueCrawl(r.url);
  }

  // Uncrawled result URLs — the rows that aren't graph nodes yet. Backs the
  // page-level "Add all to Graph": pin every discovered onion at once.
  const uncrawledUrls = $derived(
    searchHarvest.results.filter((r) => !r.crawled).map((r) => r.url),
  );

  function fmtDate(iso: string | null): string {
    if (!iso) return '';
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString();
  }

  const EMPTY_COPY: Record<string, { title: string; body?: string; error?: boolean }> = {
    'no-engines': {
      title: 'No search engines set up.',
      body: 'Add one in Settings → Engines.',
    },
    before: {
      title: 'Enter a search query above to discover .onion sites via Tor.',
    },
    'no-results': { title: 'No results found.' },
    'failed-connection': {
      title: 'All sources failed — is Tor running?',
      error: true,
    },
    'failed-other': {
      title: 'All sources failed — search engines may be down or blocking Tor exits.',
      error: true,
    },
  };
</script>

<div class="search-tab">
  {#if searchHarvest.loadError}
    <EmptyState title="Couldn't load engines." body={searchHarvest.loadError} error />
  {:else if empty === 'no-engines'}
    <EmptyState
      title={EMPTY_COPY['no-engines'].title}
      body={EMPTY_COPY['no-engines'].body}
    />
  {:else}
    <form class="bar" onsubmit={onSubmit}>
      <input
        type="text"
        class="query"
        placeholder="Search the dark web…"
        value={searchHarvest.query}
        oninput={(e) => (searchHarvest.query = e.currentTarget.value)}
        disabled={searchHarvest.searching}
        aria-label="Search query"
      />
      {#if searchHarvest.searching}
        <button type="button" class="stop" onclick={() => searchHarvest.stop()}>
          Stop
        </button>
      {:else}
        <TextButton variant="primary" type="submit">
          {#snippet icon()}<Search size={13} />{/snippet}
          Search
        </TextButton>
      {/if}
    </form>

    <div class="sources">
      {#each searchHarvest.engines as engine (engine.id)}
        {@const badge = sourceBadge(searchHarvest.statusFor(engine.label))}
        <label class="pill" class:on={searchHarvest.selectedIds.has(engine.id)}>
          <input
            type="checkbox"
            checked={searchHarvest.selectedIds.has(engine.id)}
            disabled={searchHarvest.searching}
            onchange={() => searchHarvest.toggleEngine(engine.id)}
          />
          <span class="pill-label">{engine.label}</span>
          {#if badge}
            <span class="src-status {badge.tone}">{badge.label}</span>
          {/if}
        </label>
      {/each}

      <button
        type="button"
        class="pill passive"
        class:on={searchHarvest.passive}
        title="Stay on the configured engines — don't probe discovered onions for previews"
        onclick={() => void searchHarvest.setPassive(!searchHarvest.passive)}
      >
        <span class="pill-label">Passive</span>
      </button>

      {#if searchHarvest.searching}
        <span class="tor-label">searching via Tor…</span>
      {/if}

      {#if uncrawledUrls.length > 0}
        <button
          type="button"
          class="add-all"
          onclick={() => void actAddAllToGraph(uncrawledUrls)}
          disabled={searchHarvest.searching}
          title="Pin every uncrawled result as a graph node"
        >
          + Add all to Graph ({uncrawledUrls.length})
        </button>
      {/if}
    </div>

    {#if empty}
      <EmptyState
        title={EMPTY_COPY[empty].title}
        body={EMPTY_COPY[empty].body}
        error={EMPTY_COPY[empty].error}
      />
    {:else}
      <ul class="results">
        {#each searchHarvest.results as r (r.url)}
          <li
            class="result"
            class:crawled={r.crawled}
            class:active={selectedUrl === r.url}
            oncontextmenu={(e) => onRowContextMenu(r, e)}
          >
            <button type="button" class="main" onclick={() => onRowClick(r)}>
              <span class="line">
                <span class="source">{r.engineLabel}</span>
                {#if r.crawled}<span class="badge crawled-badge">crawled</span>{/if}
                <span class="url" title={r.url}>{r.url}</span>
                {#if r.title}<span class="title">— {r.title}</span>{/if}
              </span>
              {#if r.crawled}
                <span class="detail">
                  {#if r.category}<span class="cat">{r.category}</span>{/if}
                  {#if r.lastSeen}<span class="seen">last seen {fmtDate(r.lastSeen)}</span>{/if}
                </span>
              {:else if !r.probed}
                <span class="detail probing">probing…</span>
              {:else if r.description}
                <span class="detail">{r.description}</span>
              {/if}
            </button>

            <div class="actions">
              {#if r.crawled}
                <TextButton variant="ghost" size="small" onclick={() => toGraph(r)}>
                  → Graph
                </TextButton>
              {:else}
                <TextButton variant="ghost" size="small" onclick={() => sendToCrawl(r)}>
                  Send to Crawl
                </TextButton>
              {/if}
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  {/if}
</div>

<style>
  .search-tab {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 10px;
    overflow: hidden;
    box-sizing: border-box;
  }
  .bar {
    display: flex;
    gap: 6px;
    flex-shrink: 0;
  }
  .query {
    flex: 1 1 auto;
    background: #11150f;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 10px;
    font: inherit;
    font-size: 13px;
    border-radius: 3px;
  }
  .query:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .query:disabled {
    opacity: 0.6;
  }
  .stop {
    flex: 0 0 auto;
    background: #2a1416;
    border: 1px solid #ff5577;
    color: #ff8899;
    padding: 6px 14px;
    font: inherit;
    font-size: 12px;
    border-radius: 3px;
    cursor: pointer;
  }
  .stop:hover {
    background: #3a1a1d;
  }
  .sources {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 2px 8px;
    border: 1px solid var(--border);
    border-radius: 12px;
    font-size: 11px;
    color: var(--muted);
    cursor: pointer;
    background: transparent;
  }
  .pill.on {
    color: var(--text);
    border-color: var(--accent);
  }
  .pill input {
    cursor: pointer;
    margin: 0;
  }
  .pill.passive {
    font: inherit;
    font-size: 11px;
  }
  .pill.passive.on {
    background: rgba(0, 212, 170, 0.12);
  }
  .src-status {
    font-variant-numeric: tabular-nums;
    font-size: 10px;
  }
  .src-status.wait {
    color: var(--accent);
  }
  .src-status.good {
    color: var(--text);
  }
  .src-status.bad {
    color: #ff8899;
  }
  .tor-label {
    font-size: 11px;
    color: var(--muted);
    font-style: italic;
  }
  .add-all {
    margin-left: auto;
    flex-shrink: 0;
    background: transparent;
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 2px 10px;
    font: inherit;
    font-size: 11px;
    border-radius: 12px;
    cursor: pointer;
  }
  .add-all:hover {
    background: rgba(0, 212, 170, 0.12);
  }
  .add-all:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .results {
    list-style: none;
    margin: 0;
    padding: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-height: 0;
  }
  .result {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 5px 6px;
    border-left: 2px solid transparent;
  }
  .result.crawled {
    background: rgba(255, 255, 255, 0.025);
  }
  .result.active {
    border-left-color: var(--accent);
    background: rgba(0, 212, 170, 0.1);
  }
  .result:hover {
    background: rgba(255, 255, 255, 0.04);
  }
  .main {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
    background: transparent;
    border: none;
    color: var(--text);
    font: inherit;
    text-align: left;
    padding: 0;
    cursor: pointer;
  }
  .line {
    display: flex;
    align-items: baseline;
    gap: 6px;
    min-width: 0;
  }
  .source {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    flex-shrink: 0;
  }
  .badge {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 0 4px;
    border-radius: 3px;
    flex-shrink: 0;
  }
  .crawled-badge {
    background: rgba(91, 141, 239, 0.2);
    color: #8fb3ff;
  }
  .url {
    color: var(--accent);
    font-size: 11px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex-shrink: 1;
  }
  .title {
    color: var(--text);
    font-size: 11px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex-shrink: 1;
  }
  .detail {
    display: flex;
    gap: 8px;
    font-size: 11px;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .detail.probing {
    font-style: italic;
  }
  .cat {
    color: var(--accent);
    text-transform: uppercase;
    font-size: 9px;
    letter-spacing: 0.05em;
    align-self: center;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 2px;
    flex-shrink: 0;
  }
</style>
