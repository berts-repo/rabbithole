<script lang="ts">
  // Collection sub-tab — Phase 1.5. Driven by the active workspace tab.
  // When the analyst is on the Global workspace, this tab shows a
  // pointer to open one; when they're on a collection workspace, it
  // loads that collection's items and surfaces rename / export / delete
  // for the whole collection plus per-row visibility + full-select.
  //
  // Backend already does the heavy lifting:
  //   GET    /api/collections/:id            → name + items (joined)
  //   PATCH  /api/collections/:id            → rename (and description)
  //   DELETE /api/collections/:id            → delete (cascades items)
  //   GET    /api/collections/:id/export?…   → JSON / CSV / GEXF download
  //
  // Selection model (CLAUDE.md): row click = full select. Item rows
  // carry their node id so the right-panel and graph highlight resolve
  // directly; stub rows still full-select (the node exists; it's just
  // un-crawled), and the canvas renders it hollow.
  //
  // The ●/○ dot toggles the row's host in domainVisibilityStore — same
  // store + scope as Bookmarks. Stub rows whose URL has no parseable
  // host render the dot disabled.

  import { ChevronDown, Pencil, Send, Trash2, X, Check } from 'lucide-svelte';
  import {
    ApiError,
    collectionExportUrl,
    deleteCollection,
    getCollection,
    patchCollection,
    removeItemFromCollection,
    type CollectionDetail,
    type CollectionExportFormat,
    type CollectionItem,
    type GraphNode,
  } from '$lib/api';
  import { batchConfirmStore } from '$lib/stores/batchConfirm.svelte';
  import { domainVisibilityStore } from '$lib/stores/domainVisibility.svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { navigationStore } from '$lib/stores/navigation.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { workspaceStore } from '$lib/stores/workspace.svelte';
  import Modal from '../../components/modals/Modal.svelte';
  import BottomPaneRow from './BottomPaneRow.svelte';
  import {
    rowContextMenu,
    type RowMenuTarget,
  } from '$lib/contextMenu/rowMenu.svelte';
  import { countStubs, filterItems, stubUrls } from './collection';
  import { isUncrawled, stateLabel } from '$lib/nodeState';

  // Per-collection-id cache. Switching workspaces keeps the previously-
  // loaded collection in memory so a quick back-and-forth doesn't re-
  // fetch; an explicit refresh after rename / delete invalidates.
  let cache = $state<Map<number, CollectionDetail>>(new Map());
  let loading = $state(false);
  let loadError = $state<string | null>(null);
  // Tracks which collection id was last fetched so an in-flight load
  // that completes after a workspace switch can discard its result.
  let inFlightId = $state<number | null>(null);

  let filter = $state('');

  // Inline rename — guard against the editor opening on a tab that
  // wasn't loaded yet; the rename ✎ button only enables when detail
  // resolved.
  let renaming = $state(false);
  let renameDraft = $state('');
  let renameSaving = $state(false);

  // Export dropdown open state. Closes on outside click + Escape.
  let exportOpen = $state(false);

  // Delete confirmation modal state.
  let deleteOpen = $state(false);
  let deleting = $state(false);

  const activeCollectionId = $derived(workspaceStore.activeCollectionId());
  const detail = $derived<CollectionDetail | null>(
    activeCollectionId !== null ? (cache.get(activeCollectionId) ?? null) : null,
  );
  const items = $derived<CollectionItem[]>(detail?.items ?? []);
  const filtered = $derived(filterItems(items, filter));
  const stubCount = $derived(countStubs(items));

  // id → GraphNode lookup for the right-click menu. The collection
  // payload stores enough to render the row, but the shared menu reads
  // alias / flag_status / reviewed off a real GraphNode — pull it from
  // graphStore so id-bound items get the full picture.
  const nodeById = $derived.by<Map<number, GraphNode>>(() => {
    const map = new Map<number, GraphNode>();
    const nodes = graphStore.payload?.nodes;
    if (!nodes) return map;
    for (const n of nodes) map.set(n.id, n);
    return map;
  });

  // Whenever the active collection id changes, fetch fresh detail —
  // unless it's already cached. A rename/delete invalidates the cache
  // for the affected id so the next select reloads.
  $effect(() => {
    const cid = activeCollectionId;
    if (cid === null) {
      loadError = null;
      return;
    }
    if (cache.has(cid)) {
      // Background refresh? Not for v1 — a workspace tab switch is the
      // analyst's signal that they expect what they last saw.
      return;
    }
    void load(cid);
  });

  // Reset any per-collection editor state when the active workspace
  // changes — leaving the rename input open while switching collections
  // would mutate the wrong row on commit.
  $effect(() => {
    // Reading activeCollectionId here registers the dependency.
    activeCollectionId;
    renaming = false;
    renameDraft = '';
    exportOpen = false;
    deleteOpen = false;
    filter = '';
  });

  async function load(cid: number): Promise<void> {
    loading = true;
    loadError = null;
    inFlightId = cid;
    try {
      const fresh = await getCollection(cid);
      // Ignore stale responses — the analyst may have switched tabs
      // since the request went out.
      if (inFlightId !== cid) return;
      const next = new Map(cache);
      next.set(cid, fresh);
      cache = next;
    } catch (err) {
      if (inFlightId !== cid) return;
      if (err instanceof ApiError && err.status === 404) {
        // The collection vanished out from under us — close its
        // workspace tab so the active state stays consistent.
        loadError = 'This collection no longer exists.';
        workspaceStore.closeTab(workspaceStore.tabId(cid));
      } else {
        loadError = err instanceof Error ? err.message : String(err);
      }
    } finally {
      if (inFlightId === cid) {
        loading = false;
        inFlightId = null;
      }
    }
  }

  function invalidate(cid: number): void {
    if (!cache.has(cid)) return;
    const next = new Map(cache);
    next.delete(cid);
    cache = next;
  }

  function startRename(): void {
    if (!detail) return;
    renameDraft = detail.name;
    renaming = true;
  }

  function cancelRename(): void {
    renaming = false;
    renameDraft = '';
  }

  async function commitRename(): Promise<void> {
    if (!detail || renameSaving) return;
    const cid = detail.id;
    const next = renameDraft.trim();
    if (!next) {
      toastStore.show('Collection name cannot be empty.', 'warn');
      return;
    }
    if (next === detail.name) {
      cancelRename();
      return;
    }
    renameSaving = true;
    try {
      const updated = await patchCollection(cid, { name: next });
      const merged = new Map(cache);
      const prior = merged.get(cid);
      if (prior) merged.set(cid, { ...prior, name: updated.name });
      cache = merged;
      workspaceStore.renameTab(workspaceStore.tabId(cid), updated.name);
      toastStore.show('Collection renamed.', 'info');
      renaming = false;
      renameDraft = '';
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toastStore.show('Another collection already has that name.', 'warn');
      } else {
        const msg = err instanceof Error ? err.message : String(err);
        toastStore.show(`Rename failed: ${msg}`, 'error');
      }
    } finally {
      renameSaving = false;
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

  function onExport(format: CollectionExportFormat): void {
    if (!detail) return;
    const url = collectionExportUrl(detail.id, format);
    // Same-origin GET — let the browser handle Content-Disposition.
    // Using a hidden anchor keeps things in this tab (window.open
    // momentarily flashes a tab on some platforms).
    const a = document.createElement('a');
    a.href = url;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    a.remove();
    exportOpen = false;
  }

  function openDelete(): void {
    if (!detail) return;
    deleteOpen = true;
  }

  async function confirmDelete(): Promise<void> {
    if (!detail || deleting) return;
    const cid = detail.id;
    const name = detail.name;
    deleting = true;
    try {
      await deleteCollection(cid);
      invalidate(cid);
      // Closing the workspace tab also flips activeWorkspaceId back to
      // 'global', which fires the $effect above and clears editor state.
      workspaceStore.closeTab(workspaceStore.tabId(cid));
      toastStore.show(`Collection "${name}" deleted.`, 'info');
      deleteOpen = false;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toastStore.show(`Delete failed: ${msg}`, 'error');
    } finally {
      deleting = false;
    }
  }

  function onSendAllUncrawled(): void {
    if (!detail) return;
    const urls = stubUrls(detail.items);
    if (urls.length === 0) {
      toastStore.show('No uncrawled items in this collection.', 'info');
      return;
    }
    navigationStore.setLeft('crawl');
    batchConfirmStore.stage({
      source: 'collection',
      sourceLabel: detail.name,
      urls,
      defaultsOverride: { collectionId: detail.id, collectionNamePending: null },
    });
    toastStore.show(
      `Staged ${urls.length} URL${urls.length === 1 ? '' : 's'} in Crawl tab.`,
      'info',
    );
  }

  function onSelect(it: CollectionItem): void {
    selectionStore.fullSelect(it.id);
  }

  function onRowContextMenu(it: CollectionItem, event: MouseEvent): void {
    if (!detail) return;
    const cid = detail.id;
    const target: RowMenuTarget = {
      url: it.url,
      node: nodeById.get(it.id),
      inCollection: true,
      onRemoveFromCollection: async () => {
        try {
          await removeItemFromCollection(cid, it.id);
          invalidate(cid);
          void load(cid);
          toastStore.show('Removed from collection.', 'info');
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          toastStore.show(`Remove failed: ${msg}`, 'error');
        }
      },
    };
    rowContextMenu.openAt(target, event);
  }

  // Close the export dropdown on outside click. Bound to the window so a
  // click on any element that isn't the dropdown itself dismisses it.
  function onDocumentClick(e: MouseEvent): void {
    if (!exportOpen) return;
    const t = e.target as HTMLElement | null;
    if (!t || !t.closest('.export-wrap')) {
      exportOpen = false;
    }
  }

  function onDocumentKey(e: KeyboardEvent): void {
    if (e.key === 'Escape' && exportOpen) exportOpen = false;
  }
</script>

<svelte:window onclick={onDocumentClick} onkeydown={onDocumentKey} />

<section class="collection">
  {#if activeCollectionId === null}
    <p class="empty">Open a collection workspace tab to view its contents.</p>
  {:else if loadError}
    <p class="empty error">{loadError}</p>
  {:else if !detail && loading}
    <p class="empty">Loading collection…</p>
  {:else if detail}
    <header class="head">
      {#if renaming}
        <input
          type="text"
          class="rename"
          aria-label="Rename collection"
          bind:value={renameDraft}
          onkeydown={onRenameKey}
          onblur={() => {
            if (!renameSaving) void commitRename();
          }}
          disabled={renameSaving}
        />
        <button
          type="button"
          class="icon ok"
          aria-label="Save name"
          title="Save (Enter)"
          onmousedown={(e) => e.preventDefault()}
          onclick={() => void commitRename()}
          disabled={renameSaving}
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
          disabled={renameSaving}
        >
          <X size={12} />
        </button>
      {:else}
        <span class="name" title={detail.name}>{detail.name}</span>
        <button
          type="button"
          class="icon"
          aria-label="Rename collection"
          title="Rename"
          onclick={startRename}
        >
          <Pencil size={11} />
        </button>
        <div class="export-wrap">
          <button
            type="button"
            class="icon"
            aria-label="Export collection"
            aria-haspopup="menu"
            aria-expanded={exportOpen}
            title="Export"
            onclick={(e) => {
              e.stopPropagation();
              exportOpen = !exportOpen;
            }}
          >
            <ChevronDown size={11} />
          </button>
          {#if exportOpen}
            <ul class="export-menu" role="menu" aria-label="Export format">
              <li>
                <button type="button" role="menuitem" onclick={() => onExport('json')}>
                  JSON
                </button>
              </li>
              <li>
                <button type="button" role="menuitem" onclick={() => onExport('csv')}>
                  Nodes CSV
                </button>
              </li>
              <li>
                <button type="button" role="menuitem" onclick={() => onExport('gexf')}>
                  GEXF
                </button>
              </li>
            </ul>
          {/if}
        </div>
        <button
          type="button"
          class="icon danger"
          aria-label="Delete collection"
          title="Delete"
          onclick={openDelete}
        >
          <Trash2 size={11} />
        </button>
      {/if}
    </header>

    <div class="controls">
      <input
        type="text"
        class="filter"
        placeholder="Filter URL, title, or domain…"
        bind:value={filter}
        aria-label="Filter collection items"
      />
      <span class="count" title="Filtered / total">
        {filtered.length}{filtered.length === items.length ? '' : ` / ${items.length}`}
      </span>
      {#if stubCount > 0}
        <button
          type="button"
          class="send-all"
          title="Stage every uncrawled URL in Crawl"
          onclick={onSendAllUncrawled}
        >
          <Send size={11} />
          Send to Crawl ({stubCount})
        </button>
      {/if}
    </div>

    {#if items.length === 0}
      <p class="empty">No items in this collection.</p>
    {:else if filtered.length === 0}
      <p class="empty">No items match this filter.</p>
    {:else}
      <ul class="list">
        {#each filtered as it (it.id)}
          {@const visible = it.domain
            ? domainVisibilityStore.isVisible(it.domain)
            : true}
          {@const active =
            selectionStore.selectMode === 'full' &&
            selectionStore.selectedNodeId === it.id}
          <li>
            <BottomPaneRow
              visible={visible}
              active={active}
              visibilityLabel={it.domain
                ? visible
                  ? `Hide ${it.domain}`
                  : `Show ${it.domain}`
                : 'No host'}
              onToggleVisibility={() => {
                if (!it.domain) return;
                domainVisibilityStore.toggle(it.domain);
              }}
              onSelect={() => onSelect(it)}
              oncontextmenu={(e) => onRowContextMenu(it, e)}
            >
              <span class="url" title={it.url}>{it.url}</span>
              {#if isUncrawled(it)}
                <span class="uncrawled-badge" title="Page not yet crawled">
                  {stateLabel(it.state)}
                </span>
              {:else if it.title}
                <span class="title" title={it.title}>{it.title}</span>
              {:else}
                <span class="title placeholder">(no title)</span>
              {/if}
            </BottomPaneRow>
          </li>
        {/each}
      </ul>
    {/if}
  {/if}
</section>

{#if deleteOpen && detail}
  <Modal
    title="Delete collection"
    confirmLabel="Delete"
    busy={deleting}
    onClose={() => {
      if (!deleting) deleteOpen = false;
    }}
    onConfirm={() => void confirmDelete()}
  >
    <p class="hint">
      Delete "{detail.name}"? This cannot be undone. The collection's
      member nodes are unaffected — only the collection itself and its
      memberships are removed.
    </p>
  </Modal>
{/if}

<style>
  .collection {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-height: 0;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .name {
    flex: 1 1 auto;
    min-width: 0;
    color: var(--text);
    font-size: 12px;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .rename {
    flex: 1 1 auto;
    min-width: 0;
    background: #17191f;
    border: 1px solid var(--accent);
    color: var(--text);
    padding: 3px 7px;
    font-size: 12px;
  }
  .rename:focus-visible {
    outline: none;
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
  .icon.ok:hover:not(:disabled) {
    color: var(--accent);
    border-color: var(--accent);
  }
  .icon.danger:hover:not(:disabled) {
    color: #ff5577;
    border-color: #ff5577;
  }
  .icon:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
  .export-wrap {
    position: relative;
    display: inline-flex;
  }
  .export-menu {
    position: absolute;
    top: 100%;
    left: 0;
    margin: 2px 0 0 0;
    padding: 2px 0;
    list-style: none;
    background: var(--bg);
    border: 1px solid var(--border);
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.45);
    z-index: 10;
    min-width: 120px;
  }
  .export-menu li {
    display: block;
  }
  .export-menu button {
    background: transparent;
    border: none;
    color: var(--text);
    font-size: 11px;
    padding: 5px 10px;
    width: 100%;
    text-align: left;
    cursor: pointer;
  }
  .export-menu button:hover {
    background: rgba(0, 212, 170, 0.12);
    color: var(--accent);
  }
  .controls {
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
  .send-all {
    background: transparent;
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 4px 8px;
    font-size: 11px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    white-space: nowrap;
  }
  .send-all:hover {
    background: rgba(0, 212, 170, 0.1);
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
  .list li {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .list li :global(.row) {
    flex: 1 1 auto;
    min-width: 0;
  }
  .url {
    color: var(--text);
    font-size: 11px;
    margin-right: 6px;
  }
  .title {
    color: var(--muted);
    font-size: 10px;
  }
  .title.placeholder {
    font-style: italic;
  }
  .uncrawled-badge {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 8px;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #1a1306;
    background: #ffb347;
  }
</style>
