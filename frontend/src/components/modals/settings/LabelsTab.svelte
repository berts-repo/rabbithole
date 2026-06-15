<script lang="ts">
  // Settings → Labels (item 11, Phase 3e). The management home for the label
  // taxonomy: drag to set the analyst rank order (decision D5 — shared with the
  // bottom-pane Labels tab), recolor / redescribe any label, rename or delete
  // custom labels, toggle a preset's picker visibility, and create new custom
  // labels. Presets (`builtin`) can be recolored, redescribed, and hidden but
  // never renamed or deleted (decision D3) — the UI locks those affordances.
  //
  // All mutations route through `labelsStore`, the single catalog source of
  // truth, so chips / picker / color-mode / collapse ordering everywhere else
  // reflect the change without a reload.

  import { onMount } from 'svelte';
  import {
    Check,
    GripVertical,
    Pencil,
    Plus,
    Trash2,
    X,
    Eye,
    EyeOff,
  } from 'lucide-svelte';
  import { ApiError, type Label } from '$lib/api';
  import { labelsStore } from '$lib/stores/labels.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { reorderedIds } from '$lib/labels/order';

  // Dark-theme swatches — the seven preset colors plus a neutral mint, so a new
  // custom label can echo a preset's hue or stand apart. `null` = no color
  // (renders as the accent fallback everywhere a swatch is drawn).
  const PALETTE: readonly string[] = [
    '#ff5470',
    '#ff8c42',
    '#ffd166',
    '#00d4aa',
    '#5fd0c4',
    '#4d9fff',
    '#b07cff',
    '#a8ffdb',
  ];

  let loadError = $state<string | null>(null);

  onMount(() => {
    void (async () => {
      try {
        await labelsStore.ensureLoaded();
      } catch (err) {
        loadError = errMsg(err);
      }
    })();
  });

  // Friendly text for the backend's error-code vocabulary (routes/labels.py).
  function errMsg(err: unknown): string {
    if (err instanceof ApiError) {
      switch (err.message) {
        case 'duplicate_name':
          return 'A label with that name already exists.';
        case 'builtin_rename':
          return 'Preset labels cannot be renamed.';
        case 'builtin_undeletable':
          return 'Preset labels cannot be deleted.';
        case 'empty_name':
          return 'A label needs a name.';
        case 'name_too_long':
          return 'That name is too long.';
        default:
          return err.message;
      }
    }
    return err instanceof Error ? err.message : String(err);
  }

  // --- inline edit ----------------------------------------------------------

  let editingId = $state<number | null>(null);
  let editName = $state('');
  let editColor = $state<string | null>(null);
  let editDescription = $state('');
  let busy = $state(false);

  function startEdit(label: Label): void {
    editingId = label.id;
    editName = label.name;
    editColor = label.color;
    editDescription = label.description ?? '';
  }

  function cancelEdit(): void {
    editingId = null;
  }

  // Every update sends the label's full current state with the patch merged in:
  // the PATCH route resets any field the body omits (notably `hidden`), so we
  // never send a partial. Presets keep their existing name (rename is locked).
  async function save(label: Label, patch: Partial<Label>): Promise<void> {
    if (busy) return;
    busy = true;
    const next = { ...label, ...patch };
    try {
      await labelsStore.update(label.id, {
        name: next.name,
        color: next.color,
        description: next.description,
        hidden: next.hidden,
      });
    } catch (err) {
      toastStore.show(errMsg(err), 'error');
    } finally {
      busy = false;
    }
  }

  async function commitEdit(label: Label): Promise<void> {
    const name = editName.trim();
    if (!name) {
      toastStore.show('A label needs a name.', 'warn');
      return;
    }
    await save(label, {
      // Presets can't be renamed — keep the original name regardless of input.
      name: label.builtin ? label.name : name,
      color: editColor,
      description: editDescription.trim() || null,
    });
    if (!busy) cancelEdit();
  }

  async function onDelete(label: Label): Promise<void> {
    if (label.builtin || busy) return;
    busy = true;
    try {
      await labelsStore.remove(label.id);
      if (editingId === label.id) cancelEdit();
    } catch (err) {
      toastStore.show(errMsg(err), 'error');
    } finally {
      busy = false;
    }
  }

  // --- add new --------------------------------------------------------------

  let newName = $state('');
  let newColor = $state<string | null>(PALETTE[3]);
  let adding = $state(false);

  async function onAdd(): Promise<void> {
    const name = newName.trim();
    if (!name || adding) return;
    adding = true;
    try {
      await labelsStore.create({ name, color: newColor });
      newName = '';
      newColor = PALETTE[3];
    } catch (err) {
      toastStore.show(errMsg(err), 'error');
    } finally {
      adding = false;
    }
  }

  // --- drag reorder (writes rank) -------------------------------------------

  let dragId = $state<number | null>(null);
  let overId = $state<number | null>(null);

  function onDragStart(e: DragEvent, id: number): void {
    dragId = id;
    e.dataTransfer?.setData('text/plain', String(id));
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
  }

  function onDragOver(e: DragEvent, id: number): void {
    if (dragId === null) return;
    e.preventDefault();
    overId = id;
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
  }

  async function onDrop(e: DragEvent, targetId: number): Promise<void> {
    e.preventDefault();
    const ids = labelsStore.labels.map((l) => l.id);
    const from = ids.indexOf(dragId ?? -1);
    const to = ids.indexOf(targetId);
    dragId = null;
    overId = null;
    if (from === -1 || to === -1 || from === to) return;
    try {
      await labelsStore.reorder(reorderedIds(ids, from, to));
    } catch (err) {
      toastStore.show(errMsg(err), 'error');
    }
  }

  function onDragEnd(): void {
    dragId = null;
    overId = null;
  }
</script>

<div class="tab">
  <p class="hint">
    Drag to set the rank order — higher ranks first for the picker, the
    dominant-label color, and label collapse. Presets recolor but never rename
    or delete.
  </p>

  {#if loadError}
    <p class="empty error">{loadError}</p>
  {:else if !labelsStore.loaded}
    <p class="empty">Loading…</p>
  {:else if labelsStore.labels.length === 0}
    <p class="empty">No labels yet.</p>
  {:else}
    <ul class="list">
      {#each labelsStore.labels as label (label.id)}
        <li
          class:dragover={overId === label.id && dragId !== label.id}
          class:dragging={dragId === label.id}
          ondragover={(e) => onDragOver(e, label.id)}
          ondrop={(e) => void onDrop(e, label.id)}
          role="presentation"
        >
          {#if editingId === label.id}
            <div class="edit">
              <div class="edit-line">
                <input
                  type="text"
                  class="name-input"
                  bind:value={editName}
                  disabled={label.builtin}
                  aria-label="Label name"
                  placeholder="Name"
                  title={label.builtin ? 'Presets cannot be renamed' : 'Name'}
                  onkeydown={(e) => {
                    if (e.key === 'Enter') void commitEdit(label);
                    else if (e.key === 'Escape') cancelEdit();
                  }}
                />
                <button
                  type="button"
                  class="icon"
                  aria-label="Save"
                  title="Save"
                  disabled={busy}
                  onclick={() => void commitEdit(label)}
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
              </div>
              <div class="palette" role="group" aria-label="Label color">
                {#each PALETTE as c (c)}
                  <button
                    type="button"
                    class="swatch"
                    class:on={editColor === c}
                    style:background={c}
                    aria-label={`Color ${c}`}
                    aria-pressed={editColor === c}
                    onclick={() => (editColor = c)}
                  ></button>
                {/each}
                <button
                  type="button"
                  class="swatch none"
                  class:on={editColor === null}
                  aria-label="No color"
                  aria-pressed={editColor === null}
                  title="No color"
                  onclick={() => (editColor = null)}
                >
                  <X size={10} />
                </button>
              </div>
              <input
                type="text"
                class="desc-input"
                bind:value={editDescription}
                aria-label="Label description"
                placeholder="Description (optional)"
                maxlength={512}
              />
            </div>
          {:else}
            <span
              class="grip"
              draggable="true"
              role="button"
              tabindex="-1"
              aria-label={`Drag to reorder ${label.name}`}
              title="Drag to reorder"
              ondragstart={(e) => onDragStart(e, label.id)}
              ondragend={onDragEnd}
            >
              <GripVertical size={12} />
            </span>
            <span
              class="dot"
              style:background={label.color ?? 'var(--accent)'}
              aria-hidden="true"
            ></span>
            <div class="meta" class:off={label.hidden}>
              <span class="name" title={label.description ?? label.name}>
                {label.name}
                {#if label.builtin}<span class="badge">preset</span>{/if}
                {#if label.hidden}<span class="badge">hidden</span>{/if}
              </span>
              {#if label.description}
                <span class="desc" title={label.description}>{label.description}</span>
              {/if}
            </div>
            <span class="counts" title="Resources · Domains">
              {label.resource_count}·{label.domain_count}
            </span>
            {#if label.builtin}
              <button
                type="button"
                class="icon"
                aria-label={label.hidden ? `Show ${label.name} in picker` : `Hide ${label.name} from picker`}
                title={label.hidden ? 'Hidden from picker — click to show' : 'Visible — click to hide from picker'}
                disabled={busy}
                onclick={() => void save(label, { hidden: !label.hidden })}
              >
                {#if label.hidden}<EyeOff size={13} />{:else}<Eye size={13} />{/if}
              </button>
            {/if}
            <button
              type="button"
              class="icon"
              aria-label={`Edit ${label.name}`}
              title="Edit color / description"
              onclick={() => startEdit(label)}
            >
              <Pencil size={12} />
            </button>
            <button
              type="button"
              class="icon danger"
              aria-label={`Delete ${label.name}`}
              title={label.builtin ? 'Presets cannot be deleted' : 'Delete'}
              disabled={label.builtin || busy}
              onclick={() => void onDelete(label)}
            >
              <Trash2 size={12} />
            </button>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}

  <div class="add">
    <span
      class="add-swatch"
      style:background={newColor ?? 'var(--accent)'}
      aria-hidden="true"
    ></span>
    <input
      type="text"
      placeholder="New label name"
      bind:value={newName}
      aria-label="New label name"
      disabled={adding}
      maxlength={64}
      onkeydown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          void onAdd();
        }
      }}
    />
    <div class="palette compact" role="group" aria-label="New label color">
      {#each PALETTE as c (c)}
        <button
          type="button"
          class="swatch"
          class:on={newColor === c}
          style:background={c}
          aria-label={`Color ${c}`}
          aria-pressed={newColor === c}
          onclick={() => (newColor = c)}
        ></button>
      {/each}
    </div>
    <button
      type="button"
      class="add-btn"
      onclick={() => void onAdd()}
      disabled={adding || !newName.trim()}
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
  .list > li {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px;
    border-radius: 2px;
  }
  .list > li:hover {
    background: rgba(0, 212, 170, 0.06);
  }
  .list > li.dragover {
    box-shadow: inset 0 2px 0 var(--accent);
  }
  .list > li.dragging {
    opacity: 0.5;
  }
  .grip {
    flex: 0 0 auto;
    display: inline-flex;
    color: var(--muted);
    cursor: grab;
  }
  .grip:active {
    cursor: grabbing;
  }
  .dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
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
  .name {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .badge {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
  }
  .desc {
    color: var(--muted);
    font-size: 10px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .counts {
    flex: 0 0 auto;
    font-size: 10px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
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
  .icon:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }
  .icon.danger:hover:not(:disabled) {
    color: #ff5577;
    border-color: #ff5577;
  }
  /* edit mode */
  .edit {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .edit-line {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .name-input,
  .desc-input {
    flex: 1 1 auto;
    min-width: 0;
    background: #17191f;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 4px 6px;
    font: inherit;
    font-size: 12px;
    border-radius: 3px;
  }
  .name-input:focus-visible,
  .desc-input:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .name-input:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  .palette {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .swatch {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    border: 1px solid var(--border);
    padding: 0;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: var(--muted);
  }
  .swatch.on {
    outline: 2px solid var(--accent);
    outline-offset: 1px;
  }
  .swatch.none {
    background: transparent;
  }
  /* add row */
  .add {
    display: flex;
    align-items: center;
    gap: 6px;
    border-top: 1px solid var(--border);
    padding-top: 8px;
  }
  .add-swatch {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    flex: 0 0 auto;
  }
  .add input {
    flex: 1 1 auto;
    min-width: 0;
    background: #17191f;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 5px 6px;
    font: inherit;
    font-size: 12px;
    border-radius: 3px;
  }
  .add input:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .palette.compact .swatch {
    width: 13px;
    height: 13px;
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
