<script lang="ts">
  // Domains sub-tab — Phase 3.1. Lists every `.onion` host from
  // /api/domains (the backend sorts by page_count DESC, host). Loads
  // once on first switch; manual ⟳ refresh, no polling — domains only
  // appear after a crawl writes a node, and the analyst is already
  // watching the Live Crawl tab during that work.
  //
  // Selection model (CLAUDE.md): the spec says clicking a row triggers
  // a "domain highlight" — every node from that host is highlighted in
  // the graph, everything else dimmed — and the right panel opens its
  // Domain tab on the host's first crawled page. The spec also notes
  // this "is not a multi-select and does not trigger the cluster
  // workspace." `selectionStore.replaceMulti` is the highlight-only
  // multi-select primitive: mode stays 'highlight' regardless of count,
  // so the right panel's cluster branch (which gates on selectMode ===
  // 'cluster') stays closed. The graph canvas's Ctrl/Shift-click and
  // Ctrl+A paths use `replaceCluster` / `toggleCluster` instead, which
  // is what actually trips the workspace.
  //
  // The ●/○ dot toggles the whole host in domainVisibilityStore (the
  // same store Bookmarks / Collection use). Hidden rows render dimmed.
  // Right-click opens the shared bottom-pane context menu with the
  // host's first GraphNode as the target.

  import { onMount } from 'svelte';
  import { RefreshCw } from 'lucide-svelte';
  import { listDomains, type DomainRow, type GraphNode } from '$lib/api';
  import { bottomPanePresetStore } from '$lib/stores/bottomPanePreset.svelte';
  import { domainVisibilityStore } from '$lib/stores/domainVisibility.svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { navigationStore } from '$lib/stores/navigation.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { workspaceStore } from '$lib/stores/workspace.svelte';
  import BottomPaneRow from './BottomPaneRow.svelte';
  import {
    rowContextMenu,
    type RowMenuTarget,
  } from '$lib/contextMenu/rowMenu.svelte';
  import { displayName, filterDomains } from './domains';

  let rows = $state<DomainRow[]>([]);
  let loaded = $state(false);
  let loading = $state(false);
  let loadError = $state<string | null>(null);
  let filter = $state('');

  onMount(() => {
    void refresh();
  });

  // Drain a host pre-filter staged by the right-pane Domain tab. The
  // store only hands us a value when we're the named destination, and
  // it clears on read — so the filter persists in this tab's local
  // state from here on. Reacts to bottomTab changes too so re-entering
  // the tab via another preset call still picks it up.
  $effect(() => {
    if (workspaceStore.bottomTab !== 'domains') return;
    const preset = bottomPanePresetStore.consume('domains');
    if (preset !== null) filter = preset;
  });

  async function refresh(): Promise<void> {
    loading = true;
    try {
      const res = await listDomains();
      rows = res.domains;
      loaded = true;
      loadError = null;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (!loaded) {
        loadError = msg;
      } else {
        toastStore.show(`Domains refresh failed: ${msg}`, 'warn');
      }
    } finally {
      loading = false;
    }
  }

  const filtered = $derived(filterDomains(rows, filter));

  // host → ordered list of that host's nodes (by first_seen asc, id asc
  // as a tiebreaker so the "Domain panel anchor" is stable). Built once
  // per graph payload; the row click reads both the full id set (for
  // multi-highlight) and the [0] entry (the panel anchor).
  const hostToNodes = $derived.by<Map<string, GraphNode[]>>(() => {
    const map = new Map<string, GraphNode[]>();
    const nodes = graphStore.payload?.nodes;
    if (!nodes) return map;
    for (const n of nodes) {
      if (!n.domain) continue;
      const bucket = map.get(n.domain);
      if (bucket) bucket.push(n);
      else map.set(n.domain, [n]);
    }
    for (const bucket of map.values()) {
      bucket.sort((a, b) => {
        const sa = a.first_seen ?? '';
        const sb = b.first_seen ?? '';
        if (sa === sb) return a.id - b.id;
        if (!sa) return 1;
        if (!sb) return -1;
        return sa < sb ? -1 : 1;
      });
    }
    return map;
  });

  function onSelect(host: string): void {
    const bucket = hostToNodes.get(host);
    if (!bucket || bucket.length === 0) {
      toastStore.show(
        'No graph nodes for this domain yet — crawl it first.',
        'info',
      );
      return;
    }
    selectionStore.replaceMulti(bucket.map((n) => n.id));
    navigationStore.setRight('domain');
  }

  // Open one domain's nodes as their own graph tab (induced subgraph).
  function onOpenAsTab(r: DomainRow): void {
    const bucket = hostToNodes.get(r.host);
    if (!bucket || bucket.length === 0) {
      toastStore.show(
        'No graph nodes for this domain yet — crawl it first.',
        'info',
      );
      return;
    }
    workspaceStore.openNodeSetTab({ kind: 'domain', host: r.host }, displayName(r));
  }

  function onRowContextMenu(host: string, event: MouseEvent): void {
    const bucket = hostToNodes.get(host);
    const node = bucket && bucket.length > 0 ? bucket[0] : undefined;
    const target: RowMenuTarget = {
      url: node?.raw_url ?? `http://${host}/`,
      node,
      inCollection: false,
    };
    rowContextMenu.openAt(target, event);
  }

  // The active marker tracks "the bottom-pane row whose host is the
  // focus of the current multi-highlight." When the analyst clicks a
  // single graph node, the host's row should not be marked active.
  function isActive(host: string): boolean {
    if (selectionStore.selectMode !== 'highlight') return false;
    const bucket = hostToNodes.get(host);
    if (!bucket || bucket.length === 0) return false;
    if (selectionStore.multiCount !== bucket.length) return false;
    for (const n of bucket) {
      if (!selectionStore.isSelected(n.id)) return false;
    }
    return true;
  }
</script>

<section class="domains">
  <header class="head">
    <input
      type="text"
      class="filter"
      placeholder="Filter domain or alias…"
      bind:value={filter}
      aria-label="Filter domains"
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
    <p class="empty">Loading domains…</p>
  {:else if rows.length === 0}
    <p class="empty">No domains yet — crawl a seed to populate this list.</p>
  {:else if filtered.length === 0}
    <p class="empty">No domains match this filter.</p>
  {:else}
    <ul class="list">
      {#each filtered as r (r.host)}
        {@const visible = domainVisibilityStore.isVisible(r.host)}
        {@const active = isActive(r.host)}
        <li>
          <BottomPaneRow
            visible={visible}
            active={active}
            visibilityLabel={visible ? `Hide ${r.host}` : `Show ${r.host}`}
            onToggleVisibility={() => domainVisibilityStore.toggle(r.host)}
            onSelect={() => onSelect(r.host)}
            oncontextmenu={(e) => onRowContextMenu(r.host, e)}
            onOpenAsTab={() => onOpenAsTab(r)}
            openAsTabLabel={`Open ${r.host} as graph tab`}
          >
            <span class="name" title={r.host}>{displayName(r)}</span>
            {#if r.alias && r.alias.trim()}
              <span class="host muted" title={r.host}>{r.host}</span>
            {/if}
            <span class="metric pages" title="Crawled pages">
              {r.page_count}p
            </span>
            {#if r.fail_count > 0}
              <span class="metric fails" title="Pages with 4xx/5xx">
                {r.fail_count}f
              </span>
            {/if}
            {#if r.flag_count > 0}
              <span class="metric flags" title="Active flags on this domain">
                {r.flag_count}🚩
              </span>
            {/if}
          </BottomPaneRow>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .domains {
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
  .name {
    color: var(--text);
    font-size: 11px;
    margin-right: 6px;
  }
  .host.muted {
    color: var(--muted);
    font-size: 10px;
    margin-right: 6px;
  }
  .metric {
    color: var(--muted);
    font-size: 10px;
    margin-right: 4px;
  }
  .metric.fails {
    color: #ffb347;
  }
  .metric.flags {
    color: #ff8899;
  }
</style>
