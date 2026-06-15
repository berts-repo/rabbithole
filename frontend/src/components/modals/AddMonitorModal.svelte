<script lang="ts">
  // Add Monitor modal — opened from the single-node right-click menu and
  // (later) the Domain tab. Creates an uptime monitor for one URL. Works on
  // stubs too: a monitor just pings the URL. Spec: explore-graph.md:138-147.

  import { untrack } from 'svelte';
  import Modal from './Modal.svelte';
  import { createMonitor } from '$lib/api';
  import { toastStore } from '$lib/stores/toast.svelte';

  interface Props {
    // Preset URL when opened in context (graph node, Domain tab). Pass an
    // empty string for the global Monitors-tab toolbar, where the analyst
    // types the URL themselves.
    url: string;
    onClose: () => void;
  }

  let { url, onClose }: Props = $props();

  const MIN_INTERVAL = 0.25;

  // Seed the editable URL once from the prop and keep it untracked
  // thereafter — the modal owns the field after open, so reactively
  // re-syncing to a later `url` change would clobber the analyst's typing.
  let urlValue = $state(untrack(() => url));
  let label = $state('');
  let intervalHours = $state(24);
  let alertOnChange = $state(true);
  let alertOnRestore = $state(true);
  let downtimeHours = $state(48);
  let busy = $state(false);

  const invalid = $derived(
    urlValue.trim().length === 0 ||
      !Number.isFinite(intervalHours) ||
      intervalHours < MIN_INTERVAL ||
      !Number.isFinite(downtimeHours) ||
      downtimeHours < MIN_INTERVAL,
  );

  async function submit(): Promise<void> {
    if (busy || invalid) return;
    busy = true;
    try {
      await createMonitor({
        url: urlValue.trim(),
        label: label.trim() || null,
        interval_hours: intervalHours,
        alert_on_change: alertOnChange,
        alert_on_restore: alertOnRestore,
        downtime_threshold_hours: downtimeHours,
      });
      toastStore.show('Monitor added.');
      onClose();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Add monitor failed: ${msg}`, 'error');
      busy = false;
    }
  }
</script>

<Modal
  title="Add Monitor"
  {onClose}
  onConfirm={() => void submit()}
  confirmLabel="Add"
  confirmDisabled={invalid}
  {busy}
>
  <label class="row">
    <span>URL</span>
    <input type="text" bind:value={urlValue} placeholder="http://…onion/" />
  </label>
  <label class="row">
    <span>Label (optional)</span>
    <input type="text" bind:value={label} placeholder="e.g. mirror check" />
  </label>
  <label class="row">
    <span>Check interval (hours)</span>
    <input
      type="number"
      bind:value={intervalHours}
      min={MIN_INTERVAL}
      step="0.25"
    />
  </label>
  <label class="check">
    <input type="checkbox" bind:checked={alertOnChange} />
    Alert on content change
  </label>
  <label class="check">
    <input type="checkbox" bind:checked={alertOnRestore} />
    Alert on restore
  </label>
  <label class="row">
    <span>Downtime alert after (hours)</span>
    <input
      type="number"
      bind:value={downtimeHours}
      min={MIN_INTERVAL}
      step="1"
    />
  </label>
  {#if invalid}
    <p class="hint">Interval and downtime threshold must be at least 0.25 h.</p>
  {/if}
</Modal>
