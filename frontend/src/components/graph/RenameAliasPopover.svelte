<script lang="ts">
  import { untrack } from 'svelte';
  import { ApiError } from '$lib/api';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { renameTargetIdentity, type RenameTarget } from '$lib/contextMenu/rename';

  interface Props {
    x: number;
    y: number;
    target: RenameTarget;
    currentName: string | null;
    onClose: () => void;
    // Persists the new alias (null when cleared). Resolves once the save +
    // its post-save effects have run; rejects with an ApiError so this
    // popover can render inline 409/400 validation and stay open.
    onSave: (alias: string | null) => Promise<void>;
  }

  let { x, y, target, currentName, onClose, onSave }: Props = $props();

  // What's being renamed — drives the identity meta row's label + value.
  const identity = $derived(renameTargetIdentity(target));

  // Capture initial value only — the popover is opened once and discarded.
  let value = $state(untrack(() => currentName ?? ''));
  let busy = $state(false);
  let error = $state<string | null>(null);
  let inputEl = $state<HTMLInputElement | null>(null);

  $effect(() => {
    inputEl?.focus();
    inputEl?.select();
  });

  async function save(): Promise<void> {
    if (busy) return;
    busy = true;
    error = null;
    // Whitespace-only clears the alias — mirrors the backend's own rule.
    const next = value.trim() || null;
    try {
      await onSave(next);
      onClose();
    } catch (err) {
      busy = false;
      if (err instanceof ApiError && err.status === 409) {
        error = 'That alias is already taken.';
      } else if (err instanceof ApiError && err.status === 400) {
        error = 'Alias too long (max 64 characters).';
      } else {
        toastStore.show('Rename failed', 'error');
        onClose();
      }
    }
  }

  function onKeydown(e: KeyboardEvent): void {
    if (e.key === 'Enter') {
      e.preventDefault();
      void save();
    } else if (e.key === 'Escape') {
      onClose();
    }
  }
</script>

<!-- Transparent backdrop catches click-outside -->
<div class="backdrop" role="presentation" onclick={onClose}></div>

<div class="popover" style:left="{x}px" style:top="{y}px" role="dialog" aria-label="Rename alias">
  <span class="title">Rename alias</span>

  <!-- The target (domain/page) is the immutable identity; the alias is what's
       being edited. Showing both, labelled, keeps the rename unambiguous. -->
  <dl class="meta">
    <div class="meta-row">
      <dt>{identity.label}</dt>
      <dd class="domain">{identity.value}</dd>
    </div>
    <div class="meta-row">
      <dt>Current alias</dt>
      <dd class="alias" class:unset={!currentName}>
        {currentName ?? 'not set'}
      </dd>
    </div>
  </dl>

  <input
    bind:this={inputEl}
    bind:value
    type="text"
    class="alias-input"
    class:busy
    placeholder="Enter alias…"
    maxlength={64}
    disabled={busy}
    onkeydown={onKeydown}
  />
  {#if error}
    <p class="error">{error}</p>
  {/if}
  <p class="hint">Enter to save · Esc to cancel · empty clears</p>
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
    width: 360px;
    padding: 10px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.7);
  }

  .title {
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .meta {
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .meta-row {
    display: flex;
    align-items: baseline;
    gap: 8px;
    min-width: 0;
  }

  .meta dt {
    flex: 0 0 76px;
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .meta dd {
    margin: 0;
    min-width: 0;
    font-size: 11px;
    line-height: 1.4;
  }

  .domain {
    color: var(--text);
    word-break: break-all;
  }

  .alias {
    color: var(--accent);
    word-break: break-word;
  }

  .alias.unset {
    color: var(--muted);
    font-style: italic;
  }

  .alias-input {
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

  .alias-input:focus {
    border-color: var(--accent);
  }

  .alias-input.busy {
    opacity: 0.5;
  }

  .error {
    margin: 0;
    font-size: 11px;
    color: #ff6b6b;
  }

  .hint {
    margin: 0;
    font-size: 10px;
    color: var(--muted);
  }
</style>
