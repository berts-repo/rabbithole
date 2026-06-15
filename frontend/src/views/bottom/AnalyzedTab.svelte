<script lang="ts">
  // Analyzed sub-tab — lists every node with ≥1 successful completed LLM
  // analysis (GET /api/analyzed-nodes, one row per node, dropped results
  // excluded server-side). Loads once on first switch; ⟳ refresh re-fetches.
  //
  // Selection model (CLAUDE.md): clicking a row is a full select. That drives
  // the graph highlight AND the right-pane Analysis tab — which already reacts
  // to selectionStore.selectedNodeId — so this tab needs no detail view of its
  // own. The backend joins node url/title, so node_id always resolves.
  //
  // Right-click opens the shared bottom-pane menu via rowContextMenu; the
  // host-level ●/○ dot reuses domainVisibilityStore, matching Flags / Domains.

  import { onMount } from 'svelte';
  import { RefreshCw } from 'lucide-svelte';
  import {
    listAnalyzedNodes,
    type AnalyzedNodeRow,
    type GraphNode,
  } from '$lib/api';
  import { domainVisibilityStore } from '$lib/stores/domainVisibility.svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import BottomPaneRow from './BottomPaneRow.svelte';
  import {
    rowContextMenu,
    type RowMenuTarget,
  } from '$lib/contextMenu/rowMenu.svelte';
  import { hostFromUrl } from './flags';
  import {
    displayLabel,
    filterAnalyzed,
    formatAnalyzedAt,
    typesSummary,
  } from './analyzed';

  let rows = $state<AnalyzedNodeRow[]>([]);
  let loaded = $state(false);
  let loading = $state(false);
  let loadError = $state<string | null>(null);
  let urlFilter = $state('');

  onMount(() => {
    void refresh();
  });

  async function refresh(): Promise<void> {
    loading = true;
    try {
      const res = await listAnalyzedNodes();
      rows = res.nodes;
      loaded = true;
      loadError = null;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (!loaded) {
        loadError = msg;
      } else {
        toastStore.show(`Analyzed refresh failed: ${msg}`, 'warn');
      }
    } finally {
      loading = false;
    }
  }

  const filtered = $derived(filterAnalyzed(rows, urlFilter));

  // node_id → GraphNode lookup; resolves the right-click target so the
  // menu's id-bound actions run against the full GraphNode.
  const nodeById = $derived.by<Map<number, GraphNode>>(() => {
    const map = new Map<number, GraphNode>();
    const nodes = graphStore.payload?.nodes;
    if (!nodes) return map;
    for (const n of nodes) map.set(n.id, n);
    return map;
  });

  function onSelect(r: AnalyzedNodeRow): void {
    selectionStore.fullSelect(r.node_id);
  }

  function onRowContextMenu(r: AnalyzedNodeRow, event: MouseEvent): void {
    const target: RowMenuTarget = {
      url: r.url,
      node: nodeById.get(r.node_id),
      inCollection: false,
    };
    rowContextMenu.openAt(target, event);
  }
</script>

<section class="analyzed">
  <header class="head">
    <input
      type="text"
      class="filter"
      placeholder="Filter URL or title…"
      bind:value={urlFilter}
      aria-label="Filter analyzed nodes"
    />
    <span class="count" title="Filtered / total">
      {filtered.length}{filtered.length === rows.length
        ? ''
        : ` / ${rows.length}`}
    </span>
    <button
      type="button"
      class="icon"
      aria-label="Refresh"
      title="Refresh"
      onclick={() => void refresh()}
      disabled={loading}
    >
      <RefreshCw size={12} />
    </button>
  </header>

  {#if loadError}
    <p class="empty error">{loadError}</p>
  {:else if !loaded}
    <p class="empty">Loading analyzed nodes…</p>
  {:else if rows.length === 0}
    <p class="empty">
      No analyzed nodes yet — run LLM analysis to populate this list.
    </p>
  {:else if filtered.length === 0}
    <p class="empty">No analyzed nodes match this filter.</p>
  {:else}
    <ul class="list">
      {#each filtered as r (r.node_id)}
        {@const host = hostFromUrl(r.url)}
        {@const visible = host ? domainVisibilityStore.isVisible(host) : true}
        {@const active =
          selectionStore.selectMode === 'full' &&
          selectionStore.selectedNodeId === r.node_id}
        <li>
          <BottomPaneRow
            visible={visible}
            active={active}
            visibilityLabel={host
              ? visible
                ? `Hide ${host}`
                : `Show ${host}`
              : 'No host'}
            onToggleVisibility={() => {
              if (!host) return;
              domainVisibilityStore.toggle(host);
            }}
            onSelect={() => onSelect(r)}
            oncontextmenu={(e) => onRowContextMenu(r, e)}
          >
            <span class="label" title={r.url}>{displayLabel(r)}</span>
            <span class="types" title="Analyses">{typesSummary(r)}</span>
            <span class="when" title={r.last_analyzed ?? ''}>
              {formatAnalyzedAt(r.last_analyzed)}
            </span>
          </BottomPaneRow>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .analyzed {
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
    flex: 1 1 160px;
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
  .icon {
    background: transparent;
    border: 1px solid transparent;
    color: var(--muted);
    padding: 2px 4px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 2px;
  }
  .icon:hover:not(:disabled) {
    border-color: var(--border);
    color: var(--accent);
  }
  .icon:disabled {
    opacity: 0.45;
    cursor: not-allowed;
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
  .label {
    color: var(--accent);
    font-size: 11px;
    margin-right: 6px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .types {
    color: var(--text);
    font-size: 10px;
    margin-right: 6px;
  }
  .when {
    color: var(--muted);
    font-size: 10px;
  }
</style>
