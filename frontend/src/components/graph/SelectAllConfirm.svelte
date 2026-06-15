<script lang="ts">
  // Ctrl+A confirmation when the visible node count exceeds 50.
  // Lightweight inline modal — graph spec calls this out specifically
  // (explore-graph.md:105).

  interface Props {
    count: number;
    onConfirm: () => void;
    onCancel: () => void;
  }

  let { count, onConfirm, onCancel }: Props = $props();
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="backdrop" onclick={onCancel}></div>

<div class="modal" role="dialog" aria-modal="true" aria-labelledby="select-all-title">
  <h3 id="select-all-title">Select all {count} nodes?</h3>
  <p>Bulk actions will apply to every one.</p>
  <div class="actions">
    <button type="button" class="ghost" onclick={onCancel}>Cancel</button>
    <button type="button" class="primary" onclick={onConfirm}>Select all</button>
  </div>
</div>

<style>
  .backdrop {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 9;
  }
  .modal {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 16px 18px;
    min-width: 280px;
    z-index: 10;
  }
  h3 {
    margin: 0 0 6px;
    font-size: 12px;
    color: var(--text);
  }
  p {
    margin: 0 0 14px;
    color: var(--muted);
    font-size: 11px;
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
  button {
    border: 1px solid var(--border);
    background: transparent;
    padding: 4px 12px;
    font-size: 11px;
    color: var(--text);
    cursor: pointer;
    border-radius: 2px;
  }
  button.primary {
    background: var(--accent-bg);
    border-color: var(--accent);
    color: var(--accent);
  }
  button.primary:hover {
    background: var(--accent);
    color: var(--bg);
  }
  button.ghost:hover {
    color: var(--accent);
    border-color: var(--accent);
  }
</style>
