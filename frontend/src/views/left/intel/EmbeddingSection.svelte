<script lang="ts">
  // Intel · Embedding Model section. The embed worker generates vector
  // embeddings for crawled pages (semantic search). It auto-starts with the
  // backend; Intel offers pause/resume + a coverage readout. Full start/stop
  // lives in Settings → Embedding (spec line 344).

  import {
    getEmbedStatus,
    pauseEmbed,
    resumeEmbed,
    type EmbedStatus,
  } from '$lib/api';
  import { explainError } from '$lib/api/errors';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { StatusBadge, TextButton } from '$lib/ui';

  // Spec: embedding model status refreshes every 10 s while the tab is active.
  const POLL_MS = 10000;

  let status = $state<EmbedStatus | null>(null);
  let busy = $state(false);
  let error = $state<string | null>(null);

  const paused = $derived(status?.paused === true);
  const running = $derived(status?.status === 'running' && !paused);

  const badge = $derived.by((): { variant: 'running' | 'paused' | 'pending' | 'warning'; label: string } => {
    if (error) return { variant: 'warning', label: 'unavailable' };
    if (!status) return { variant: 'pending', label: '…' };
    if (status.circuit_open) return { variant: 'warning', label: 'circuit open' };
    if (paused) return { variant: 'paused', label: 'paused' };
    if (running) return { variant: 'running', label: 'running' };
    return { variant: 'pending', label: status.status };
  });

  const percent = $derived.by((): number => {
    if (!status || status.eligible === 0) return 100;
    return Math.round((status.embedded / status.eligible) * 100);
  });

  async function refresh(): Promise<void> {
    try {
      status = await getEmbedStatus();
      error = null;
    } catch (e) {
      error = explainError(e, 'Embedding status unavailable');
    }
  }

  async function act(
    fn: () => Promise<EmbedStatus>,
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

<div class="embed">
  <div class="status-row">
    <StatusBadge status={badge.variant} label={badge.label} />
    {#if status?.model}
      <span class="model" title="Embedding model">{status.model}</span>
    {/if}
  </div>

  {#if status}
    <p class="progress">
      {status.embedded} / {status.eligible} pages embedded ({percent}%)
      {#if status.queue_size > 0}
        <span class="depth"> · {status.queue_size} queued</span>
      {/if}
    </p>
  {/if}

  <div class="controls">
    {#if paused}
      <TextButton
        variant="primary"
        onclick={() => void act(resumeEmbed, 'Resume failed')}
        disabled={busy}
      >
        Resume
      </TextButton>
    {:else}
      <TextButton onclick={() => void act(pauseEmbed, 'Pause failed')} disabled={busy}>
        Pause
      </TextButton>
    {/if}
  </div>

  {#if error}
    <p class="err">{error}</p>
  {/if}
</div>

<style>
  .embed {
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
  .progress {
    margin: 0;
    font-size: 11px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .depth {
    color: var(--accent);
  }
  .controls {
    display: flex;
    gap: 6px;
  }
  .err {
    margin: 0;
    font-size: 11px;
    color: #ff8f8f;
  }
</style>
