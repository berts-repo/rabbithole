<script lang="ts">
  // Centered modal that fires on kill-switch trip. Reason-aware copy
  // (only `tor_lost` exists today; new reasons drop in here). Acknowledge
  // dismisses the modal but leaves the FSM in `tripped` so the pill stays
  // red. Retry probes Tor by refetching status; the backend monitor will
  // publish `kill_switch.clear` on its next tick if recovery sticks.

  import { ShieldAlert, RotateCw, X } from 'lucide-svelte';
  import { servicesStore } from '$lib/stores/services.svelte';
  import { probeTor } from '$lib/api';
  import { toastStore } from '$lib/stores/toast.svelte';

  let dismissed = $state(false);
  let retrying = $state(false);
  // True after a successful Retry probe, while we wait for the backend
  // monitor to publish `kill_switch.clear`. Drives the inline "waiting"
  // state on the Retry button so the user sees the click had effect.
  let waitingForClear = $state(false);

  // Show only on the first transition into `tripped`. Re-show when the
  // phase moves away from tripped (so the next outage opens a fresh
  // modal). Pure phase-driven — no event listener needed.
  $effect(() => {
    if (servicesStore.killSwitch.phase !== 'tripped') {
      dismissed = false;
      waitingForClear = false;
    }
  });

  const visible = $derived(
    servicesStore.killSwitch.phase === 'tripped' && !dismissed,
  );

  const enforced = $derived(servicesStore.killSwitch.enabled);
  // "Startup" framing fires when Tor has never been reachable this
  // session — there's nothing to "lose", the analyst just needs to
  // start the service.
  const startup = $derived(!servicesStore.tor.everReachable);

  async function onRetry(): Promise<void> {
    if (retrying || waitingForClear) return;
    retrying = true;
    try {
      // POST /api/tor/probe forces a synchronous backend probe — on
      // success the kill switch publishes `kill_switch.clear` before
      // this call returns, so the modal closes on the next SSE tick
      // (~one round trip) rather than waiting for the next background
      // probe interval.
      const s = await probeTor();
      servicesStore.setTor({ reachable: s.ok, lastPoll: Date.now() });
      if (s.ok) {
        // Backend already emitted `kill_switch.clear`; the $effect
        // above will dismiss the modal when phase leaves `tripped`.
        // Show a transient "waiting" state in case the SSE event is
        // still in flight when we return here.
        waitingForClear = true;
      } else {
        toastStore.show('Tor still unreachable.', 'warn');
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Retry failed: ${msg}`, 'error');
    } finally {
      retrying = false;
    }
  }
</script>

{#if visible}
  <div class="backdrop" role="presentation"></div>
  <div
    class="modal"
    role="alertdialog"
    aria-modal="true"
    aria-labelledby="ks-alert-title"
    aria-describedby="ks-alert-body"
  >
    <header>
      <ShieldAlert size={18} class="icon" aria-hidden="true" />
      <h2 id="ks-alert-title">
        {startup ? 'Connect to Tor' : 'Tor connection lost'}
      </h2>
      <button
        type="button"
        class="close"
        aria-label="Dismiss"
        onclick={() => (dismissed = true)}
      >
        <X size={14} />
      </button>
    </header>
    <div id="ks-alert-body" class="body">
      {#if startup}
        <p>Tor isn't running — start it, then retry the connection.</p>
      {:else if enforced}
        <p>
          The kill switch has halted the crawl. No outbound traffic will
          resume until Tor is reachable again and you re-arm the kill
          switch.
        </p>
      {:else}
        <p>
          Tor is unreachable and the crawl has halted. Enforcement is
          off, so any in-flight request was allowed to finish on its own
          rather than being cut off mid-stream. Re-arm the kill switch
          from the header pill once Tor is reachable again.
        </p>
      {/if}
      <p class="hint">
        Bring Tor back with <code>sudo systemctl start tor</code>.
      </p>
    </div>
    <div class="actions">
      <button
        type="button"
        class="ghost"
        onclick={() => (dismissed = true)}
      >
        Acknowledge
      </button>
      <button
        type="button"
        class="primary"
        disabled={retrying || waitingForClear}
        onclick={onRetry}
      >
        <RotateCw size={12} aria-hidden="true" />
        {#if waitingForClear}
          Waiting for monitor…
        {:else if retrying}
          Retrying…
        {:else}
          Retry connection
        {/if}
      </button>
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.65);
    z-index: 100;
  }
  .modal {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: var(--bg);
    border: 1px solid var(--danger);
    border-radius: 3px;
    min-width: 360px;
    max-width: 440px;
    z-index: 101;
    box-shadow: 0 10px 40px rgba(255, 68, 68, 0.15);
  }
  header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
    color: var(--danger);
  }
  h2 {
    margin: 0;
    flex: 1;
    font-size: 13px;
    font-weight: 600;
    color: var(--danger);
  }
  .close {
    background: transparent;
    border: none;
    color: var(--muted);
    cursor: pointer;
    padding: 2px;
    display: inline-flex;
  }
  .close:hover {
    color: var(--text);
  }
  .body {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 12px 14px;
  }
  .body p {
    margin: 0;
    color: var(--text);
    font-size: 12px;
    line-height: 1.5;
  }
  .body p.hint {
    color: var(--muted);
  }
  .body code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 11px;
    color: var(--text);
    background: rgba(168, 255, 219, 0.08);
    padding: 1px 5px;
    border-radius: 2px;
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding: 0 14px 14px;
  }
  button {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: 1px solid var(--border);
    background: transparent;
    padding: 5px 12px;
    font-size: 11px;
    color: var(--text);
    cursor: pointer;
    border-radius: 2px;
  }
  button.primary {
    border-color: var(--danger);
    color: var(--danger);
  }
  button.primary:hover:not(:disabled) {
    background: var(--danger);
    color: var(--bg);
  }
  button.ghost:hover {
    color: var(--accent);
    border-color: var(--accent);
  }
  button:disabled {
    opacity: 0.6;
    cursor: progress;
  }
</style>
