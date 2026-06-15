<script lang="ts">
  // Fingerprints sub-tab — Phase 4.2. Groups `.onion` sites by shared
  // HTTP response headers; high-IDF clusters surface unusual shared infra.
  //
  // Backend already returns clusters sorted (IDF desc, sites desc), so
  // the tab renders them in-order. Cluster expand fetches members lazily
  // and caches by (key,value) so a re-expand is free. Manual refresh
  // wipes both the cluster list and every member cache.
  //
  // Selection model: cluster rows themselves don't select — they expand.
  // Member rows use BottomPaneRow with per-node visibility (the spec is
  // explicit about per-node, not per-host: `domainVisibilityStore.toggleNode`).
  // Row click full-selects via selectionStore.

  import { onMount } from 'svelte';
  import { ChevronRight, ChevronDown, Download, Network, RefreshCw } from 'lucide-svelte';
  import {
    fingerprintsCsvUrl,
    listFingerprintMembers,
    listFingerprints,
    type FingerprintCluster,
    type FingerprintMember,
    type GraphNode,
  } from '$lib/api';
  import { bottomPanePresetStore } from '$lib/stores/bottomPanePreset.svelte';
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
    clampMinSites,
    clusterKey,
    filterClusters,
    filterMembers,
    formatIdf,
  } from './fingerprints';

  let minSites = $state(2);
  let filter = $state('');

  let clusters = $state<FingerprintCluster[]>([]);
  let loading = $state(false);
  let loadError = $state<string | null>(null);

  // (key,value) -> members cache. Switching min-sites or hitting ⟳
  // empties this so the next expand refetches.
  let memberCache = $state<Map<string, FingerprintMember[]>>(new Map());
  // Member load state, keyed the same way. 'loading' rows render a
  // spinner; 'error' rows render an inline message + retry link.
  let memberStatus = $state<Map<string, 'loading' | 'error'>>(new Map());

  // Open clusters — Set of (key,value) keys. Multiple may be open.
  let expanded = $state<Set<string>>(new Set());

  // Per-cluster filter — applied to that cluster's member list once
  // loaded. Keyed by (key,value); cleared when min-sites changes.
  let memberFilter = $state<Map<string, string>>(new Map());

  onMount(() => {
    void loadClusters();
  });

  // Drain a host pre-filter from the right-pane Domain tab's
  // "View fingerprint clusters →" link. The filter input matches any
  // cluster value (header value) by substring — host names appear
  // in member rows but not in cluster keys, so a host preset acts as
  // a member-list scoping hint via the cluster value/text filter.
  $effect(() => {
    if (workspaceStore.bottomTab !== 'fingerprints') return;
    const preset = bottomPanePresetStore.consume('fingerprints');
    if (preset !== null) filter = preset;
  });

  async function loadClusters(): Promise<void> {
    loading = true;
    loadError = null;
    try {
      const res = await listFingerprints(clampMinSites(minSites));
      clusters = res.clusters;
    } catch (err) {
      loadError = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  function onMinSitesChange(): void {
    minSites = clampMinSites(minSites);
    // Wipe member caches — a cluster's row count is meaningful per
    // threshold; on a fresh threshold the prior members are stale.
    memberCache = new Map();
    memberStatus = new Map();
    expanded = new Set();
    memberFilter = new Map();
    void loadClusters();
  }

  function onRefresh(): void {
    memberCache = new Map();
    memberStatus = new Map();
    expanded = new Set();
    void loadClusters();
  }

  function onCsv(): void {
    const url = fingerprintsCsvUrl(clampMinSites(minSites));
    const a = document.createElement('a');
    a.href = url;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  async function loadMembers(c: FingerprintCluster): Promise<void> {
    const k = clusterKey(c);
    if (memberCache.has(k)) return;
    const nextStatus = new Map(memberStatus);
    nextStatus.set(k, 'loading');
    memberStatus = nextStatus;
    try {
      const res = await listFingerprintMembers(c.key, c.value);
      const cache = new Map(memberCache);
      cache.set(k, res.members);
      memberCache = cache;
      const cleared = new Map(memberStatus);
      cleared.delete(k);
      memberStatus = cleared;
    } catch (err) {
      const errored = new Map(memberStatus);
      errored.set(k, 'error');
      memberStatus = errored;
      const msg = err instanceof Error ? err.message : String(err);
      toastStore.show(`Members load failed: ${msg}`, 'error');
    }
  }

  function toggleExpanded(c: FingerprintCluster): void {
    const k = clusterKey(c);
    const next = new Set(expanded);
    if (next.has(k)) {
      next.delete(k);
    } else {
      next.add(k);
      void loadMembers(c);
    }
    expanded = next;
  }

  function memberFilterFor(k: string): string {
    return memberFilter.get(k) ?? '';
  }

  function setMemberFilter(k: string, value: string): void {
    const next = new Map(memberFilter);
    if (value) next.set(k, value);
    else next.delete(k);
    memberFilter = next;
  }

  // Pull a real GraphNode for the right-click menu so id-bound items
  // (Flag, Mark Reviewed, Open in Tor) get the full picture. The
  // members payload doesn't carry alias / flag_status / reviewed.
  const nodeById = $derived.by<Map<number, GraphNode>>(() => {
    const map = new Map<number, GraphNode>();
    const nodes = graphStore.payload?.nodes;
    if (!nodes) return map;
    for (const n of nodes) map.set(n.id, n);
    return map;
  });

  function onMemberSelect(m: FingerprintMember): void {
    selectionStore.fullSelect(m.id);
  }

  function onMemberContextMenu(m: FingerprintMember, event: MouseEvent): void {
    const target: RowMenuTarget = {
      url: m.url,
      node: nodeById.get(m.id),
      inCollection: false,
    };
    rowContextMenu.openAt(target, event);
  }

  // Open one fingerprint cluster's members as their own graph tab. Members
  // load lazily on expand; ensure they're fetched before capturing ids.
  async function onOpenClusterAsTab(c: FingerprintCluster): Promise<void> {
    const k = clusterKey(c);
    if (!memberCache.has(k)) await loadMembers(c);
    const members = memberCache.get(k);
    if (!members || members.length === 0) {
      toastStore.show('No cluster members to open.', 'info');
      return;
    }
    const summary = `${c.key}:${c.value}`;
    workspaceStore.openNodeSetTab(
      { kind: 'fingerprint', nodeIds: members.map((m) => m.id), summary },
      `${c.key}: ${c.value}`,
    );
  }

  const filteredClusters = $derived(filterClusters(clusters, filter));
</script>

<section class="fingerprints">
  <header class="head">
    <label class="min-sites" title="Minimum site count">
      Sites ≥
      <input
        type="number"
        min="1"
        max="1000"
        step="1"
        bind:value={minSites}
        onchange={onMinSitesChange}
        aria-label="Minimum sites per cluster"
      />
    </label>
    <input
      type="text"
      class="filter"
      placeholder="Filter header key or value…"
      bind:value={filter}
      aria-label="Filter clusters"
    />
    <span class="count" title="Filtered / total">
      {filteredClusters.length}{filteredClusters.length === clusters.length
        ? ''
        : ` / ${clusters.length}`}
    </span>
    <button type="button" class="icon" title="Refresh" aria-label="Refresh" onclick={onRefresh}>
      <RefreshCw size={11} />
    </button>
    <button type="button" class="icon" title="Export CSV" aria-label="Export CSV" onclick={onCsv}>
      <Download size={11} />
    </button>
  </header>

  {#if loadError}
    <p class="empty error">{loadError}</p>
  {:else if loading && clusters.length === 0}
    <p class="empty">Loading fingerprints…</p>
  {:else if clusters.length === 0}
    <p class="empty">
      No clusters at this threshold. Lower the "Sites ≥" value to see
      smaller groups.
    </p>
  {:else if filteredClusters.length === 0}
    <p class="empty">No clusters match this filter.</p>
  {:else}
    <ul class="clusters">
      {#each filteredClusters as c (clusterKey(c))}
        {@const k = clusterKey(c)}
        {@const isOpen = expanded.has(k)}
        {@const memStatus = memberStatus.get(k)}
        {@const members = memberCache.get(k)}
        {@const memFilter = memberFilterFor(k)}
        {@const memFiltered = members ? filterMembers(members, memFilter) : []}
        <li class="cluster">
          <div class="cluster-head">
            <button
              type="button"
              class="cluster-row"
              aria-expanded={isOpen}
              onclick={() => toggleExpanded(c)}
            >
              <span class="caret">
                {#if isOpen}
                  <ChevronDown size={12} />
                {:else}
                  <ChevronRight size={12} />
                {/if}
              </span>
              <span class="key" title={c.key}>{c.key}</span>
              <span class="value" title={c.value}>{c.value}</span>
              <span class="sites" title="Site count">{c.sites}</span>
              <span class="idf" title="Inverse document frequency">
                {formatIdf(c.idf)}
              </span>
            </button>
            <button
              type="button"
              class="open-tab"
              aria-label={`Open ${c.key}: ${c.value} as graph tab`}
              title="Open cluster as graph tab"
              onclick={() => void onOpenClusterAsTab(c)}
            >
              <Network size={13} />
            </button>
          </div>
          {#if isOpen}
            <div class="members">
              {#if memStatus === 'loading'}
                <p class="member-empty">Loading members…</p>
              {:else if memStatus === 'error'}
                <p class="member-empty error">
                  Members load failed.
                  <button
                    type="button"
                    class="link"
                    onclick={() => void loadMembers(c)}
                  >
                    Retry
                  </button>
                </p>
              {:else if !members || members.length === 0}
                <p class="member-empty">No members.</p>
              {:else}
                <input
                  type="text"
                  class="member-filter"
                  placeholder="Filter URL or title…"
                  value={memFilter}
                  oninput={(e) =>
                    setMemberFilter(k, (e.currentTarget as HTMLInputElement).value)}
                  aria-label="Filter members"
                />
                {#if memFiltered.length === 0}
                  <p class="member-empty">No members match.</p>
                {:else}
                  <ul class="member-list">
                    {#each memFiltered as m (m.id)}
                      {@const visible = domainVisibilityStore.isNodeVisible(m.id)}
                      {@const active =
                        selectionStore.selectMode === 'full' &&
                        selectionStore.selectedNodeId === m.id}
                      <li>
                        <BottomPaneRow
                          visible={visible}
                          active={active}
                          visibilityLabel={visible ? 'Hide node' : 'Show node'}
                          onToggleVisibility={() =>
                            domainVisibilityStore.toggleNode(m.id)}
                          onSelect={() => onMemberSelect(m)}
                          oncontextmenu={(e) => onMemberContextMenu(m, e)}
                        >
                          <span class="m-url" title={m.url}>{m.url}</span>
                          {#if m.title}
                            <span class="m-title" title={m.title}>{m.title}</span>
                          {/if}
                          {#if m.risk_score}
                            <span class="m-risk" title="Risk score">{m.risk_score}</span>
                          {/if}
                          {#if m.category}
                            <span class="m-cat" title="Category">{m.category}</span>
                          {/if}
                        </BottomPaneRow>
                      </li>
                    {/each}
                  </ul>
                {/if}
              {/if}
            </div>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .fingerprints {
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
  .min-sites {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--muted);
    font-size: 11px;
  }
  .min-sites input {
    width: 56px;
    background: #17191f;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 3px 6px;
    font-size: 11px;
  }
  .min-sites input:focus-visible {
    border-color: var(--accent);
    outline: none;
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
    padding: 3px 6px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    border-radius: 2px;
  }
  .icon:hover {
    border-color: var(--border);
    color: var(--accent);
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
  .clusters {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .cluster {
    display: flex;
    flex-direction: column;
  }
  .cluster-head {
    display: flex;
    align-items: center;
    gap: 2px;
  }
  .cluster-row {
    flex: 1 1 auto;
    min-width: 0;
    display: grid;
    grid-template-columns: 16px minmax(80px, 1fr) minmax(120px, 2fr) 40px 50px;
    align-items: center;
    gap: 6px;
    background: transparent;
    border: none;
    color: var(--text);
    padding: 4px 4px;
    font: inherit;
    text-align: left;
    cursor: pointer;
    border-radius: 2px;
  }
  .cluster-row:hover {
    background: rgba(0, 212, 170, 0.06);
  }
  .cluster-head .open-tab {
    flex: 0 0 auto;
    width: 22px;
    height: 20px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    background: transparent;
    border: none;
    color: var(--muted);
    cursor: pointer;
    border-radius: 2px;
    opacity: 0;
    transition: opacity 80ms ease;
  }
  .cluster-head:hover .open-tab,
  .cluster-head .open-tab:focus-visible {
    opacity: 0.7;
  }
  .cluster-head .open-tab:hover {
    opacity: 1;
    color: var(--accent);
    background: rgba(0, 212, 170, 0.12);
  }
  .caret {
    display: inline-flex;
    color: var(--muted);
  }
  .key {
    font-size: 11px;
    color: var(--text);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .value {
    font-size: 11px;
    color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .sites {
    font-size: 11px;
    color: var(--text);
    text-align: right;
  }
  .idf {
    font-size: 11px;
    color: var(--accent);
    text-align: right;
  }
  .members {
    padding: 4px 8px 4px 24px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    border-left: 1px solid var(--border);
    margin-left: 6px;
  }
  .member-filter {
    background: #17191f;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 3px 6px;
    font-size: 11px;
  }
  .member-filter:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .member-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .member-list li {
    display: flex;
    align-items: center;
  }
  .member-list li :global(.row) {
    flex: 1 1 auto;
    min-width: 0;
  }
  .member-empty {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
    padding: 4px 2px;
  }
  .member-empty.error {
    color: #ff8899;
  }
  .link {
    background: none;
    border: none;
    color: var(--accent);
    cursor: pointer;
    font: inherit;
    text-decoration: underline;
    padding: 0 4px;
  }
  .m-url {
    color: var(--text);
    font-size: 11px;
    margin-right: 6px;
  }
  .m-title {
    color: var(--muted);
    font-size: 10px;
    margin-right: 6px;
  }
  .m-risk {
    color: #ffb347;
    font-size: 10px;
    margin-right: 6px;
  }
  .m-cat {
    color: var(--muted);
    font-size: 10px;
  }
</style>
