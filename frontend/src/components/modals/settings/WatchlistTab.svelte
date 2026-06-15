<script lang="ts">
  // Settings → Watchlist. Literal-term watchlist CRUD (add / edit / delete).
  // A live Focused crawl rebuilds its Aho-Corasick automaton off the
  // backend's watchlist.changed event, so edits here take effect without a
  // restart. Each row autosaves: add commits on Enter/＋, edit on Save,
  // delete immediately.

  import { onMount } from 'svelte';
  import { Check, Pencil, Plus, X } from 'lucide-svelte';
  import {
    addWatchlistTerm,
    ApiError,
    deleteWatchlistTerm,
    listWatchlist,
    updateWatchlistTerm,
    type WatchlistTerm,
  } from '$lib/api';
  import { toastStore } from '$lib/stores/toast.svelte';

  let terms = $state<WatchlistTerm[]>([]);
  let loaded = $state(false);
  let loadError = $state<string | null>(null);

  let draft = $state('');
  let saving = $state(false);

  // id of the row being edited, plus its working value.
  let editingId = $state<number | null>(null);
  let editValue = $state('');

  onMount(() => void load());

  async function load(): Promise<void> {
    loadError = null;
    try {
      terms = (await listWatchlist()).terms;
      loaded = true;
    } catch (err) {
      loadError = err instanceof Error ? err.message : String(err);
    }
  }

  function errMsg(err: unknown): string {
    if (err instanceof ApiError) {
      const body = err.body as { message?: string } | undefined;
      return body?.message ?? err.message;
    }
    return err instanceof Error ? err.message : String(err);
  }

  async function onAdd(): Promise<void> {
    const term = draft.trim();
    if (!term || saving) return;
    saving = true;
    try {
      const row = await addWatchlistTerm({ term });
      terms = [...terms, row];
      draft = '';
    } catch (err) {
      toastStore.show(`Add failed: ${errMsg(err)}`, 'error');
    } finally {
      saving = false;
    }
  }

  function startEdit(row: WatchlistTerm): void {
    editingId = row.id;
    editValue = row.term;
  }

  function cancelEdit(): void {
    editingId = null;
    editValue = '';
  }

  async function commitEdit(id: number): Promise<void> {
    const term = editValue.trim();
    if (!term) {
      toastStore.show('Term cannot be empty.', 'warn');
      return;
    }
    try {
      const row = await updateWatchlistTerm(id, { term });
      terms = terms.map((t) => (t.id === id ? row : t));
      cancelEdit();
    } catch (err) {
      toastStore.show(`Save failed: ${errMsg(err)}`, 'error');
    }
  }

  async function onDelete(id: number): Promise<void> {
    try {
      await deleteWatchlistTerm(id);
      terms = terms.filter((t) => t.id !== id);
      if (editingId === id) cancelEdit();
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        terms = terms.filter((t) => t.id !== id);
      } else {
        toastStore.show(`Delete failed: ${errMsg(err)}`, 'error');
      }
    }
  }
</script>

<div class="tab">
  <p class="hint">
    Literal terms, matched case-insensitively by the crawl runtime. A live
    Focused crawl picks up edits without a restart.
  </p>

  {#if loadError}
    <p class="empty error">{loadError}</p>
  {:else if !loaded}
    <p class="empty">Loading…</p>
  {:else if terms.length === 0}
    <p class="empty">No watch terms yet.</p>
  {:else}
    <ul class="list">
      {#each terms as row (row.id)}
        <li>
          {#if editingId === row.id}
            <input
              class="edit"
              type="text"
              bind:value={editValue}
              aria-label="Edit term"
              onkeydown={(e) => {
                if (e.key === 'Enter') void commitEdit(row.id);
                else if (e.key === 'Escape') cancelEdit();
              }}
            />
            <button
              type="button"
              class="icon"
              aria-label="Save"
              title="Save"
              onclick={() => void commitEdit(row.id)}
            >
              <Check size={13} />
            </button>
            <button
              type="button"
              class="icon"
              aria-label="Cancel"
              title="Cancel"
              onclick={cancelEdit}
            >
              <X size={13} />
            </button>
          {:else}
            <span class="term" title={row.term}>{row.term}</span>
            <button
              type="button"
              class="icon"
              aria-label={`Edit "${row.term}"`}
              title="Edit"
              onclick={() => startEdit(row)}
            >
              <Pencil size={12} />
            </button>
            <button
              type="button"
              class="icon danger"
              aria-label={`Delete "${row.term}"`}
              title="Delete"
              onclick={() => void onDelete(row.id)}
            >
              <X size={13} />
            </button>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}

  <div class="add-row">
    <input
      type="text"
      placeholder="Add a watch term…"
      bind:value={draft}
      aria-label="New watch term"
      disabled={saving}
      onkeydown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          void onAdd();
        }
      }}
    />
    <button
      type="button"
      class="add"
      onclick={() => void onAdd()}
      disabled={saving || draft.trim().length === 0}
    >
      <Plus size={12} />
      Add
    </button>
  </div>
</div>

<style>
  .tab {
    display: flex;
    flex-direction: column;
    gap: 8px;
    font-size: 12px;
  }
  .hint {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
  }
  .empty {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
    padding: 4px 0;
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
    padding: 3px 4px;
    border-radius: 2px;
  }
  .list li:hover {
    background: rgba(0, 212, 170, 0.06);
  }
  .term {
    flex: 1 1 auto;
    min-width: 0;
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .edit {
    flex: 1 1 auto;
    min-width: 0;
    background: #17191f;
    border: 1px solid var(--accent);
    color: var(--text);
    padding: 3px 6px;
    font: inherit;
    font-size: 12px;
    border-radius: 3px;
  }
  .edit:focus-visible {
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
  .icon.danger:hover:not(:disabled) {
    color: #ff5577;
    border-color: #ff5577;
  }
  .add-row {
    display: flex;
    gap: 4px;
    border-top: 1px solid var(--border);
    padding-top: 8px;
  }
  .add-row input {
    flex: 1;
    min-width: 0;
    background: #17191f;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 5px 7px;
    font-size: 12px;
  }
  .add-row input:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .add-row input:disabled {
    opacity: 0.6;
  }
  .add {
    background: transparent;
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 5px 10px;
    font-size: 11px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .add:hover:not(:disabled) {
    background: rgba(0, 212, 170, 0.1);
  }
  .add:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
</style>
