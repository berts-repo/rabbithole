<script lang="ts">
  // Settings → Engines. Search-engine registry CRUD (add / edit / delete)
  // plus a per-engine enabled toggle. The enabled flag is a separate
  // templated setting (search.engine.{id}.enabled), loaded alongside the
  // list and written on toggle. URLs must be v3 .onion with a {q}
  // placeholder — the backend re-validates, so a bad URL surfaces as a
  // toast rather than a silent save.

  import { onMount } from 'svelte';
  import { Check, Pencil, Plus, X } from 'lucide-svelte';
  import {
    ApiError,
    createEngine,
    deleteEngine,
    getEngineEnabled,
    listEngines,
    setEngineEnabled,
    updateEngine,
    type SearchEngine,
  } from '$lib/api';
  import { toastStore } from '$lib/stores/toast.svelte';

  let engines = $state<SearchEngine[]>([]);
  // id → enabled. Missing setting (null) defaults to enabled.
  let enabled = $state<Record<number, boolean>>({});
  let loaded = $state(false);
  let loadError = $state<string | null>(null);

  // Add form.
  let newLabel = $state('');
  let newUrl = $state('');
  let saving = $state(false);

  // Inline edit.
  let editingId = $state<number | null>(null);
  let editLabel = $state('');
  let editUrl = $state('');

  onMount(() => void load());

  async function load(): Promise<void> {
    loadError = null;
    try {
      const list = (await listEngines()).engines;
      const flags = await Promise.all(
        list.map((e) => getEngineEnabled(e.id).catch(() => null)),
      );
      const map: Record<number, boolean> = {};
      list.forEach((e, i) => {
        map[e.id] = flags[i]?.value !== 'false'; // null/true → enabled
      });
      engines = list;
      enabled = map;
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

  async function onToggle(id: number, value: boolean): Promise<void> {
    enabled = { ...enabled, [id]: value };
    try {
      await setEngineEnabled(id, value);
    } catch (err) {
      enabled = { ...enabled, [id]: !value }; // revert on failure
      toastStore.show(`Toggle failed: ${errMsg(err)}`, 'error');
    }
  }

  async function onAdd(): Promise<void> {
    const label = newLabel.trim();
    const url = newUrl.trim();
    if (!label || !url || saving) return;
    saving = true;
    try {
      const row = await createEngine({ label, url });
      engines = [...engines, row];
      enabled = { ...enabled, [row.id]: true };
      newLabel = '';
      newUrl = '';
    } catch (err) {
      toastStore.show(`Add failed: ${errMsg(err)}`, 'error');
    } finally {
      saving = false;
    }
  }

  function startEdit(row: SearchEngine): void {
    editingId = row.id;
    editLabel = row.label;
    editUrl = row.url;
  }

  function cancelEdit(): void {
    editingId = null;
    editLabel = '';
    editUrl = '';
  }

  async function commitEdit(id: number): Promise<void> {
    const label = editLabel.trim();
    const url = editUrl.trim();
    if (!label || !url) {
      toastStore.show('Label and URL are required.', 'warn');
      return;
    }
    try {
      const row = await updateEngine(id, { label, url });
      engines = engines.map((e) => (e.id === id ? row : e));
      cancelEdit();
    } catch (err) {
      toastStore.show(`Save failed: ${errMsg(err)}`, 'error');
    }
  }

  async function onDelete(id: number): Promise<void> {
    try {
      await deleteEngine(id);
      engines = engines.filter((e) => e.id !== id);
      if (editingId === id) cancelEdit();
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        engines = engines.filter((e) => e.id !== id);
      } else {
        toastStore.show(`Delete failed: ${errMsg(err)}`, 'error');
      }
    }
  }
</script>

<div class="tab">
  <p class="hint">
    Engines power the Search tab. URLs must be a v3 .onion or .i2p address with
    a <code>{'{q}'}</code> query placeholder. I2P engines are only queried when
    I2P is enabled (Tor &amp; Privacy settings).
  </p>

  {#if loadError}
    <p class="empty error">{loadError}</p>
  {:else if !loaded}
    <p class="empty">Loading…</p>
  {:else if engines.length === 0}
    <p class="empty">No engines configured.</p>
  {:else}
    <ul class="list">
      {#each engines as row (row.id)}
        <li>
          {#if editingId === row.id}
            <div class="edit-fields">
              <input
                type="text"
                bind:value={editLabel}
                aria-label="Engine label"
                placeholder="Label"
              />
              <input
                type="text"
                bind:value={editUrl}
                aria-label="Engine URL"
                placeholder="http://…onion/?q={'{q}'}"
                onkeydown={(e) => {
                  if (e.key === 'Enter') void commitEdit(row.id);
                  else if (e.key === 'Escape') cancelEdit();
                }}
              />
            </div>
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
            <input
              type="checkbox"
              class="toggle"
              checked={enabled[row.id]}
              aria-label={`Enable ${row.label}`}
              title={enabled[row.id] ? 'Enabled' : 'Disabled'}
              onchange={(e) =>
                void onToggle(row.id, (e.target as HTMLInputElement).checked)}
            />
            <div class="meta" class:off={!enabled[row.id]}>
              <span class="label" title={row.label}>
                {row.label}
                {#if row.network === 'i2p'}<span class="net-badge">I2P</span>{/if}
              </span>
              <span class="url" title={row.url}>{row.url}</span>
            </div>
            <button
              type="button"
              class="icon"
              aria-label={`Edit ${row.label}`}
              title="Edit"
              onclick={() => startEdit(row)}
            >
              <Pencil size={12} />
            </button>
            <button
              type="button"
              class="icon danger"
              aria-label={`Delete ${row.label}`}
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

  <div class="add">
    <div class="add-fields">
      <input
        type="text"
        placeholder="Label"
        bind:value={newLabel}
        aria-label="New engine label"
        disabled={saving}
      />
      <input
        type="text"
        placeholder="http://…onion/?q={'{q}'}"
        bind:value={newUrl}
        aria-label="New engine URL"
        disabled={saving}
        onkeydown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            void onAdd();
          }
        }}
      />
    </div>
    <button
      type="button"
      class="add-btn"
      onclick={() => void onAdd()}
      disabled={saving || !newLabel.trim() || !newUrl.trim()}
    >
      <Plus size={12} />
      Add engine
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
  .hint code {
    color: var(--accent);
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
    gap: 6px;
    padding: 4px;
    border-radius: 2px;
  }
  .list li:hover {
    background: rgba(0, 212, 170, 0.06);
  }
  .toggle {
    cursor: pointer;
    flex: 0 0 auto;
  }
  .meta {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .meta.off {
    opacity: 0.5;
  }
  .label {
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .url {
    color: var(--muted);
    font-size: 10px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .net-badge {
    margin-left: 6px;
    padding: 0 4px;
    border: 1px solid var(--border);
    border-radius: 3px;
    color: var(--accent);
    font-size: 9px;
    vertical-align: middle;
  }
  .edit-fields,
  .add-fields {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .edit-fields input,
  .add-fields input {
    background: #17191f;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 4px 6px;
    font: inherit;
    font-size: 12px;
    border-radius: 3px;
    width: 100%;
  }
  .edit-fields input:focus-visible,
  .add-fields input:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .edit-fields input:first-child {
    border-color: var(--accent);
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
    flex: 0 0 auto;
  }
  .icon:hover:not(:disabled) {
    border-color: var(--border);
    color: var(--accent);
  }
  .icon.danger:hover:not(:disabled) {
    color: #ff5577;
    border-color: #ff5577;
  }
  .add {
    display: flex;
    gap: 6px;
    align-items: flex-end;
    border-top: 1px solid var(--border);
    padding-top: 8px;
  }
  .add-btn {
    flex: 0 0 auto;
    background: transparent;
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 5px 10px;
    font-size: 11px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    white-space: nowrap;
  }
  .add-btn:hover:not(:disabled) {
    background: rgba(0, 212, 170, 0.1);
  }
  .add-btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
</style>
