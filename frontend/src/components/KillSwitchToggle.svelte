<script lang="ts">
  import { Shield, ShieldAlert } from 'lucide-svelte';
  import { servicesStore } from '$lib/stores/services.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { putSetting } from '$lib/api';

  let saving = $state(false);

  async function toggle() {
    if (saving) return;
    const next = !servicesStore.killSwitch.enabled;
    saving = true;
    // Optimistic — flip locally so the UI is instant.
    servicesStore.setKillSwitchEnabled(next);
    try {
      await putSetting('tor.kill_switch', next);
    } catch (e) {
      servicesStore.setKillSwitchEnabled(!next);
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Kill switch save failed: ${msg}`, 'error');
    } finally {
      saving = false;
    }
  }

  const enabled = $derived(servicesStore.killSwitch.enabled);
  const phase = $derived(servicesStore.killSwitch.phase);

  const tooltip = $derived.by(() => {
    if (!enabled) return 'Kill switch off — Tor outage will only show a banner';
    switch (phase) {
      case 'tripped':
        return 'Kill switch tripped — Tor unreachable, activity paused';
      case 'cleared_idle':
        return 'Tor recovered — click Resume in the graph toolbar to re-arm';
      default:
        return 'Kill switch on — Tor outage will pause activity';
    }
  });
</script>

<button
  type="button"
  class="ks"
  class:on={enabled && phase === 'armed'}
  class:off={!enabled}
  class:tripped={enabled && phase === 'tripped'}
  class:idle={enabled && phase === 'cleared_idle'}
  disabled={saving}
  onclick={toggle}
  title={tooltip}
>
  {#if !enabled}
    <Shield size={14} aria-hidden="true" />
  {:else if phase === 'tripped'}
    <ShieldAlert size={14} aria-hidden="true" />
  {:else if phase === 'cleared_idle'}
    <Shield size={14} aria-hidden="true" />
  {:else}
    <Shield size={14} fill="currentColor" aria-hidden="true" />
  {/if}
  <span>Kill switch</span>
</button>

<style>
  .ks {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 8px;
    border: 1px solid var(--border);
    border-radius: 2px;
    background: transparent;
    font-size: 12px;
    cursor: pointer;
    user-select: none;
  }
  .ks:hover:not(:disabled) {
    border-color: var(--accent);
  }
  .ks:disabled {
    opacity: 0.6;
    cursor: progress;
  }
  .on {
    color: var(--accent);
  }
  .tripped {
    color: var(--danger);
    border-color: var(--danger);
  }
  .tripped:hover:not(:disabled) {
    border-color: var(--danger);
  }
  .idle {
    color: var(--warn);
    border-color: var(--warn);
  }
  .idle:hover:not(:disabled) {
    border-color: var(--warn);
  }
</style>
