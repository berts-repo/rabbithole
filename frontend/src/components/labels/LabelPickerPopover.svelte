<script lang="ts">
  // Label-picker popover (item 11) — apply/remove labels on one target, and
  // create a new label inline. Mirrors RenameAliasPopover's mount contract
  // (fixed-position, backdrop catches click-outside, Esc closes); the surface
  // owns the anchor coords and supplies the target + its current direct ids.
  //
  // Toggles are optimistic and idempotent: the checkbox flips immediately, the
  // attach/detach runs, and a failure reverts the row with a toast. The graph
  // poll is deferred to close (via `onChanged`) so toggling several labels
  // doesn't fire a poll per click.

  import { untrack } from 'svelte';
  import { ApiError } from '$lib/api';
  import { labelsStore } from '$lib/stores/labels.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { setLabel, labelTargetIdentity, type LabelTarget } from '$lib/contextMenu/actions';
  import { labelCreateName } from '$lib/contextMenu/labels';

  interface Props {
    x: number;
    y: number;
    target: LabelTarget;
    currentIds: number[];
    onClose: () => void;
    // Fired on close iff any attach/detach landed — the surface refreshes its
    // graph/detail so chips elsewhere reflect the change.
    onChanged?: () => void;
  }

  let { x, y, target, currentIds, onClose, onChanged }: Props = $props();

  const identity = $derived(labelTargetIdentity(target));

  // The live checked set — seeded once from the target's current direct ids.
  let selected = $state<number[]>(untrack(() => [...currentIds]));
  let query = $state('');
  let busyId = $state<number | null>(null);
  let creating = $state(false);
  let dirty = false;
  let inputEl = $state<HTMLInputElement | null>(null);

  $effect(() => {
    inputEl?.focus();
  });

  const isChecked = (id: number): boolean => selected.includes(id);

  // Picker order: rank-sorted, presets the analyst hid dropped, filtered by the
  // search query (case-insensitive substring on name).
  const matches = $derived.by(() => {
    const q = query.trim().toLowerCase();
    return labelsStore.visible.filter(
      (l) => q === '' || l.name.toLowerCase().includes(q),
    );
  });

  // Offer create only when the typed name matches no existing label exactly
  // (across hidden ones too — the name is UNIQUE in the DB).
  const createName = $derived(
    labelCreateName(query, labelsStore.labels.map((l) => l.name)),
  );

  async function toggle(id: number): Promise<void> {
    if (busyId !== null) return;
    const on = !isChecked(id);
    busyId = id;
    // Optimistic flip.
    selected = on ? [...selected, id] : selected.filter((x) => x !== id);
    try {
      const changed = await setLabel(target, id, on);
      if (changed) dirty = true;
    } catch (err) {
      // Revert and report.
      selected = on ? selected.filter((x) => x !== id) : [...selected, id];
      const msg = err instanceof ApiError ? err.message : 'Label update failed';
      toastStore.show(msg, 'error');
    } finally {
      busyId = null;
    }
  }

  async function createAndApply(): Promise<void> {
    const name = createName;
    if (name === null || creating) return;
    creating = true;
    try {
      const label = await labelsStore.create({ name });
      const changed = await setLabel(target, label.id, true);
      if (changed) dirty = true;
      selected = [...selected, label.id];
      query = '';
    } catch (err) {
      const msg =
        err instanceof ApiError && err.status === 409
          ? 'A label with that name already exists.'
          : 'Create label failed';
      toastStore.show(msg, 'error');
    } finally {
      creating = false;
    }
  }

  function close(): void {
    if (dirty) onChanged?.();
    onClose();
  }

  function onKeydown(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
      e.preventDefault();
      close();
    } else if (e.key === 'Enter' && createName !== null) {
      e.preventDefault();
      void createAndApply();
    }
  }
</script>

<div class="backdrop" role="presentation" onclick={close}></div>

<div
  class="popover"
  style:left="{x}px"
  style:top="{y}px"
  role="dialog"
  aria-label="Apply labels"
>
  <div class="head">
    <span class="title">Labels</span>
    <span class="ident" title={identity.value}>{identity.label}: {identity.value}</span>
  </div>

  <input
    bind:this={inputEl}
    bind:value={query}
    type="text"
    class="search"
    placeholder="Search or create…"
    maxlength={64}
    onkeydown={onKeydown}
  />

  <ul class="list" role="listbox" aria-label="Labels">
    {#each matches as label (label.id)}
      <li>
        <button
          type="button"
          class="row"
          class:checked={isChecked(label.id)}
          role="option"
          aria-selected={isChecked(label.id)}
          disabled={busyId === label.id}
          onclick={() => toggle(label.id)}
        >
          <span class="check" aria-hidden="true">{isChecked(label.id) ? '✓' : ''}</span>
          <span class="dot" style:background={label.color ?? 'var(--accent)'} aria-hidden="true"></span>
          <span class="name">{label.name}</span>
          {#if label.builtin}<span class="preset">preset</span>{/if}
        </button>
      </li>
    {/each}

    {#if createName !== null}
      <li>
        <button
          type="button"
          class="row create"
          disabled={creating}
          onclick={createAndApply}
        >
          <span class="check" aria-hidden="true">+</span>
          <span class="name">Create &amp; apply “{createName}”</span>
        </button>
      </li>
    {:else if matches.length === 0}
      <li class="empty">No labels</li>
    {/if}
  </ul>

  <p class="hint">Click to toggle · Esc to close</p>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 199;
  }

  .popover {
    position: fixed;
    transform: translate(-50%, -50%);
    z-index: 200;
    width: 260px;
    padding: 10px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.7);
  }

  .head {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .title {
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .ident {
    font-size: 11px;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .search {
    width: 100%;
    box-sizing: border-box;
    padding: 5px 8px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 3px;
    color: var(--text);
    font-size: 13px;
    outline: none;
  }

  .search:focus {
    border-color: var(--accent);
  }

  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: 220px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 7px;
    width: 100%;
    padding: 4px 6px;
    background: transparent;
    border: none;
    border-radius: 3px;
    color: var(--text);
    font-size: 12px;
    text-align: left;
    cursor: pointer;
  }

  .row:hover:not(:disabled) {
    background: rgba(0, 212, 170, 0.08);
  }

  .row:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .row.checked {
    color: var(--accent);
  }

  .check {
    flex: 0 0 12px;
    font-size: 11px;
    color: var(--accent);
    text-align: center;
  }

  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .name {
    flex: 1;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .preset {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
  }

  .row.create .name {
    color: var(--accent);
  }

  .empty {
    padding: 6px;
    font-size: 11px;
    color: var(--muted);
    text-align: center;
  }

  .hint {
    margin: 0;
    font-size: 10px;
    color: var(--muted);
  }
</style>
