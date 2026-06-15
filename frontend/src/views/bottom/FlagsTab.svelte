<script lang="ts">
  // Flags sub-tab — Phase 3.2. Lists every row from /api/flags (joined
  // with node url + title server-side). Loads once on first switch;
  // ⟳ refresh re-fetches manually. The graph payload's `flag_status`
  // change events would justify a poll, but flags mutate slowly —
  // manual refresh + the toast that fires when actFlag / actUnflag
  // resolve is enough today.
  //
  // Selection model (CLAUDE.md): clicking a row is a full select. The
  // backend join guarantees `node_id` resolves to a real `nodes` row,
  // so fullSelect always has a target — no toast fallback needed here
  // the way Bookmarks needs one for stub-URL rows.
  //
  // Right-click opens the shared bottom-pane menu via rowContextMenu.
  // The host-level ●/○ dot reuses domainVisibilityStore — hiding a
  // host hides every node from it in the graph, which matches the
  // visibility-toggle behaviour on Bookmarks / Collection / Domains.

  import { onMount } from 'svelte';
  import { Network, RefreshCw } from 'lucide-svelte';
  import {
    listFlags,
    type FlagListRow,
    type GraphNode,
  } from '$lib/api';
  import { domainVisibilityStore } from '$lib/stores/domainVisibility.svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { workspaceStore } from '$lib/stores/workspace.svelte';
  import BottomPaneRow from './BottomPaneRow.svelte';
  import {
    rowContextMenu,
    type RowMenuTarget,
  } from '$lib/contextMenu/rowMenu.svelte';
  import {
    filterFlags,
    hostFromUrl,
    PRIORITY_FILTER_OPTIONS,
    priorityBadgeClass,
    priorityLabel,
    STATUS_FILTER_OPTIONS,
    statusLabel,
    type PriorityFilterValue,
    type StatusFilterValue,
  } from './flags';

  let rows = $state<FlagListRow[]>([]);
  let loaded = $state(false);
  let loading = $state(false);
  let loadError = $state<string | null>(null);

  let urlFilter = $state('');
  let statusFilter = $state<StatusFilterValue>('all');
  let priorityFilter = $state<PriorityFilterValue>('all');

  onMount(() => {
    void refresh();
  });

  async function refresh(): Promise<void> {
    loading = true;
    try {
      const res = await listFlags();
      rows = res.flags;
      loaded = true;
      loadError = null;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (!loaded) {
        loadError = msg;
      } else {
        toastStore.show(`Flags refresh failed: ${msg}`, 'warn');
      }
    } finally {
      loading = false;
    }
  }

  const filtered = $derived(
    filterFlags(rows, statusFilter, priorityFilter, urlFilter),
  );

  // node_id → GraphNode lookup; used to resolve the right-click
  // target so the menu's id-bound actions (Flag, Mark Reviewed, etc.)
  // run against the full GraphNode rather than a stripped placeholder.
  const nodeById = $derived.by<Map<number, GraphNode>>(() => {
    const map = new Map<number, GraphNode>();
    const nodes = graphStore.payload?.nodes;
    if (!nodes) return map;
    for (const n of nodes) map.set(n.id, n);
    return map;
  });

  function onSelect(r: FlagListRow): void {
    selectionStore.fullSelect(r.node_id);
  }

  // Open the currently-filtered flagged nodes as their own graph tab.
  // Members are captured at open; the filter description keys the tab so
  // different filters open distinct tabs and the same filter refreshes.
  function flagTabLabel(): string {
    const parts: string[] = [];
    if (statusFilter !== 'all') parts.push(statusFilter);
    if (priorityFilter !== 'all') parts.push(priorityLabel(priorityFilter as number));
    return parts.length ? `Flags: ${parts.join(' ')}` : 'Flags';
  }

  function onOpenFlaggedAsTab(): void {
    const ids = filtered.map((r) => r.node_id);
    if (ids.length === 0) {
      toastStore.show('No flagged nodes to open.', 'info');
      return;
    }
    const summary = `${statusFilter}|${priorityFilter}|${urlFilter.trim()}`;
    workspaceStore.openNodeSetTab({ kind: 'flag', nodeIds: ids, summary }, flagTabLabel());
  }

  function onRowContextMenu(r: FlagListRow, event: MouseEvent): void {
    const target: RowMenuTarget = {
      url: r.url,
      node: nodeById.get(r.node_id),
      inCollection: false,
    };
    rowContextMenu.openAt(target, event);
  }
</script>

<section class="flags">
  <header class="head">
    <input
      type="text"
      class="filter"
      placeholder="Filter URL or title…"
      bind:value={urlFilter}
      aria-label="Filter flags"
    />
    <select
      class="select"
      bind:value={statusFilter}
      aria-label="Filter by status"
    >
      {#each STATUS_FILTER_OPTIONS as o (o.value)}
        <option value={o.value}>{o.label}</option>
      {/each}
    </select>
    <select
      class="select"
      bind:value={priorityFilter}
      aria-label="Filter by priority"
    >
      {#each PRIORITY_FILTER_OPTIONS as o (o.value)}
        <option value={o.value}>{o.label}</option>
      {/each}
    </select>
    <span class="count" title="Filtered / total">
      {filtered.length}{filtered.length === rows.length
        ? ''
        : ` / ${rows.length}`}
    </span>
    <button
      type="button"
      class="icon"
      aria-label="Open flagged as graph tab"
      title="Open flagged as graph tab"
      onclick={onOpenFlaggedAsTab}
      disabled={filtered.length === 0}
    >
      <Network size={12} />
    </button>
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
    <p class="empty">Loading flags…</p>
  {:else if rows.length === 0}
    <p class="empty">
      No flags yet — flag a node from the right-click menu or right pane.
    </p>
  {:else if filtered.length === 0}
    <p class="empty">No flags match these filters.</p>
  {:else}
    <ul class="list">
      {#each filtered as r (r.id)}
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
            <span class="url" title={r.url}>{r.url}</span>
            <span
              class={`badge ${priorityBadgeClass(r.priority)}`}
              title={`Priority: ${priorityLabel(r.priority)}`}
            >
              {priorityLabel(r.priority)}
            </span>
            <span class="status" title={r.status}>{statusLabel(r.status)}</span>
          </BottomPaneRow>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .flags {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-height: 0;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
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
  .select {
    background: #17191f;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 3px 6px;
    font-size: 11px;
  }
  .select:focus-visible {
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
  .url {
    color: var(--accent);
    font-size: 11px;
    margin-right: 6px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .badge {
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 8px;
    text-align: center;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-right: 6px;
  }
  .prio-high {
    background: rgba(255, 85, 119, 0.18);
    color: #ff8899;
  }
  .prio-med {
    background: rgba(255, 179, 71, 0.18);
    color: #ffb347;
  }
  .prio-low {
    background: rgba(0, 212, 170, 0.15);
    color: var(--accent);
  }
  .prio-unknown {
    background: rgba(120, 120, 140, 0.18);
    color: var(--muted);
  }
  .status {
    color: var(--muted);
    font-size: 10px;
  }
</style>
