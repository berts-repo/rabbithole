<script lang="ts">
  // Settings → Embedding. Model selection + auto-start + a manual
  // recompute trigger. The embed worker auto-starts with the backend, so
  // day-to-day throttling (pause/resume) lives in the Intel pane; this tab
  // owns the durable configuration plus an explicit re-arm.
  //
  // Model list is the 384-dim fastembed registry (only 384-dim fits the
  // vec0 schema). Both settings autosave; "Recompute" re-arms the worker
  // over the existing corpus (POST /api/embed/start).

  import { onMount } from 'svelte';
  import {
    ApiError,
    getEmbedProgress,
    getSetting,
    listEmbedModels,
    putSetting,
    startEmbed,
    type EmbedModel,
    type EmbedProgress,
  } from '$lib/api';
  import { toastStore } from '$lib/stores/toast.svelte';

  let models = $state<EmbedModel[]>([]);
  let model = $state('');
  let autoStart = $state(true);
  let progress = $state<EmbedProgress | null>(null);
  let loaded = $state(false);
  let loadError = $state<string | null>(null);
  let recomputing = $state(false);

  onMount(() => void load());

  async function load(): Promise<void> {
    loadError = null;
    try {
      const [list, current, auto, prog] = await Promise.all([
        listEmbedModels(),
        getSetting<string>('embedding.model').catch(() => null),
        getSetting<string>('embedding.auto_start').catch(() => null),
        getEmbedProgress().catch(() => null),
      ]);
      models = list.models;
      if (current?.value) model = current.value;
      autoStart = auto?.value !== 'false';
      progress = prog;
      loaded = true;
    } catch (err) {
      loadError = err instanceof Error ? err.message : String(err);
    }
  }

  function errMsg(err: unknown): string {
    if (err instanceof ApiError) {
      const body = err.body as { message?: string } | undefined;
      return body?.message ?? err.message;
    }
    return err instanceof Error ? err.message : String(err);
  }

  async function saveModel(value: string): Promise<void> {
    model = value;
    try {
      await putSetting('embedding.model', value);
      toastStore.show('Model saved — recompute to re-embed the corpus.', 'info');
    } catch (err) {
      toastStore.show(`Save failed: ${errMsg(err)}`, 'error');
    }
  }

  async function saveAutoStart(value: boolean): Promise<void> {
    autoStart = value;
    try {
      await putSetting('embedding.auto_start', value);
    } catch (err) {
      autoStart = !value;
      toastStore.show(`Save failed: ${errMsg(err)}`, 'error');
    }
  }

  async function recompute(): Promise<void> {
    if (recomputing) return;
    recomputing = true;
    try {
      await startEmbed();
      progress = await getEmbedProgress().catch(() => progress);
      toastStore.show('Embedding worker started.', 'info');
    } catch (err) {
      toastStore.show(`Recompute failed: ${errMsg(err)}`, 'error');
    } finally {
      recomputing = false;
    }
  }
</script>

<div class="tab">
  {#if loadError}
    <p class="empty error">{loadError}</p>
  {:else if !loaded}
    <p class="empty">Loading…</p>
  {:else}
    <label class="field">
      <span>Embedding model</span>
      <select value={model} onchange={(e) => void saveModel(e.currentTarget.value)}>
        {#if !model}
          <option value="" disabled selected>Select a model…</option>
        {/if}
        {#each models as m (m.model)}
          <option value={m.model}>
            {m.model}{m.size_in_GB ? ` (${m.size_in_GB} GB)` : ''}
          </option>
        {/each}
      </select>
      <span class="hint">
        Only 384-dimension models are listed — the vector index is fixed at
        384 dims.
      </span>
    </label>

    <label class="check">
      <input
        type="checkbox"
        checked={autoStart}
        onchange={(e) => void saveAutoStart((e.target as HTMLInputElement).checked)}
      />
      <span>Auto-start the embedding worker with the backend</span>
    </label>

    <div class="recompute">
      <div class="coverage">
        {#if progress}
          <span class="cov-pct">{progress.percent}%</span>
          <span class="cov-detail">
            {progress.embedded} / {progress.eligible} pages embedded
          </span>
        {:else}
          <span class="cov-detail">Coverage unavailable</span>
        {/if}
      </div>
      <button
        type="button"
        class="btn"
        onclick={() => void recompute()}
        disabled={recomputing}
      >
        {recomputing ? 'Starting…' : 'Recompute embeddings'}
      </button>
    </div>
    <p class="hint">
      Recompute re-arms the worker over any pages missing an embedding —
      run it after changing the model.
    </p>
  {/if}
</div>

<style>
  .tab {
    display: flex;
    flex-direction: column;
    gap: 14px;
    font-size: 12px;
  }
  .empty {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
  }
  .empty.error {
    color: #ff8899;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .field > span:first-child {
    color: var(--muted);
  }
  .field select {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 3px;
    padding: 5px 7px;
    font: inherit;
    font-size: 12px;
    width: 100%;
  }
  .field select:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 7px;
    cursor: pointer;
  }
  .check input {
    cursor: pointer;
  }
  .hint {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
  }
  .recompute {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 8px 10px;
  }
  .coverage {
    display: flex;
    align-items: baseline;
    gap: 8px;
    min-width: 0;
  }
  .cov-pct {
    color: var(--accent);
    font-size: 16px;
    font-variant-numeric: tabular-nums;
  }
  .cov-detail {
    color: var(--muted);
    font-size: 11px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .btn {
    flex: 0 0 auto;
    background: transparent;
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 5px 12px;
    font-size: 11px;
    cursor: pointer;
    border-radius: 3px;
    white-space: nowrap;
  }
  .btn:hover:not(:disabled) {
    background: rgba(0, 212, 170, 0.1);
  }
  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
