<script lang="ts">
  // Settings → Crawl & Queue. Durable crawl policy that does not belong in a
  // per-crawl control: the request pacing profile (crawl.pacing) and the
  // queue dispatch gate (crawl.queue_paused). Both autosave on change.
  //
  // Pacing is read by the crawl runtime at crawl start (crawler/runtime.py
  // _PACING_RANGES). queue_paused is a durable gate: when set, the queue
  // runner keeps accepting intake but stops dispatching work
  // (services/crawl_queue_runner.py) — the same key the bottom-pane Activity
  // controls flip for a quick pause, surfaced here as the durable default.

  import { onMount } from 'svelte';
  import { ApiError, getSetting, putSetting } from '$lib/api';
  import { toastStore } from '$lib/stores/toast.svelte';

  type Pacing = 'fast' | 'polite' | 'stealth';

  let pacing = $state<Pacing>('polite');
  let queuePaused = $state(false);
  let loaded = $state(false);

  onMount(() => void load());

  async function load(): Promise<void> {
    try {
      const [p, q] = await Promise.all([
        getSetting<string>('crawl.pacing').catch(() => null),
        getSetting<string>('crawl.queue_paused').catch(() => null),
      ]);
      if (p?.value === 'fast' || p?.value === 'polite' || p?.value === 'stealth') {
        pacing = p.value;
      }
      queuePaused = q?.value === 'true';
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

  async function savePacing(value: Pacing): Promise<void> {
    const prev = pacing;
    pacing = value;
    try {
      await putSetting('crawl.pacing', value);
    } catch (err) {
      pacing = prev;
      toastStore.show(`Save failed: ${errMsg(err)}`, 'error');
    }
  }

  async function saveQueuePaused(value: boolean): Promise<void> {
    queuePaused = value;
    try {
      await putSetting('crawl.queue_paused', value);
    } catch (err) {
      queuePaused = !value;
      toastStore.show(`Save failed: ${errMsg(err)}`, 'error');
    }
  }
</script>

<div class="tab">
  <label class="field">
    <span>Request pacing</span>
    <select
      value={pacing}
      disabled={!loaded}
      onchange={(e) => void savePacing(e.currentTarget.value as Pacing)}
    >
      <option value="fast">Fast — no delay between requests</option>
      <option value="polite">Polite — short jittered delay (default)</option>
      <option value="stealth">Stealth — human-scale jittered think-time</option>
    </select>
    <span class="hint">
      Applied when a crawl starts. Slower profiles blend crawl traffic into
      ordinary browsing cadence and ease load on the target site.
    </span>
  </label>

  <label class="check">
    <input
      type="checkbox"
      checked={queuePaused}
      disabled={!loaded}
      onchange={(e) => void saveQueuePaused((e.target as HTMLInputElement).checked)}
    />
    <span>
      Pause queue dispatch — keep accepting new work but stop running it
    </span>
  </label>
  <span class="hint indent">
    Intake continues while paused; queued jobs resume dispatching the moment
    this is cleared.
  </span>
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
    flex: 0 0 auto;
  }
  .hint {
    color: var(--muted);
    font-size: 11px;
  }
  .hint.indent {
    margin-top: -10px;
    padding-left: 21px;
  }
</style>
