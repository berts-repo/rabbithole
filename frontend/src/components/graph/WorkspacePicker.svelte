<script lang="ts">
  // Inline popover anchored under WorkspaceTabs' '+' button. Loads
  // collections on mount, calls reconcileCollections so cross-window
  // deletions surface before the analyst tries to open the gone row.
  // Click-outside + Escape close. Inline "+ New collection..." input.

  import { onMount } from 'svelte';
  import { Plus } from 'lucide-svelte';
  import {
    listCollections,
    createCollection,
    type Collection,
  } from '$lib/api';
  import { workspaceStore } from '$lib/stores/workspace.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';

  type Props = { onClose: () => void };
  const { onClose }: Props = $props();

  let collections = $state<Collection[]>([]);
  let loading = $state(true);
  let creating = $state(false);
  let newName = $state('');
  let newOpen = $state(false);
  let popoverEl: HTMLDivElement | null = $state(null);
  let newInputEl: HTMLInputElement | null = $state(null);

  onMount(async () => {
    try {
      const res = await listCollections();
      collections = res.collections;
      workspaceStore.reconcileCollections(res.collections);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'load failed';
      toastStore.show(`Collections: ${msg}`, 'error');
    } finally {
      loading = false;
    }
  });

  function onDocClick(e: MouseEvent) {
    if (!popoverEl) return;
    if (popoverEl.contains(e.target as Node)) return;
    onClose();
  }
  function onKeyDown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onClose();
    }
  }
  $effect(() => {
    document.addEventListener('click', onDocClick, true);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('click', onDocClick, true);
      document.removeEventListener('keydown', onKeyDown);
    };
  });

  function pick(c: Collection) {
    workspaceStore.openCollectionTab(c);
    onClose();
  }

  function startNew() {
    newOpen = true;
    queueMicrotask(() => newInputEl?.focus());
  }

  async function submitNew() {
    const name = newName.trim();
    if (!name || creating) return;
    creating = true;
    try {
      const created = await createCollection({ name });
      workspaceStore.openCollectionTab({
        id: created.id,
        name: created.name,
        description: null,
      });
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'create failed';
      toastStore.show(`New collection: ${msg}`, 'error');
    } finally {
      creating = false;
    }
  }
</script>

<div
  bind:this={popoverEl}
  class="popover"
  role="dialog"
  aria-label="Open collection workspace"
>
  <header class="head">Open collection</header>
  <div class="body">
    {#if loading}
      <p class="empty">Loading…</p>
    {:else if collections.length === 0}
      <p class="empty">No collections yet.</p>
    {:else}
      <ul class="list">
        {#each collections as c (c.id)}
          <li>
            <button type="button" class="row" onclick={() => pick(c)}>
              {c.name}
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </div>
  <footer class="foot">
    {#if newOpen}
      <form
        class="new"
        onsubmit={(e) => {
          e.preventDefault();
          void submitNew();
        }}
      >
        <input
          bind:this={newInputEl}
          bind:value={newName}
          type="text"
          placeholder="New collection name"
          maxlength={120}
          disabled={creating}
        />
        <button type="submit" disabled={creating || !newName.trim()}>
          Add
        </button>
      </form>
    {:else}
      <button type="button" class="add" onclick={startNew}>
        <Plus size={12} /> New collection…
      </button>
    {/if}
  </footer>
</div>

<style>
  .popover {
    position: absolute;
    top: 100%;
    left: 0;
    z-index: 50;
    min-width: 220px;
    max-width: 320px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
    display: flex;
    flex-direction: column;
    font-size: 12px;
    margin-top: 2px;
  }
  .head {
    padding: 6px 10px;
    color: var(--muted);
    font-size: 10px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    border-bottom: 1px solid var(--border);
  }
  .body {
    max-height: 240px;
    overflow-y: auto;
  }
  .empty {
    margin: 0;
    padding: 10px;
    color: var(--muted);
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .row {
    width: 100%;
    text-align: left;
    background: transparent;
    border: none;
    color: var(--text);
    padding: 6px 10px;
    cursor: pointer;
    font: inherit;
  }
  .row:hover {
    background: var(--accent-bg-subtle, rgba(0, 212, 170, 0.08));
    color: var(--accent);
  }
  .foot {
    border-top: 1px solid var(--border);
    padding: 6px;
  }
  .add {
    background: transparent;
    border: none;
    color: var(--muted);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font: inherit;
    padding: 4px;
  }
  .add:hover {
    color: var(--accent);
  }
  .new {
    display: flex;
    gap: 4px;
  }
  .new input {
    flex: 1;
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 3px 6px;
    font: inherit;
    border-radius: 3px;
  }
  .new input:focus {
    outline: none;
    border-color: var(--accent);
  }
  .new button {
    background: transparent;
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 3px 8px;
    border-radius: 3px;
    cursor: pointer;
    font: inherit;
  }
  .new button:disabled {
    opacity: 0.4;
    cursor: default;
  }
</style>
