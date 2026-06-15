<script lang="ts">
  // Settings → LLM / Ollama. Durable configuration for the local analysis
  // worker: the Ollama endpoint (llm.ollama_url), the default model
  // (llm.model), the per-tick worker batch size (llm.batch_size), and whether
  // the worker auto-starts with the backend (llm.auto_start). All autosave.
  //
  // The endpoint validator (security/net.py validate_ollama_url) is loopback-
  // only — http://(127.0.0.1|::1):<port> — keeping LLM traffic on the machine
  // and off Tor. The model is a free-text Ollama tag (qwen2.5:3b,
  // llama3.2:3b-instruct-q4_K_M, …); there is no installed-models endpoint and
  // the backend validates only non-empty/length, so we mirror that with a
  // plain input rather than a fake dropdown. Batch size is the single worker
  // capacity number (1–50) also surfaced in the Intel worker controls; this is
  // its durable home.

  import { onMount } from 'svelte';
  import { ApiError, getSetting, putSetting } from '$lib/api';
  import { toastStore } from '$lib/stores/toast.svelte';

  const DEFAULT_OLLAMA_URL = 'http://127.0.0.1:11434';
  const DEFAULT_MODEL = 'qwen2.5:3b';
  const DEFAULT_BATCH = 5;

  let ollamaUrl = $state('');
  let model = $state('');
  let batchSize = $state(DEFAULT_BATCH);
  let autoStart = $state(false);
  let loaded = $state(false);

  onMount(() => void load());

  async function load(): Promise<void> {
    try {
      const [u, m, b, a] = await Promise.all([
        getSetting<string>('llm.ollama_url').catch(() => null),
        getSetting<string>('llm.model').catch(() => null),
        getSetting<string>('llm.batch_size').catch(() => null),
        getSetting<string>('llm.auto_start').catch(() => null),
      ]);
      ollamaUrl = u?.value || DEFAULT_OLLAMA_URL;
      model = m?.value || DEFAULT_MODEL;
      const parsed = b?.value ? Number(b.value) : NaN;
      batchSize = Number.isFinite(parsed) ? parsed : DEFAULT_BATCH;
      autoStart = a?.value === 'true';
      loaded = true;
    } catch {
      loaded = true;
    }
  }

  function errMsg(err: unknown): string {
    if (err instanceof ApiError) {
      const body = err.body as { message?: string } | undefined;
      return body?.message ?? err.message;
    }
    return err instanceof Error ? err.message : String(err);
  }

  async function saveUrl(): Promise<void> {
    const value = ollamaUrl.trim();
    if (!value) return; // empty = leave the stored value (clearing unsupported)
    try {
      const res = await putSetting('llm.ollama_url', value);
      ollamaUrl = (res.value as string) ?? value;
      toastStore.show('Ollama endpoint saved.', 'info');
    } catch (err) {
      toastStore.show(`Invalid endpoint: ${errMsg(err)}`, 'error');
    }
  }

  async function saveModel(): Promise<void> {
    const value = model.trim();
    if (!value) return;
    try {
      const res = await putSetting('llm.model', value);
      model = (res.value as string) ?? value;
      toastStore.show('Default model saved.', 'info');
    } catch (err) {
      toastStore.show(`Invalid model: ${errMsg(err)}`, 'error');
    }
  }

  async function saveBatchSize(): Promise<void> {
    try {
      const res = await putSetting('llm.batch_size', batchSize);
      batchSize = Number(res.value);
      toastStore.show('Batch size saved.', 'info');
    } catch (err) {
      toastStore.show(`Invalid batch size: ${errMsg(err)}`, 'error');
      await load(); // reset to the stored value
    }
  }

  async function saveAutoStart(value: boolean): Promise<void> {
    autoStart = value;
    try {
      await putSetting('llm.auto_start', value);
    } catch (err) {
      autoStart = !value;
      toastStore.show(`Save failed: ${errMsg(err)}`, 'error');
    }
  }
</script>

<div class="tab">
  <label class="field">
    <span>Ollama endpoint</span>
    <input
      type="text"
      placeholder={DEFAULT_OLLAMA_URL}
      bind:value={ollamaUrl}
      disabled={!loaded}
      onchange={() => void saveUrl()}
    />
    <span class="hint">
      Loopback only — <code>http://127.0.0.1:&lt;port&gt;</code> (or
      <code>::1</code>). LLM analysis stays local and never routes through Tor.
    </span>
  </label>

  <label class="field">
    <span>Default model</span>
    <input
      type="text"
      placeholder={DEFAULT_MODEL}
      bind:value={model}
      disabled={!loaded}
      onchange={() => void saveModel()}
    />
    <span class="hint">
      The Ollama tag the analysis worker pulls when a job doesn't override it.
      Make sure it's already pulled in Ollama (<code>ollama pull …</code>).
    </span>
  </label>

  <label class="field narrow">
    <span>Worker batch size</span>
    <input
      type="number"
      min="1"
      max="50"
      step="1"
      bind:value={batchSize}
      disabled={!loaded}
      onchange={() => void saveBatchSize()}
    />
    <span class="hint">
      Analysis jobs the worker drains per tick (1–50). Higher finishes a backlog
      faster but loads Ollama harder.
    </span>
  </label>

  <label class="check">
    <input
      type="checkbox"
      checked={autoStart}
      disabled={!loaded}
      onchange={(e) => void saveAutoStart((e.target as HTMLInputElement).checked)}
    />
    <span>Auto-start the analysis worker with the backend</span>
  </label>
</div>

<style>
  .tab {
    display: flex;
    flex-direction: column;
    gap: 14px;
    font-size: 12px;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .field.narrow input {
    width: 120px;
  }
  .field > span:first-child {
    color: var(--muted);
  }
  .field input {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 3px;
    padding: 5px 7px;
    font: inherit;
    font-size: 12px;
    width: 100%;
  }
  .field input:focus-visible {
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
    flex: 0 0 auto;
  }
  .hint {
    color: var(--muted);
    font-size: 11px;
  }
  code {
    font-size: 11px;
    color: var(--text);
  }
</style>
