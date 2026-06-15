<script lang="ts">
  // Toolbar above the canvas — the status line plus graph controls:
  // layout picker, draw-edge, expand-to-collection, fit, filter, export,
  // reset. Contextual extras: Resume (kill-switch cleared_idle), Stop
  // (FA2 settling), and the draw-edge instruction line.

  import {
    Maximize2,
    RotateCcw,
    Filter,
    Play,
    Square,
    Spline,
    FolderPlus,
    Download,
  } from 'lucide-svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { graphFiltersStore } from '$lib/stores/graphFilters.svelte';
  import { graphLayoutStore } from '$lib/stores/graphLayout.svelte';
  import { drawEdgeStore } from '$lib/stores/drawEdge.svelte';
  import {
    LAYOUT_KINDS,
    LAYOUT_LABELS,
    type LayoutKind,
  } from '$lib/graph/layouts';
  import { expandByHops } from '$lib/graph/expand';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { crawlStore } from '$lib/stores/crawl.svelte';
  import { servicesStore } from '$lib/stores/services.svelte';
  import { workspaceStore } from '$lib/stores/workspace.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import {
    addItemsToCollection,
    listCollections,
    EXPORT_GEXF_PATH,
    EXPORT_NODES_CSV_PATH,
  } from '$lib/api';
  import FilterShelf from './FilterShelf.svelte';
  import CollectionPicker from '../CollectionPicker.svelte';

  interface Props {
    onFit: () => void;
    onReset: () => void;
  }

  let { onFit, onReset }: Props = $props();

  let filterShelfOpen = $state(false);

  // Export / Expand popovers — one open at a time, both anchored in the
  // shared menu wrap so a single outside-click listener dismisses them.
  let openMenu = $state<'none' | 'export' | 'expand'>('none');
  let menuWrapEl = $state<HTMLDivElement>();
  let expandCollectionId = $state<number | null>(null);
  let expandHops = $state(1);
  let expandBusy = $state(false);

  const canExpand = $derived(selectionStore.multiCount >= 1);

  $effect(() => {
    if (openMenu === 'none') return;
    const onDocClick = (e: MouseEvent): void => {
      if (menuWrapEl && !menuWrapEl.contains(e.target as Node)) {
        openMenu = 'none';
      }
    };
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') openMenu = 'none';
    };
    document.addEventListener('click', onDocClick, true);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('click', onDocClick, true);
      document.removeEventListener('keydown', onKey);
    };
  });

  // Opening the Expand popover pre-fills the collection with the active
  // workspace's collection (spec: explore-graph.md:66), if one is open.
  function toggleExpand(): void {
    if (openMenu === 'expand') {
      openMenu = 'none';
      return;
    }
    if (expandCollectionId === null) {
      expandCollectionId = workspaceStore.activeCollectionId();
    }
    openMenu = 'expand';
  }

  // Expand: BFS the in-memory graph N hops out from the selection, then
  // bulk-add the reachable node set to the chosen collection.
  async function doExpand(): Promise<void> {
    if (expandCollectionId === null || expandBusy) return;
    expandBusy = true;
    try {
      const seeds = [...selectionStore.selectedIds];
      const ids = expandByHops(graphStore.graph(), seeds, expandHops);
      const res = await addItemsToCollection(expandCollectionId, ids);
      toastStore.show(
        `Added ${res.added} node(s) to collection — within ` +
          `${expandHops} hop${expandHops > 1 ? 's' : ''} of ${seeds.length} selected`,
      );
      openMenu = 'none';
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Expand failed: ${msg}`, 'error');
    } finally {
      expandBusy = false;
    }
  }

  function pad(n: number): string {
    return n < 10 ? `0${n}` : String(n);
  }

  const timeLabel = $derived.by(() => {
    const t = graphStore.lastUpdated;
    if (!t) return '—';
    const d = new Date(t);
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  });

  const multi = $derived(selectionStore.multiCount);

  // Status dot precedence: a running crawl is the most meaningful signal,
  // so it beats an in-flight fetch. Fetch beats idle.
  const dotState = $derived<'idle' | 'fetch' | 'crawl'>(
    crawlStore.running ? 'crawl' : graphStore.loading ? 'fetch' : 'idle',
  );

  // Inline re-arm affordance when the kill switch is sitting in
  // cleared_idle. Pollers and SSE stay paused until the analyst clicks.
  const showResume = $derived(
    servicesStore.killSwitch.phase === 'cleared_idle',
  );

  // Render the active workspace label next to the dot when we are
  // scoped to a collection (not the Global tab).
  const scopeLabel = $derived(
    workspaceStore.activeWorkspaceId === 'global'
      ? null
      : workspaceStore.activeLabel(),
  );

  // Fallback name cache for the chip when the collection tab isn't open.
  // Populated by a one-shot fetch the first time we see an unknown cid.
  let collectionNameCache = $state<Record<number, string>>({});

  $effect(() => {
    const cid = crawlStore.polledActiveRow?.collection_id ?? null;
    if (cid === null) return;
    if (workspaceStore.openTabs.some((t) => t.collectionId === cid)) return;
    if (collectionNameCache[cid] !== undefined) return;
    listCollections().then((res) => {
      const next: Record<number, string> = {};
      for (const c of res.collections) next[c.id] = c.name;
      collectionNameCache = { ...collectionNameCache, ...next };
    }).catch(() => {});
  });

  // "crawling → {label}" affordance — only shown on Global while a crawl
  // is running into a specific collection. Clicking opens/activates the
  // collection's workspace tab.
  const targetedChip = $derived.by<{ collectionId: number; label: string } | null>(
    () => {
      if (workspaceStore.activeWorkspaceId !== 'global') return null;
      const row = crawlStore.polledActiveRow;
      const cid = row?.collection_id ?? null;
      if (cid === null) return null;
      const tab = workspaceStore.openTabs.find((t) => t.collectionId === cid);
      return { collectionId: cid, label: tab?.label ?? collectionNameCache[cid] ?? `Collection ${cid}` };
    },
  );
</script>

<div class="bar" role="toolbar" aria-label="Graph toolbar">
  <div class="status" aria-live="polite">
    {#if drawEdgeStore.active}
      <span class="dot draw"></span>
      <span class="text">
        {drawEdgeStore.source
          ? 'Click destination node'
          : 'Click source node'}
      </span>
      <button
        type="button"
        class="chip"
        onclick={() => drawEdgeStore.cancel()}>Cancel</button
      >
    {:else if multi >= 2}
      <span class="dot multi"></span>
      <span class="text">{multi} nodes selected</span>
    {:else}
      <span
        class="dot"
        class:fetch={dotState === 'fetch'}
        class:crawl={dotState === 'crawl'}
      ></span>
      {#if scopeLabel}
        <span class="scope">{scopeLabel}</span>
        <span class="text">·</span>
      {/if}
      <span class="text">
        updated {timeLabel} · {graphStore.visibleNodeCount} nodes · {graphStore.visibleEdgeCount} edges
        · {graphStore.scopeDomains} domains · {graphStore.scopePages} pages
      </span>
      {#if graphStore.error}
        <span class="err">· {graphStore.error}</span>
      {/if}
      {#if targetedChip}
        <button
          type="button"
          class="chip"
          onclick={() =>
            void workspaceStore.openCollectionTabById(targetedChip.collectionId)}
          title="Open this collection's workspace"
        >
          crawling → {targetedChip.label}
        </button>
      {/if}
    {/if}
  </div>

  <div class="actions">
    {#if showResume}
      <button
        type="button"
        class="resume"
        onclick={() => servicesStore.armKillSwitch()}
        title="Tor recovered — click to re-arm the kill switch and resume polling"
      >
        <Play size={12} aria-hidden="true" />
        Resume
      </button>
    {/if}

    {#if graphLayoutStore.settling}
      <button
        type="button"
        class="settle-stop"
        onclick={() => graphLayoutStore.requestStop()}
        title="Freeze the Force layout where it is now"
      >
        <Square size={9} aria-hidden="true" />
        Stop
      </button>
    {/if}

    <select
      class="layout-select"
      aria-label="Graph layout"
      title="Graph layout"
      value={graphLayoutStore.kind}
      onchange={(e) =>
        graphLayoutStore.setKind(e.currentTarget.value as LayoutKind)}
    >
      {#each LAYOUT_KINDS as kind (kind)}
        <option value={kind}>{LAYOUT_LABELS[kind]}</option>
      {/each}
    </select>

    <button
      type="button"
      class="btn"
      class:active={drawEdgeStore.active}
      onclick={() => drawEdgeStore.request()}
      aria-label="Draw analyst edge"
      title="Draw analyst edge"
    >
      <Spline size={14} />
    </button>

    <div class="menus" bind:this={menuWrapEl}>
      <button
        type="button"
        class="btn"
        class:active={openMenu === 'expand'}
        disabled={!canExpand}
        onclick={toggleExpand}
        aria-label="Expand selection to a collection"
        title={canExpand
          ? 'Expand selection to a collection'
          : 'Select at least one node first'}
      >
        <FolderPlus size={14} />
      </button>

      <button
        type="button"
        class="btn"
        class:active={openMenu === 'export'}
        onclick={() => (openMenu = openMenu === 'export' ? 'none' : 'export')}
        aria-label="Export graph"
        title="Export graph"
      >
        <Download size={14} />
      </button>

      {#if openMenu === 'expand'}
        <div class="popover" role="dialog" aria-label="Expand to collection">
          <p class="pv-head">Expand to collection</p>
          <label class="pv-row">
            <span>Collection</span>
            <CollectionPicker
              value={expandCollectionId}
              onChange={(id) => (expandCollectionId = id)}
            />
          </label>
          <div class="pv-row">
            <span>Hops</span>
            <div class="hops">
              {#each [1, 2, 3] as h (h)}
                <button
                  type="button"
                  class="hop"
                  class:on={expandHops === h}
                  onclick={() => (expandHops = h)}>{h}</button
                >
              {/each}
            </div>
          </div>
          <button
            type="button"
            class="pv-go"
            disabled={expandCollectionId === null || expandBusy}
            onclick={() => void doExpand()}
          >
            {expandBusy ? 'Adding…' : 'Add to collection'}
          </button>
        </div>
      {:else if openMenu === 'export'}
        <div class="popover export" role="menu" aria-label="Export graph">
          <a
            class="pv-item"
            role="menuitem"
            href={EXPORT_GEXF_PATH}
            download
            onclick={() => (openMenu = 'none')}>GEXF (.gexf)</a
          >
          <a
            class="pv-item"
            role="menuitem"
            href={EXPORT_NODES_CSV_PATH}
            download
            onclick={() => (openMenu = 'none')}>Nodes CSV (.csv)</a
          >
        </div>
      {/if}
    </div>

    <button
      type="button"
      class="btn"
      onclick={onFit}
      aria-label="Fit graph to viewport"
      title="Fit"
    >
      <Maximize2 size={14} />
    </button>

    <div class="filter-wrap">
      <button
        type="button"
        class="btn"
        class:active={filterShelfOpen || graphFiltersStore.hasActiveFilters}
        onclick={() => (filterShelfOpen = !filterShelfOpen)}
        aria-label="Open filter shelf"
        aria-expanded={filterShelfOpen}
        title={graphFiltersStore.hasActiveFilters
          ? 'Filters active — click to adjust'
          : 'Filter the rendered graph (no refetch)'}
      >
        <Filter size={14} />
      </button>
      {#if filterShelfOpen}
        <FilterShelf onClose={() => (filterShelfOpen = false)} />
      {/if}
    </div>

    <button
      type="button"
      class="btn"
      onclick={onReset}
      aria-label="Reset layout"
      title="Reset layout"
    >
      <RotateCcw size={14} />
    </button>
  </div>
</div>

<style>
  .bar {
    height: 34px;
    flex: 0 0 34px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 0 12px;
    border-bottom: 1px solid var(--border);
    background: var(--bg);
  }
  .status {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--muted);
    font-size: 11px;
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .text {
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .err {
    color: #ff7676;
  }
  .scope {
    color: var(--accent);
  }
  .chip {
    background: transparent;
    border: 1px solid var(--accent);
    color: var(--accent);
    border-radius: 10px;
    font-size: 10px;
    padding: 1px 8px;
    cursor: pointer;
    white-space: nowrap;
    line-height: 16px;
  }
  .chip:hover {
    background: var(--accent-bg-subtle, rgba(0, 212, 170, 0.12));
  }
  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent);
    flex: 0 0 auto;
  }
  .dot.fetch {
    animation: pulse 1.2s ease-in-out infinite;
  }
  .dot.crawl {
    background: var(--warn);
    animation: pulse 1.2s ease-in-out infinite;
  }
  .dot.multi {
    background: #ffb852;
  }
  .dot.draw {
    background: var(--accent);
    animation: pulse 1.2s ease-in-out infinite;
  }
  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.3;
    }
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .filter-wrap {
    position: relative;
    display: inline-flex;
  }
  .btn {
    background: transparent;
    border: 1px solid transparent;
    color: var(--muted);
    cursor: pointer;
    padding: 4px;
    border-radius: 2px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .btn:hover {
    color: var(--accent);
    border-color: var(--border);
  }
  .btn.active {
    color: var(--accent);
    border-color: var(--border);
    background: var(--accent-bg-subtle);
  }
  .btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }
  .btn:disabled:hover {
    color: var(--muted);
    border-color: transparent;
  }
  .menus {
    position: relative;
    display: inline-flex;
    gap: 4px;
  }
  .popover {
    position: absolute;
    top: calc(100% + 4px);
    right: 0;
    z-index: 50;
    min-width: 220px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 10px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
  }
  .popover.export {
    min-width: 160px;
    gap: 2px;
    padding: 4px;
  }
  .pv-head {
    margin: 0;
    font-size: 11px;
    color: var(--muted);
  }
  .pv-row {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .pv-row > span {
    font-size: 11px;
    color: var(--muted);
  }
  .hops {
    display: flex;
    gap: 4px;
  }
  .hop {
    flex: 1;
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    border-radius: 3px;
    padding: 3px 0;
    font-size: 12px;
    cursor: pointer;
  }
  .hop.on {
    color: var(--bg);
    background: var(--accent);
    border-color: var(--accent);
  }
  .pv-go {
    background: var(--accent);
    border: 1px solid var(--accent);
    color: var(--bg);
    font-size: 12px;
    font-weight: 600;
    padding: 5px 0;
    border-radius: 3px;
    cursor: pointer;
  }
  .pv-go:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .pv-item {
    display: block;
    padding: 6px 10px;
    font-size: 12px;
    color: var(--text);
    border-radius: 3px;
  }
  .pv-item:hover {
    background: var(--accent-bg-subtle);
    color: var(--accent);
    text-decoration: none;
  }
  .resume {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: transparent;
    border: 1px solid var(--warn);
    color: var(--warn);
    padding: 2px 8px;
    border-radius: 2px;
    font-size: 11px;
    cursor: pointer;
  }
  .resume:hover {
    background: var(--warn);
    color: var(--bg);
  }
  .layout-select {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--muted);
    font-size: 11px;
    padding: 2px 4px;
    border-radius: 2px;
    cursor: pointer;
  }
  .layout-select:hover {
    color: var(--accent);
    border-color: var(--accent);
  }
  .layout-select:focus-visible {
    outline: 1px solid var(--accent);
  }
  .settle-stop {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: var(--accent-bg-subtle);
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 2px 8px;
    border-radius: 2px;
    font-size: 11px;
    cursor: pointer;
  }
  .settle-stop:hover {
    background: var(--accent);
    color: var(--bg);
  }
</style>
