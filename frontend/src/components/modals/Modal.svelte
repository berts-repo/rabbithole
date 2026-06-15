<script lang="ts">
  // Shared modal shell for the F4b graph modals. Owns the backdrop, the
  // centred dialog, Escape / backdrop-click dismissal, and a standard
  // Cancel / Confirm footer so every modal looks and behaves identically.
  // Form-control styling is applied globally to the slotted body so the
  // modal components only supply semantic markup (.row / .check / .hint).

  import { X } from 'lucide-svelte';
  import type { Snippet } from 'svelte';
  import { TextButton } from '$lib/ui';

  interface Props {
    title: string;
    onClose: () => void;
    onConfirm: () => void;
    confirmLabel: string;
    confirmDisabled?: boolean;
    busy?: boolean;
    children: Snippet;
  }

  let {
    title,
    onClose,
    onConfirm,
    confirmLabel,
    confirmDisabled = false,
    busy = false,
    children,
  }: Props = $props();

  function onKey(e: KeyboardEvent): void {
    if (e.key === 'Escape' && !busy) {
      e.stopPropagation();
      onClose();
    }
  }
</script>

<svelte:window onkeydown={onKey} />

<div
  class="backdrop"
  role="presentation"
  onclick={(e) => {
    if (e.target === e.currentTarget && !busy) onClose();
  }}
>
  <div class="modal" role="dialog" aria-modal="true" aria-label={title}>
    <header>
      <h2>{title}</h2>
      <button type="button" class="x" aria-label="Close" onclick={onClose}>
        <X size={15} />
      </button>
    </header>
    <div class="body">{@render children()}</div>
    <footer>
      <TextButton variant="ghost" onclick={onClose}>Cancel</TextButton>
      <TextButton
        variant="primary"
        disabled={confirmDisabled || busy}
        onclick={onConfirm}
      >
        {busy ? '…' : confirmLabel}
      </TextButton>
    </footer>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 950;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.55);
  }
  .modal {
    width: min(440px, calc(100vw - 32px));
    max-height: calc(100vh - 64px);
    display: flex;
    flex-direction: column;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
  }
  h2 {
    margin: 0;
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
  }
  .x {
    background: transparent;
    border: none;
    color: var(--muted);
    cursor: pointer;
    display: inline-flex;
    padding: 2px;
  }
  .x:hover {
    color: var(--accent);
  }
  .body {
    padding: 14px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  footer {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding: 10px 14px;
    border-top: 1px solid var(--border);
  }
  /* Form-control styling for slotted modal bodies. Modal components use
     .row (stacked label + control), .check (inline checkbox), .hint. */
  .body :global(.row) {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .body :global(.row > span) {
    font-size: 11px;
    color: var(--muted);
  }
  .body :global(input[type='text']),
  .body :global(input[type='number']),
  .body :global(textarea),
  .body :global(select) {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 3px;
    padding: 5px 7px;
    font-size: 12px;
    width: 100%;
  }
  .body :global(input:focus-visible),
  .body :global(textarea:focus-visible),
  .body :global(select:focus-visible) {
    border-color: var(--accent);
  }
  .body :global(input:read-only) {
    color: var(--muted);
    cursor: default;
  }
  .body :global(.check) {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 12px;
    cursor: pointer;
  }
  .body :global(.check input) {
    cursor: pointer;
  }
  .body :global(.hint) {
    margin: 0;
    font-size: 11px;
    color: var(--muted);
  }
  .body :global(.count) {
    color: var(--accent);
  }
</style>
