<script lang="ts">
  // Intel · LLM Service section. Drives the background analysis worker
  // (start / stop / pause / resume) and shows the live load block from
  // GET /api/llm/status — capacity (jobs per tick), in-flight, queue depth.
  // The worker-control routes already existed (routes/llm.py); this is the
  // first frontend surface over them.

  import {
    getLlmStatus,
    pauseLlm,
    resumeLlm,
    startLlm,
    stopLlm,
    type LlmStatus,
  } from '$lib/api';
  import { explainError } from '$lib/api/errors';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { StatusBadge, TextButton } from '$lib/ui';

  // Spec: LLM status refreshes every 8 s while the Intel tab is active.
  const POLL_MS = 8000;

  let status = $state<LlmStatus | null>(null);
  let busy = $state(false);
  let error = $state<string | null>(null);

  const running = $derived(status?.status === 'running');
  const paused = $derived(status?.paused === true);

  // Map the worker's status string → a StatusBadge variant + label. Stopped
  // reads neutral; an unreachable worker (503) shows as a warning.
  const badge = $derived.by((): { variant: 'running' | 'paused' | 'pending' | 'warning'; label: string } => {
    if (error) return { variant: 'warning', label: 'unavailable' };
    if (!status) return { variant: 'pending', label: '…' };
    if (paused) return { variant: 'paused', label: 'paused' };
    if (running) return { variant: 'running', label: 'running' };
    return { variant: 'pending', label: status.status };
  });

  async function refresh(): Promise<void> {
    try {
      status = await getLlmStatus();
      error = null;
    } catch (e) {
      error = explainError(e, 'Worker status unavailable');
    }
  }

  async function act(
    fn: () => Promise<LlmStatus>,
    failMsg: string,
  ): Promise<void> {
    if (busy) return;
    busy = true;
    try {
      status = await fn();
      error = null;
    } catch (e) {
      toastStore.show(explainError(e, failMsg), 'error');
    } finally {
      busy = false;
    }
  }

  $effect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(id);
  });
</script>

<div class="worker">
  <div class="status-row">
    <StatusBadge status={badge.variant} label={badge.label} />
    {#if status && running}
      <span class="model" title="Active model">{status.model}</span>
    {/if}
    {#if status && status.queue_depth > 0}
      <span class="depth" title="Jobs waiting in the queue">
        {status.queue_depth} queued
      </span>
    {/if}
  </div>

  <div class="controls">
    {#if running}
      <TextButton onclick={() => void act(stopLlm, 'Stop failed')} disabled={busy}>
        Stop
      </TextButton>
      {#if paused}
        <TextButton
          variant="primary"
          onclick={() => void act(resumeLlm, 'Resume failed')}
          disabled={busy}
        >
          Resume
        </TextButton>
      {:else}
        <TextButton onclick={() => void act(pauseLlm, 'Pause failed')} disabled={busy}>
          Pause
        </TextButton>
      {/if}
    {:else}
      <TextButton
        variant="primary"
        onclick={() => void act(startLlm, 'Start failed')}
        disabled={busy}
      >
        Start
      </TextButton>
    {/if}
  </div>

  {#if status}
    <dl class="load" aria-label="Worker load">
      <div><dt>In flight</dt><dd>{status.in_flight}</dd></div>
      <div><dt>Queued</dt><dd>{status.queue_depth}</dd></div>
      <div><dt>Capacity</dt><dd>{status.capacity}/tick</dd></div>
    </dl>
  {/if}

  {#if error}
    <p class="err">{error}</p>
  {/if}
</div>

<style>
  .worker {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .status-row {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .model {
    font-size: 11px;
    color: var(--text);
  }
  .depth {
    font-size: 10px;
    color: var(--accent);
  }
  .controls {
    display: flex;
    gap: 6px;
  }
  .load {
    display: flex;
    gap: 14px;
    margin: 2px 0 0;
  }
  .load div {
    display: flex;
    flex-direction: column;
  }
  .load dt {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
  }
  .load dd {
    margin: 0;
    font-size: 13px;
    color: var(--text);
    font-variant-numeric: tabular-nums;
  }
  .err {
    margin: 0;
    font-size: 11px;
    color: #ff8f8f;
  }
</style>
