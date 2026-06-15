<script lang="ts">
  // Inventory tab — a passive, read-only survey of "what's loaded into my
  // session?" (item 5, inventory-tab.md). Three sections:
  //   1. Workspace tabs — every open graph tab, click to focus.
  //   2. Domains in the current graph — sorted by node count, click to
  //      highlight that host's nodes + open the right-pane Domain tab.
  //   3. Aggregate counts for the current scope.
  //
  // Reflects the ACTIVE workspace's rendered scope: for a NodeSet tab it runs
  // the loaded payload through the same buildNodeSetPredicate seam GraphCanvas
  // installs, so the inventory matches the induced subgraph on screen. Rows
  // navigate; nothing here mutates state.

  import { buildNodeSetPredicate } from '$lib/graph/nodeSetScope';
  import { domainVisibilityStore } from '$lib/stores/domainVisibility.svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { navigationStore } from '$lib/stores/navigation.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { workspaceStore, type OpenTab } from '$lib/stores/workspace.svelte';
  import { EmptyState } from '$lib/ui';
  import {
    inducedSubgraph,
    summarize,
    domainsInGraph,
    type DomainCount,
  } from './inventory';

  // The node/edge arrays for the active workspace's rendered scope. Global /
  // collection tabs use the full loaded payload; a NodeSet tab filters it to
  // its induced subgraph through the tab's own predicate.
  const scoped = $derived.by(() => {
    const payload = graphStore.payload;
    if (!payload) return { nodes: [], edges: [] };
    const source = workspaceStore.activeNodeSetSource();
    if (!source) return { nodes: payload.nodes, edges: payload.edges };
    const { predicate } = buildNodeSetPredicate(source, {
      isHidden: (d) => domainVisibilityStore.isHidden(d),
      isNodeHidden: (id) => domainVisibilityStore.isNodeHidden(id),
    });
    // ScopePredicate keys are graphology node ids (strings); the predicate
    // reads raw.id anyway, but pass the string form to match its signature.
    return inducedSubgraph(payload, (n) => predicate(String(n.id), n));
  });

  const summary = $derived(summarize(scoped.nodes, scoped.edges));
  const domains = $derived(domainsInGraph(scoped.nodes));

  // host → that host's node ids in scope, for the highlight gesture.
  const hostIds = $derived.by<Map<string, number[]>>(() => {
    const map = new Map<string, number[]>();
    for (const n of scoped.nodes) {
      if (n.is_cluster || !n.domain) continue;
      const bucket = map.get(n.domain);
      if (bucket) bucket.push(n.id);
      else map.set(n.domain, [n.id]);
    }
    return map;
  });

  function tabKindLabel(t: OpenTab): string {
    if (t.kind === 'global') return 'Global';
    if (t.kind === 'collection') return 'Collection';
    switch (t.source?.kind) {
      case 'domain':
        return 'Domain';
      case 'flag':
        return 'Flag set';
      case 'fingerprint':
        return 'Fingerprint';
      case 'bookmarks':
        return 'Bookmarks';
      case 'hidden':
        return 'Hidden';
      case 'selection':
        return 'Selection';
      default:
        return 'Node set';
    }
  }

  // Node count is exact only for the active tab (its payload is loaded) and
  // for captured NodeSet tabs (the member ids travel with the source). Others
  // show '—' — only one workspace payload is in memory at a time.
  function tabCount(t: OpenTab): number | null {
    if (t.id === workspaceStore.activeWorkspaceId) return scoped.nodes.length;
    const s = t.source;
    if (s && (s.kind === 'flag' || s.kind === 'fingerprint' || s.kind === 'selection')) {
      return s.nodeIds.length;
    }
    return null;
  }

  // Mirror DomainsTab: a host row is "active" when the current highlight is
  // exactly this host's node set (highlight mode, same members).
  function isDomainActive(d: DomainCount): boolean {
    if (selectionStore.selectMode !== 'highlight') return false;
    const ids = hostIds.get(d.host);
    if (!ids || ids.length === 0 || selectionStore.multiCount !== ids.length) return false;
    return ids.every((id) => selectionStore.isSelected(id));
  }

  function focusTab(id: string): void {
    workspaceStore.setWorkspace(id);
  }

  // Same gesture as DomainsTab.onSelect — highlight-only multi-select plus the
  // right-pane Domain tab; does not move the bottom-pane active row.
  function highlightDomain(host: string): void {
    const ids = hostIds.get(host);
    if (!ids || ids.length === 0) return;
    selectionStore.replaceMulti(ids);
    navigationStore.setRight('domain');
  }
</script>

<section class="inventory">
  {#if !graphStore.payload}
    <EmptyState title="No graph loaded." body="Crawl a seed or open a workspace to populate the inventory." />
  {:else}
    <!-- Aggregate counts -->
    <div class="counts" aria-label="Aggregate counts">
      <span class="stat"><b>{summary.nodes}</b> nodes</span>
      <span class="stat"><b>{summary.edges}</b> edges</span>
      <span class="sep">·</span>
      <span class="stat"><b>{summary.crawled}</b> crawled</span>
      <span class="stat muted"><b>{summary.uncrawled}</b> uncrawled</span>
      <span class="sep">·</span>
      <span class="stat flags"><b>{summary.flagged}</b> flagged</span>
      <span class="stat"><b>{summary.reviewed}</b> reviewed</span>
      <span class="stat"><b>{summary.categorized}</b> categorized</span>
    </div>

    <!-- Workspace tabs -->
    <div class="block">
      <h3 class="hd">Workspace tabs <span class="n">{workspaceStore.openTabs.length}</span></h3>
      <ul class="list">
        {#each workspaceStore.openTabs as t (t.id)}
          {@const count = tabCount(t)}
          <li>
            <button
              type="button"
              class="row"
              class:active={t.id === workspaceStore.activeWorkspaceId}
              onclick={() => focusTab(t.id)}
              title={`Focus ${t.label}`}
            >
              <span class="label" title={t.label}>{t.label}</span>
              <span class="kind">{tabKindLabel(t)}</span>
              <span class="metric">{count === null ? '—' : `${count}n`}</span>
            </button>
          </li>
        {/each}
      </ul>
    </div>

    <!-- Domains in the current graph -->
    <div class="block">
      <h3 class="hd">Domains in view <span class="n">{domains.length}</span></h3>
      {#if domains.length === 0}
        <p class="empty">No domains in the current scope.</p>
      {:else}
        <ul class="list">
          {#each domains as d (d.host)}
            <li>
              <button
                type="button"
                class="row"
                class:active={isDomainActive(d)}
                onclick={() => highlightDomain(d.host)}
                title={`Highlight ${d.host}`}
              >
                <span class="label" title={d.host}>{d.host}</span>
                {#if d.flagged > 0}
                  <span class="metric flags" title="Flagged nodes">{d.flagged}🚩</span>
                {/if}
                <span class="metric" title="Nodes in view">{d.count}n</span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
</section>

<style>
  .inventory {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-height: 0;
  }
  .counts {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 4px 10px;
    font-size: 11px;
    color: var(--text);
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }
  .stat b {
    color: var(--accent);
    font-weight: 600;
  }
  .stat.muted b {
    color: var(--muted);
  }
  .stat.flags b {
    color: #ff8899;
  }
  .sep {
    color: var(--border);
  }
  .block {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-height: 0;
  }
  .hd {
    margin: 0;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    font-weight: 600;
  }
  .hd .n {
    color: var(--border);
    margin-left: 2px;
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
    width: 100%;
    display: flex;
    align-items: center;
    gap: 6px;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    padding: 3px 6px;
    cursor: pointer;
    text-align: left;
  }
  .row:hover {
    background: rgba(0, 212, 170, 0.06);
  }
  .row.active {
    border-color: var(--accent);
    background: var(--accent-bg-subtle);
  }
  .label {
    flex: 1 1 auto;
    min-width: 0;
    color: var(--text);
    font-size: 11px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .kind {
    color: var(--muted);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }
  .metric {
    color: var(--muted);
    font-size: 10px;
    flex: 0 0 auto;
  }
  .metric.flags {
    color: #ff8899;
  }
  .empty {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
    padding: 2px 4px;
  }
</style>
