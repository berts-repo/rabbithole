<script lang="ts">
  // Bookmarks sub-tab — Phase 1.4. Reads `seedBookmarksStore` (the same
  // source feeding the left-pane Crawl bookmarks dropdown), so a row
  // added from anywhere (Save-as-Seed-Bookmark from the graph menu, the
  // Plus-popover in CrawlControls) shows here immediately without a
  // refetch.
  //
  // Selection model (CLAUDE.md): clicking the content button is a full
  // select. A bookmark URL may not have a graph node yet (the seed was
  // never crawled) — in that case fullSelect short-circuits with a toast
  // and the right panel stays put.
  //
  // The ●/○ dot toggles the bookmark's host in domainVisibilityStore.
  // The graph canvas's structural-visibility pass reads that store and
  // hides every node whose `domain` matches a hidden host. Bookmarks
  // whose URL has no parseable host render with the dot disabled.

  import { onMount } from 'svelte';
  import { Network, Plus, Send, Pencil, X, Check } from 'lucide-svelte';
  import { isSupportedUrl } from '$lib/onionUrl';
  import type { GraphNode, Seed } from '$lib/api';
  import { actQueueCrawl } from '$lib/contextMenu/actions';
  import { domainVisibilityStore } from '$lib/stores/domainVisibility.svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { seedBookmarksStore } from '$lib/stores/seedBookmarks.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { workspaceStore } from '$lib/stores/workspace.svelte';
  import BottomPaneRow from './BottomPaneRow.svelte';
  import {
    rowContextMenu,
    type RowMenuTarget,
  } from '$lib/contextMenu/rowMenu.svelte';
  import { filterSeeds, formatAddedAt, hostFromUrl } from './bookmarks';

  let filter = $state('');

  // "Add bookmark" inline popover. The URL field accepts onion-only;
  // label is optional. Duplicate hits show the same already-saved toast
  // CrawlControls uses so the analyst recognises the message.
  let addOpen = $state(false);
  let addUrl = $state('');
  let addLabel = $state('');
  let saving = $state(false);

  // Inline rename — only one row may be editing at a time. The draft
  // label is held here so Escape can revert without touching the store.
  let editingUrl = $state<string | null>(null);
  let editingDraft = $state('');

  // Seeds load once per page lifetime. The store already mirrors the
  // server, so a switch into this tab without any data triggers a fetch.
  onMount(() => {
    if (!seedBookmarksStore.loaded) {
      void seedBookmarksStore.refresh();
    }
  });

  const seeds = $derived(seedBookmarksStore.seeds);
  const filtered = $derived(filterSeeds(seeds, filter));

  // Build a host → first matching GraphNode lookup once per payload so
  // each row's right-click target / full-select id can be resolved in
  // O(1) — the spec doesn't pin the node to a specific URL on stub
  // entries, the first node from that host is good enough.
  const hostToNode = $derived.by<Map<string, GraphNode>>(() => {
    const map = new Map<string, GraphNode>();
    const nodes = graphStore.payload?.nodes;
    if (!nodes) return map;
    for (const n of nodes) {
      if (n.domain && !map.has(n.domain)) map.set(n.domain, n);
    }
    return map;
  });

  function nodeForSeed(s: Seed): GraphNode | undefined {
    const host = hostFromUrl(s.url);
    if (!host) return undefined;
    return hostToNode.get(host);
  }

  async function onAddBookmark(): Promise<void> {
    const url = addUrl.trim();
    if (!isSupportedUrl(url)) {
      toastStore.show('Enter a valid .onion or .i2p URL first.', 'warn');
      return;
    }
    saving = true;
    try {
      const added = await seedBookmarksStore.add({
        url,
        label: addLabel.trim() || null,
      });
      toastStore.show(
        added ? 'Bookmark saved.' : 'Already in crawl bookmarks.',
        'info',
      );
      if (added) {
        addUrl = '';
        addLabel = '';
        addOpen = false;
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Save failed: ${msg}`, 'error');
    } finally {
      saving = false;
    }
  }

  async function onDelete(url: string): Promise<void> {
    try {
      await seedBookmarksStore.remove(url);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Delete failed: ${msg}`, 'error');
    }
  }

  function startRename(s: Seed): void {
    editingUrl = s.url;
    editingDraft = s.label ?? '';
  }

  function cancelRename(): void {
    editingUrl = null;
    editingDraft = '';
  }

  async function commitRename(): Promise<void> {
    if (editingUrl === null) return;
    const target = editingUrl;
    const next = editingDraft.trim();
    try {
      await seedBookmarksStore.renameLabel(target, next || null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Rename failed: ${msg}`, 'error');
    } finally {
      // Always close the editor — the analyst can re-open if the store
      // didn't update. Leaving it open after a failed save just looks
      // stuck.
      editingUrl = null;
      editingDraft = '';
    }
  }

  function onRenameKey(e: KeyboardEvent): void {
    if (e.key === 'Enter') {
      e.preventDefault();
      void commitRename();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      cancelRename();
    }
  }

  function onSendToCrawl(s: Seed): void {
    actQueueCrawl(s.url);
  }

  function onSelect(s: Seed): void {
    const node = nodeForSeed(s);
    if (!node) {
      // Spec: clicking a row "selects that node in the graph". A bookmark
      // URL whose host hasn't been crawled has no node to select — be
      // honest about it.
      toastStore.show(
        'No graph node for this bookmark yet — crawl it first.',
        'info',
      );
      return;
    }
    selectionStore.fullSelect(node.id);
  }

  // Open the bookmarked sites as a graph tab — the induced subgraph over
  // every node belonging to a bookmarked seed's host.
  function onOpenBookmarksAsTab(): void {
    const hosts = [
      ...new Set(
        filtered
          .map((s) => hostFromUrl(s.url))
          .filter((h): h is string => h !== null),
      ),
    ];
    if (hosts.length === 0) {
      toastStore.show('No bookmarked hosts to open.', 'info');
      return;
    }
    workspaceStore.openNodeSetTab({ kind: 'bookmarks', hosts }, 'Bookmarks');
  }

  function onRowContextMenu(s: Seed, event: MouseEvent): void {
    const target: RowMenuTarget = {
      url: s.url,
      node: nodeForSeed(s),
      inCollection: false,
    };
    rowContextMenu.openAt(target, event);
  }
</script>

<section class="bookmarks">
  <header class="head">
    <input
      type="text"
      class="filter"
      placeholder="Filter URL or label…"
      bind:value={filter}
      aria-label="Filter bookmarks"
    />
    <span class="count" title="Filtered / total">
      {filtered.length}{filtered.length === seeds.length ? '' : ` / ${seeds.length}`}
    </span>
    <button
      type="button"
      class="icon"
      aria-label="Open bookmarks as graph tab"
      title="Open bookmarks as graph tab"
      onclick={onOpenBookmarksAsTab}
      disabled={filtered.length === 0}
    >
      <Network size={12} />
    </button>
    <button
      type="button"
      class="add"
      aria-expanded={addOpen}
      onclick={() => (addOpen = !addOpen)}
    >
      <Plus size={12} />
      Add bookmark
    </button>
  </header>

  {#if addOpen}
    <div class="add-row">
      <input
        type="text"
        placeholder="http://…onion/"
        bind:value={addUrl}
        onkeydown={(e) => {
          if (e.key === 'Enter') void onAddBookmark();
          if (e.key === 'Escape') (addOpen = false);
        }}
      />
      <input
        type="text"
        placeholder="Label (optional)"
        bind:value={addLabel}
        onkeydown={(e) => {
          if (e.key === 'Enter') void onAddBookmark();
        }}
      />
      <button type="button" class="save" disabled={saving} onclick={onAddBookmark}>
        {saving ? 'Saving…' : 'Save'}
      </button>
    </div>
  {/if}

  {#if !seedBookmarksStore.loaded}
    <p class="empty">Loading bookmarks…</p>
  {:else if seeds.length === 0}
    <p class="empty">No seed bookmarks yet — add one above.</p>
  {:else if filtered.length === 0}
    <p class="empty">No bookmarks match this filter.</p>
  {:else}
    <ul class="list">
      {#each filtered as s (s.url)}
        {@const host = hostFromUrl(s.url)}
        {@const visible = host ? domainVisibilityStore.isVisible(host) : true}
        {@const node = nodeForSeed(s)}
        {@const active =
          node !== undefined &&
          selectionStore.selectMode === 'full' &&
          selectionStore.selectedNodeId === node.id}
        <li class:editing={editingUrl === s.url}>
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
            onSelect={() => onSelect(s)}
            oncontextmenu={(e) => onRowContextMenu(s, e)}
          >
            <span class="label" title={s.label ?? '(unlabeled)'}>
              {s.label ?? '(unlabeled)'}
            </span>
            <span class="url" title={s.url}>{s.url}</span>
            <span class="date" title={s.added_at}>{formatAddedAt(s.added_at)}</span>
          </BottomPaneRow>
          <div class="row-actions">
            {#if editingUrl === s.url}
              <input
                class="rename"
                type="text"
                aria-label="Rename label"
                bind:value={editingDraft}
                onkeydown={onRenameKey}
                onblur={() => void commitRename()}
                placeholder="Label (blank to clear)"
              />
              <button
                type="button"
                class="icon ok"
                aria-label="Save label"
                title="Save (Enter)"
                onmousedown={(e) => e.preventDefault()}
                onclick={() => void commitRename()}
              >
                <Check size={12} />
              </button>
              <button
                type="button"
                class="icon"
                aria-label="Cancel rename"
                title="Cancel (Escape)"
                onmousedown={(e) => e.preventDefault()}
                onclick={cancelRename}
              >
                <X size={12} />
              </button>
            {:else}
              <button
                type="button"
                class="icon"
                aria-label="Send to Crawl"
                title="Send to Crawl"
                onclick={() => onSendToCrawl(s)}
              >
                <Send size={11} />
              </button>
              <button
                type="button"
                class="icon"
                aria-label="Rename label"
                title="Rename label"
                onclick={() => startRename(s)}
              >
                <Pencil size={11} />
              </button>
              <button
                type="button"
                class="icon danger"
                aria-label="Delete bookmark"
                title="Delete"
                onclick={() => void onDelete(s.url)}
              >
                <X size={12} />
              </button>
            {/if}
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .bookmarks {
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
  .add {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 4px 8px;
    font-size: 11px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .add:hover {
    border-color: var(--accent);
    color: var(--accent);
  }
  .add-row {
    display: flex;
    gap: 4px;
    border: 1px solid var(--border);
    padding: 6px;
  }
  .add-row input {
    flex: 1;
    min-width: 0;
    background: #17191f;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 4px 7px;
    font-size: 11px;
  }
  .add-row input:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .save {
    background: transparent;
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 4px 10px;
    font-size: 11px;
    cursor: pointer;
  }
  .save:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
  .empty {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
    padding: 6px 4px;
  }
  .list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .list li {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .list li :global(.row) {
    flex: 1 1 auto;
    min-width: 0;
  }
  .label {
    color: var(--text);
    font-size: 11px;
    margin-right: 6px;
  }
  .url {
    color: var(--muted);
    font-size: 10px;
    margin-right: 6px;
  }
  .date {
    color: var(--muted);
    font-size: 10px;
  }
  .row-actions {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    gap: 2px;
    padding-right: 2px;
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
  .icon.ok:hover {
    color: var(--accent);
    border-color: var(--accent);
  }
  .icon.danger:hover {
    color: #ff5577;
    border-color: #ff5577;
  }
  .rename {
    background: #17191f;
    border: 1px solid var(--accent);
    color: var(--text);
    padding: 2px 6px;
    font-size: 11px;
    width: 180px;
  }
  .rename:focus-visible {
    outline: none;
  }
  li.editing :global(.content) {
    /* While editing, keep the row from also full-selecting on stray
       click bubbles — the editor sits to the right with a heavier
       border, the body is non-interactive for this moment. */
    pointer-events: none;
  }
</style>
