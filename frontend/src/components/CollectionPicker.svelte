<script lang="ts">
  // Shared collection chooser — a select listing every collection plus an
  // inline "+ New collection…" row that creates one without leaving the
  // surface. Used by the Add-to-Collection modal and the graph toolbar's
  // Expand-to-collection popover (PLAN.md backlog: "B7 collection picker
  // reuse"). The parent owns the chosen id via the value / onChange pair.

  import { listCollections, createCollection, type Collection } from '$lib/api';
  import { toastStore } from '$lib/stores/toast.svelte';

  interface Props {
    value: number | null;
    onChange: (id: number | null) => void;
  }

  let { value, onChange }: Props = $props();

  let collections = $state<Collection[]>([]);
  let creating = $state(false);
  let newName = $state('');
  let busy = $state(false);
  let newInputEl = $state<HTMLInputElement>();

  $effect(() => {
    void listCollections()
      .then((r) => {
        collections = r.collections;
      })
      .catch(() => {
        // Non-fatal — the analyst can still type a new collection name.
      });
  });

  function onSelect(e: Event): void {
    const v = (e.currentTarget as HTMLSelectElement).value;
    if (v === '__new__') {
      creating = true;
      queueMicrotask(() => newInputEl?.focus());
      return;
    }
    onChange(v === '' ? null : Number(v));
  }

  async function submitNew(): Promise<void> {
    const name = newName.trim();
    if (!name || busy) return;
    busy = true;
    try {
      const c = await createCollection({ name });
      collections = [
        { id: c.id, name: c.name, description: null },
        ...collections,
      ];
      onChange(c.id);
      creating = false;
      newName = '';
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Create collection failed: ${msg}`, 'error');
    } finally {
      busy = false;
    }
  }

  function cancelNew(): void {
    creating = false;
    newName = '';
  }
</script>

{#if creating}
  <div class="new">
    <input
      bind:this={newInputEl}
      bind:value={newName}
      type="text"
      placeholder="New collection name"
      onkeydown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          void submitNew();
        } else if (e.key === 'Escape') {
          e.stopPropagation();
          cancelNew();
        }
      }}
    />
    <button
      type="button"
      class="add"
      disabled={busy || !newName.trim()}
      onclick={() => void submitNew()}>Add</button
    >
  </div>
{:else}
  <select
    aria-label="Collection"
    value={value === null ? '' : String(value)}
    onchange={onSelect}
  >
    <option value="">— Select collection —</option>
    {#each collections as c (c.id)}
      <option value={String(c.id)}>{c.name}</option>
    {/each}
    <option value="__new__">+ New collection…</option>
  </select>
{/if}

<style>
  /* Self-contained controls so the picker looks right both inside a modal
     and in the graph toolbar's Expand popover. */
  select,
  .new input {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 3px;
    padding: 5px 7px;
    font-size: 12px;
  }
  select {
    width: 100%;
    cursor: pointer;
  }
  select:focus-visible,
  .new input:focus-visible {
    border-color: var(--accent);
  }
  .new {
    display: flex;
    gap: 6px;
  }
  .new input {
    flex: 1;
    min-width: 0;
  }
  .add {
    background: var(--accent);
    border: 1px solid var(--accent);
    color: var(--bg);
    font-size: 12px;
    font-weight: 600;
    padding: 0 12px;
    border-radius: 3px;
    cursor: pointer;
  }
  .add:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
