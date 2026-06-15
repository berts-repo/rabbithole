<script lang="ts">
  // Right-pane action bar (pane-responsibility-reset).
  //
  // One consistent strip of selection actions for the current node, sitting
  // above the Page / Domain / Analysis tab strip. Primary buttons cover the
  // frequent verbs; "More" holds the less-frequent ones. All actions reuse
  // the surface-neutral helpers in `$lib/contextMenu/actions.ts` and the
  // existing action modals — this bar adds no new action logic.
  //
  // The action set varies by selection type: the Domain tab adds "Add
  // monitor" to More (a domain-scoped verb); structure and styling are
  // identical across tabs.

  import { onMount } from 'svelte';
  import {
    Flag,
    FolderPlus,
    MoreHorizontal,
    Send,
    Sparkles,
  } from 'lucide-svelte';
  import { ActionBar as ActionBarPrimitive } from '$lib/ui';
  import { getNode, type GraphNode, type NodeRow } from '$lib/api';
  import { isUncrawled } from '$lib/nodeState';
  import {
    actCopyUrl,
    actFlag,
    actHideFromGraph,
    actOpenInTor,
    actQueueCrawl,
    actRemoveFlag,
    actSaveSeedBookmark,
    actToggleReviewed,
    queueAnalysis,
    selectionFromNodes,
  } from '$lib/contextMenu/actions';
  import CollectionPickerModal from '../../components/modals/CollectionPickerModal.svelte';
  import AddMonitorModal from '../../components/modals/AddMonitorModal.svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { navigationStore } from '$lib/stores/navigation.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { servicesStore } from '$lib/stores/services.svelte';

  // Lazily fetched detail for a selected node that isn't in the current
  // graph payload (filtered, hidden, or in another workspace). The payload
  // is the zero-cost source for the common case; this is the fallback.
  let fetched = $state<NodeRow | null>(null);
  let fetchGen = 0;

  $effect(() => {
    const id = selectionStore.selectedNodeId;
    if (id === null) {
      fetched = null;
      return;
    }
    if (graphStore.payload?.nodes.some((n) => n.id === id)) {
      fetched = null;
      return;
    }
    void loadFetched(id);
  });

  async function loadFetched(id: number): Promise<void> {
    const gen = ++fetchGen;
    try {
      const n = await getNode(id);
      if (gen === fetchGen) fetched = n;
    } catch {
      if (gen === fetchGen) fetched = null;
    }
  }

  // Current selection summary, derived from the payload first.
  const sel = $derived.by(() => {
    const id = selectionStore.selectedNodeId;
    if (id === null) return null;
    const live = graphStore.payload?.nodes.find((n) => n.id === id);
    if (live) {
      return {
        id,
        url: live.raw_url,
        flagged: !!live.flag_status,
        reviewed: live.reviewed,
        uncrawled: isUncrawled(live),
        domain: live.domain,
      };
    }
    if (fetched && fetched.id === id) {
      return {
        id,
        url: fetched.url,
        flagged: !!fetched.flag,
        reviewed: fetched.reviewed,
        uncrawled: isUncrawled(fetched),
        domain: fetched.domain,
      };
    }
    return { id, url: null, flagged: false, reviewed: false, uncrawled: false, domain: null };
  });

  // Build the GraphNode[] the action modals consume — prefer the live
  // payload node, fall back to synthesizing from fetched detail (same
  // pattern as AnalysisTab's queueTarget).
  function target(): GraphNode[] {
    const id = selectionStore.selectedNodeId;
    if (id === null) return [];
    const live = graphStore.payload?.nodes.find((n) => n.id === id);
    if (live) return [live];
    if (fetched && fetched.id === id) {
      return [
        {
          id: fetched.id,
          label: fetched.title ?? fetched.url,
          alias: null,
          title_text: fetched.title ?? '',
          raw_url: fetched.url,
          color: '#000',
          domain: fetched.domain,
          network: fetched.network,
          depth: null,
          flag_status: fetched.flag?.status ?? null,
          is_bridge: false,
          betweenness: 0,
          pagerank: 0,
          cluster_id: null,
          infra_cluster_id: null,
          first_seen: fetched.first_seen,
          is_cluster: false,
          state: fetched.state,
          analysis_excluded: fetched.analysis_excluded,
          reviewed: fetched.reviewed,
          category: fetched.category,
          in_degree_count: 0,
          out_degree_count: 0,
          label_ids: fetched.label_ids,
          domain_label_ids: fetched.domain_label_ids,
        },
      ];
    }
    return [];
  }

  const torArmed = $derived(servicesStore.killSwitch.phase === 'armed');
  const isDomainTab = $derived(navigationStore.rightTab === 'domain');

  // ---------------- Modal + menu state ----------------

  let collectionOpen = $state(false);
  let monitorOpen = $state(false);
  let moreOpen = $state(false);

  function toggleFlag(): void {
    if (!sel) return;
    if (sel.flagged) void actRemoveFlag(sel.id);
    else void actFlag(sel.id, 2); // analyst quick-flag → Medium
  }

  function closeMore(): void {
    moreOpen = false;
  }

  // Close the More dropdown on any outside pointerdown.
  onMount(() => {
    function onDown(e: PointerEvent) {
      if (!moreOpen) return;
      const t = e.target;
      if (t instanceof Element && t.closest('.more-wrap')) return;
      moreOpen = false;
    }
    document.addEventListener('pointerdown', onDown);
    return () => document.removeEventListener('pointerdown', onDown);
  });
</script>

{#if sel}
  <ActionBarPrimitive>
    {#snippet primary()}
      <button
        type="button"
        class="act"
        onclick={() => sel.url && actQueueCrawl(sel.url)}
        disabled={!sel.url}
        title="Send to Crawl"
      >
        <Send size={12} /> Crawl
      </button>
      <button
        type="button"
        class="act"
        onclick={() => (collectionOpen = true)}
        title="Add to collection"
      >
        <FolderPlus size={12} /> Collection
      </button>
      <button
        type="button"
        class="act"
        class:on={sel.flagged}
        onclick={toggleFlag}
        title={sel.flagged ? 'Remove flag' : 'Flag'}
      >
        <Flag size={12} /> {sel.flagged ? 'Flagged' : 'Flag'}
      </button>
      <button
        type="button"
        class="act"
        onclick={() => queueAnalysis(selectionFromNodes(target()))}
        title="Queue analysis"
      >
        <Sparkles size={12} /> Analyze
      </button>
    {/snippet}
    {#snippet overflow()}
      <div class="more-wrap">
        <button
          type="button"
          class="act icon"
          aria-label="More actions"
          aria-haspopup="menu"
          aria-expanded={moreOpen}
          onclick={() => (moreOpen = !moreOpen)}
        >
          <MoreHorizontal size={14} />
        </button>
        {#if moreOpen}
          <div class="menu" role="menu">
            <button
              type="button"
              role="menuitem"
              onclick={() => {
                if (sel.url) void actCopyUrl(sel.url);
                closeMore();
              }}
            >
              Copy URL
            </button>
            <button
              type="button"
              role="menuitem"
              disabled={!torArmed}
              title={torArmed ? '' : 'Tor not connected'}
              onclick={() => {
                void actOpenInTor(sel.id);
                closeMore();
              }}
            >
              Open in Tor Browser
            </button>
            <button
              type="button"
              role="menuitem"
              onclick={() => {
                void actToggleReviewed(sel.id, sel.reviewed);
                closeMore();
              }}
            >
              {sel.reviewed ? 'Mark Unreviewed' : 'Mark Reviewed'}
            </button>
            <button
              type="button"
              role="menuitem"
              onclick={() => {
                if (sel.url) void actSaveSeedBookmark(sel.url);
                closeMore();
              }}
            >
              Save as Seed Bookmark
            </button>
            {#if isDomainTab}
              <button
                type="button"
                role="menuitem"
                onclick={() => {
                  monitorOpen = true;
                  closeMore();
                }}
              >
                Add Monitor…
              </button>
            {/if}
            <button
              type="button"
              role="menuitem"
              disabled={sel.uncrawled || !sel.url}
              title={sel.uncrawled ? 'Crawled nodes only' : ''}
              onclick={() => {
                if (sel.url) void actHideFromGraph(sel.url);
                closeMore();
              }}
            >
              Hide from Graph
            </button>
          </div>
        {/if}
      </div>
    {/snippet}
  </ActionBarPrimitive>
{/if}

{#if collectionOpen}
  <CollectionPickerModal
    nodeIds={target().map((n) => n.id)}
    onClose={() => (collectionOpen = false)}
  />
{/if}
{#if monitorOpen && sel?.url}
  <AddMonitorModal url={sel.url} onClose={() => (monitorOpen = false)} />
{/if}

<style>
  .act {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 2px;
    color: var(--muted);
    font-size: 11px;
    padding: 4px 8px;
    cursor: pointer;
    white-space: nowrap;
  }
  .act:hover:not(:disabled) {
    color: var(--accent);
    border-color: var(--accent);
  }
  .act:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .act.on {
    color: var(--accent);
    border-color: var(--accent);
    background: var(--accent-bg-subtle);
  }
  .act.icon {
    padding: 4px 6px;
  }
  .more-wrap {
    position: relative;
  }
  .menu {
    position: absolute;
    top: calc(100% + 4px);
    right: 0;
    z-index: 20;
    display: flex;
    flex-direction: column;
    min-width: 180px;
    background: rgba(10, 15, 13, 0.98);
    border: 1px solid var(--border);
    border-radius: 2px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
  }
  .menu button {
    background: transparent;
    border: none;
    color: var(--text);
    font-size: 11px;
    text-align: left;
    padding: 6px 10px;
    cursor: pointer;
  }
  .menu button:hover:not(:disabled) {
    background: rgba(0, 212, 170, 0.12);
    color: var(--accent);
  }
  .menu button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
