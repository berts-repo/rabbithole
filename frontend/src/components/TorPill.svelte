<script lang="ts">
  import { servicesStore } from '$lib/stores/services.svelte';

  const reachable = $derived(servicesStore.tor.reachable);
  const title = $derived(
    servicesStore.tor.lastPoll === null
      ? 'Tor — checking…'
      : reachable
        ? 'Tor — connected'
        : 'Tor — unreachable',
  );
</script>

<span class="pill" class:up={reachable} class:down={!reachable} {title}>
  <span class="dot" aria-hidden="true"></span>
  <span class="label">Tor</span>
</span>

<style>
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 8px;
    border: 1px solid var(--border);
    border-radius: 2px;
    font-size: 12px;
    color: var(--text);
    user-select: none;
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--muted);
  }
  .up .dot {
    background: var(--accent);
    box-shadow: 0 0 4px var(--accent);
  }
  .down .dot {
    background: #ff5577;
    box-shadow: 0 0 4px #ff5577;
  }
</style>
