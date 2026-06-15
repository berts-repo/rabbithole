<script lang="ts">
  import { toastStore } from '$lib/stores/toast.svelte';

  // `tick` re-triggers the keyed re-mount so the fade-in animation
  // replays even when an identical message fires twice.
  const message = $derived(toastStore.message);
  const kind = $derived(toastStore.kind);
  const tick = $derived(toastStore.tick);
</script>

{#if message !== null}
  {#key tick}
    <div class="toast" data-kind={kind} role="status" aria-live="polite">
      {message}
    </div>
  {/key}
{/if}

<style>
  .toast {
    position: fixed;
    left: 50%;
    bottom: 32px;
    transform: translateX(-50%);
    padding: 8px 16px;
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    font-size: 12px;
    border-radius: 2px;
    pointer-events: none;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
    animation: rise 200ms ease-out;
    z-index: 1000;
    max-width: 80vw;
    text-align: center;
  }
  .toast[data-kind='warn'] {
    border-color: #b88a2e;
    color: #ffd58a;
  }
  .toast[data-kind='error'] {
    border-color: #ff5577;
    color: #ffb3c0;
  }
  @keyframes rise {
    from {
      opacity: 0;
      transform: translate(-50%, 12px);
    }
    to {
      opacity: 1;
      transform: translate(-50%, 0);
    }
  }
</style>
