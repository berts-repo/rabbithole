<script lang="ts">
  // Cluster workspace — Nodes tab (default).
  //
  // Managed list of every node in the current cluster selection. Per
  // spec, this is where the analyst sees what's actually selected and
  // performs cluster-wide intake actions:
  //
  //   - ✕ removes a node from the selection. Dropping to 1 node flips
  //     selectMode back to 'highlight' inside the store, which snaps
  //     the right panel back to its single-node view.
  //   - Add to collection: collection picker, adds every selected node
  //     (uncrawled included).
  //   - Save as new collection: name-input popover, creates collection
  //     then adds all.
  //   - Send to Crawl: stages every URL in the BatchConfirmStrip and
  //     flips the left pane to Crawl. Works regardless of crawl state.
  //
  // Spec: docs/specs/right-pane.md:355-366.

  import { X } from 'lucide-svelte';
  import {
    addItemsToCollection,
    ApiError,
    createCollection,
    listCollections,
    type Collection,
  } from '$lib/api';
  import { batchConfirmStore } from '$lib/stores/batchConfirm.svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { navigationStore } from '$lib/stores/navigation.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import {
    fetchMissingNodes,
    resolveFromPayload,
    type NodeBag,
  } from './nodeBag';

  // ---------------- Selection → bag resolution ----------------

  let bag = $state<NodeBag>(new Map());
  let resolvingMissing = $state(false);
  let resolveGen = 0;

  // Re-resolve whenever the selected set changes. Resolution is cheap
  // when ids live in graphStore.payload; only the misses cost a fetch.
  $effect(() => {
    const ids = Array.from(selectionStore.selectedIds);
    const gen = ++resolveGen;
    const { resolved, missing } = resolveFromPayload(ids, graphStore.payload);
    bag = resolved;
    if (missing.length === 0) return;
    resolvingMissing = true;
    void fetchMissingNodes(missing).then((extra) => {
      if (gen !== resolveGen) return;
      // Merge — keep the live payload entries authoritative.
      const merged: NodeBag = new Map(bag);
      for (const [id, entry] of extra) {
        if (!merged.has(id)) merged.set(id, entry);
      }
      bag = merged;
      resolvingMissing = false;
    });
  });

  // Stable ordering: graph payload order first, then any merged-in
  // misses in id order. The selectionStore set has no guaranteed
  // iteration order so this keeps the list from reshuffling on add.
  let orderedRows = $derived.by(() => {
    const ids = Array.from(selectionStore.selectedIds);
    return ids
      .map((id) => bag.get(id) ?? { id, url: `#${id}`, uncrawled: false, domain: null })
      .sort((a, b) => a.id - b.id);
  });

  let crawledCount = $derived(
    orderedRows.filter((r) => !r.uncrawled).length,
  );
  let uncrawledCount = $derived(orderedRows.length - crawledCount);

  // ---------------- Remove ----------------

  function removeRow(id: number): void {
    selectionStore.deselect(id);
  }

  // ---------------- Add to collection ----------------

  let pickerOpen = $state(false);
  let pickerLoading = $state(false);
  let pickerError = $state<string | null>(null);
  let collectionsCache = $state<Collection[] | null>(null);
  let addBusy = $state(false);

  async function openPicker(): Promise<void> {
    pickerOpen = true;
    if (collectionsCache !== null) return;
    pickerLoading = true;
    pickerError = null;
    try {
      const res = await listCollections();
      collectionsCache = res.collections;
    } catch (err) {
      pickerError = explainError(err, 'Load failed');
    } finally {
      pickerLoading = false;
    }
  }

  function closePicker(): void {
    pickerOpen = false;
  }

  async function addAllToCollection(c: Collection): Promise<void> {
    if (addBusy) return;
    addBusy = true;
    try {
      const ids = orderedRows.map((r) => r.id);
      const res = await addItemsToCollection(c.id, ids);
      const msg = `Added ${res.added} to ${c.name}${
        res.skipped > 0 ? ` (${res.skipped} already in)` : ''
      }`;
      toastStore.show(msg);
      closePicker();
    } catch (err) {
      toastStore.show(explainError(err, 'Add failed'), 'error');
    } finally {
      addBusy = false;
    }
  }

  // ---------------- Save as new collection ----------------

  let newCollectionOpen = $state(false);
  let newCollectionName = $state('');
  let newCollectionBusy = $state(false);

  function openNewCollection(): void {
    newCollectionName = '';
    newCollectionOpen = true;
  }
  function closeNewCollection(): void {
    newCollectionOpen = false;
  }

  async function saveAsNewCollection(): Promise<void> {
    const name = newCollectionName.trim();
    if (!name || newCollectionBusy) return;
    newCollectionBusy = true;
    try {
      const created = await createCollection({ name });
      const ids = orderedRows.map((r) => r.id);
      const res = await addItemsToCollection(created.id, ids);
      // Refresh the picker cache so the new collection appears in the
      // dropdown next time the analyst opens it.
      collectionsCache = null;
      toastStore.show(
        `Created "${created.name}" with ${res.added} node${res.added === 1 ? '' : 's'}`,
      );
      closeNewCollection();
    } catch (err) {
      toastStore.show(explainError(err, 'Create collection failed'), 'error');
    } finally {
      newCollectionBusy = false;
    }
  }

  // ---------------- Send to Crawl ----------------

  function sendToCrawl(): void {
    if (orderedRows.length === 0) return;
    batchConfirmStore.stage({
      source: 'right_pane',
      sourceLabel: `Cluster selection (${orderedRows.length})`,
      urls: orderedRows.map((r) => r.url),
    });
    navigationStore.setLeft('crawl');
    toastStore.show(
      `Staged ${orderedRows.length} URL${orderedRows.length === 1 ? '' : 's'} in Crawl tab.`,
    );
  }

  // ---------------- Helpers ----------------

  function explainError(err: unknown, fallback: string): string {
    if (err instanceof ApiError) return `${fallback}: ${err.message}`;
    if (err instanceof Error) return `${fallback}: ${err.message}`;
    return fallback;
  }
</script>

<div class="root">
  <header class="head">
    <span class="block-label">Selected ({orderedRows.length})</span>
    <span class="counts">
      {crawledCount} crawled{uncrawledCount > 0 ? ` · ${uncrawledCount} uncrawled` : ''}
    </span>
  </header>

  {#if orderedRows.length === 0}
    <p class="empty">No nodes selected.</p>
  {:else}
    <ul class="rows">
      {#each orderedRows as r (r.id)}
        <li class="row">
          <a class="row-url" href={r.url} target="_blank" rel="noreferrer">
            {r.url}
          </a>
          {#if r.uncrawled}
            <span class="uncrawled-badge">uncrawled</span>
          {/if}
          <button
            type="button"
            class="row-remove"
            aria-label="Remove from selection"
            onclick={() => removeRow(r.id)}
          >
            <X size={11} />
          </button>
        </li>
      {/each}
    </ul>

    {#if resolvingMissing}
      <p class="hint">Resolving {selectionStore.selectedIds.size - bag.size} nodes…</p>
    {/if}

    <div class="actions">
      <button type="button" class="action" onclick={openPicker}>
        Add to collection
      </button>
      <button type="button" class="action" onclick={openNewCollection}>
        Save as new collection
      </button>
      <button type="button" class="action primary" onclick={sendToCrawl}>
        Send to Crawl
      </button>
    </div>

    {#if pickerOpen}
      <div class="picker">
        <div class="picker-head">
          <span class="block-label">Pick a collection</span>
          <button
            type="button"
            class="picker-close"
            aria-label="Close"
            onclick={closePicker}
          >
            <X size={10} />
          </button>
        </div>
        {#if pickerLoading}
          <p class="empty">Loading…</p>
        {:else if pickerError}
          <p class="empty error">{pickerError}</p>
        {:else if (collectionsCache ?? []).length === 0}
          <p class="empty">No collections yet. Use "Save as new collection."</p>
        {:else}
          {#each collectionsCache ?? [] as c (c.id)}
            <button
              type="button"
              class="picker-row"
              disabled={addBusy}
              onclick={() => addAllToCollection(c)}
            >
              {c.name}
            </button>
          {/each}
        {/if}
      </div>
    {/if}

    {#if newCollectionOpen}
      <div class="picker">
        <div class="picker-head">
          <span class="block-label">New collection</span>
          <button
            type="button"
            class="picker-close"
            aria-label="Close"
            onclick={closeNewCollection}
          >
            <X size={10} />
          </button>
        </div>
        <!-- svelte-ignore a11y_autofocus -->
        <input
          type="text"
          class="new-input"
          placeholder="Collection name"
          bind:value={newCollectionName}
          onkeydown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              void saveAsNewCollection();
            } else if (e.key === 'Escape') {
              closeNewCollection();
            }
          }}
          autofocus
        />
        <button
          type="button"
          class="action primary"
          onclick={saveAsNewCollection}
          disabled={!newCollectionName.trim() || newCollectionBusy}
        >
          Create + add {orderedRows.length}
        </button>
      </div>
    {/if}
  {/if}
</div>

<style>
  .root {
    display: flex;
    flex-direction: column;
    gap: 10px;
    font-size: 11px;
    color: var(--text);
  }
  .head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }
  .block-label {
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .counts {
    color: var(--muted);
    font-size: 10px;
  }
  .empty {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
    font-style: italic;
  }
  .empty.error {
    color: #ff6b6b;
    font-style: normal;
  }
  .hint {
    margin: 0;
    color: var(--muted);
    font-size: 10px;
    font-style: italic;
  }

  .rows {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    border: 1px solid var(--border);
    border-radius: 2px;
    max-height: 240px;
    overflow-y: auto;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 6px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  }
  .row:last-child {
    border-bottom: none;
  }
  .row-url {
    flex: 1;
    color: var(--text);
    font-size: 11px;
    word-break: break-all;
    text-decoration: none;
  }
  .row-url:hover {
    color: var(--accent);
    text-decoration: underline;
  }
  .uncrawled-badge {
    padding: 1px 6px;
    border: 1px solid #b08a3a;
    border-radius: 8px;
    color: #e0b860;
    font-size: 9px;
    text-transform: uppercase;
  }
  .row-remove {
    background: transparent;
    border: none;
    color: var(--muted);
    cursor: pointer;
    padding: 0;
    line-height: 0;
  }
  .row-remove:hover {
    color: #ff6b6b;
  }

  .actions {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .action {
    padding: 6px 10px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 2px;
    color: var(--muted);
    font-size: 11px;
    cursor: pointer;
  }
  .action:hover {
    color: var(--accent);
    border-color: var(--accent);
  }
  .action.primary {
    background: rgba(0, 212, 170, 0.12);
    border-color: var(--accent);
    color: var(--accent);
  }
  .action.primary:hover {
    background: rgba(0, 212, 170, 0.2);
  }
  .action.primary:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .picker {
    display: flex;
    flex-direction: column;
    gap: 4px;
    border: 1px solid var(--border);
    border-radius: 2px;
    background: rgba(10, 15, 13, 0.97);
    padding: 6px;
  }
  .picker-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .picker-close {
    background: transparent;
    border: none;
    color: var(--muted);
    cursor: pointer;
    padding: 0;
    line-height: 0;
  }
  .picker-close:hover {
    color: var(--accent);
  }
  .picker-row {
    text-align: left;
    background: transparent;
    border: none;
    color: var(--text);
    font-size: 11px;
    padding: 4px 8px;
    cursor: pointer;
    border-radius: 2px;
  }
  .picker-row:hover {
    background: rgba(0, 212, 170, 0.12);
  }
  .new-input {
    padding: 4px 6px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 2px;
    color: var(--text);
    font: inherit;
  }
  .new-input:focus {
    border-color: var(--accent);
    outline: none;
  }
</style>
