<script lang="ts">
  // Settings → Retention. Job-history retention only: delete terminal
  // job-tracking rows (completed crawls, analyses, probes) finished more than
  // N days ago. The window (retention.jobs_days) autosaves; 0 = keep forever
  // (the default). Enforced at backend startup and on the "Run cleanup now"
  // button (POST /api/retention/run).
  //
  // Deliberately scoped to bookkeeping only. Page snapshots and the page
  // version-history / diff record are NOT pruned here — that history is
  // investigation evidence, so retention stays off it by design. This tab says
  // so explicitly rather than offering a control that would erase it.

  import { onMount } from 'svelte';
  import {
    ApiError,
    getRetentionStatus,
    getSetting,
    putSetting,
    runRetention,
  } from '$lib/api';
  import { toastStore } from '$lib/stores/toast.svelte';

  let jobsDays = $state(0);
  let eligible = $state(0);
  let loaded = $state(false);
  let running = $state(false);

  onMount(() => void load());

  async function load(): Promise<void> {
    try {
      const [setting, status] = await Promise.all([
        getSetting<string>('retention.jobs_days').catch(() => null),
        getRetentionStatus().catch(() => null),
      ]);
      const parsed = setting?.value ? Number(setting.value) : NaN;
      jobsDays = Number.isFinite(parsed) ? parsed : 0;
      if (status) eligible = status.eligible_jobs;
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

  async function refreshEligible(): Promise<void> {
    const status = await getRetentionStatus().catch(() => null);
    if (status) eligible = status.eligible_jobs;
  }

  async function saveDays(): Promise<void> {
    try {
      const res = await putSetting('retention.jobs_days', jobsDays);
      jobsDays = Number(res.value);
      await refreshEligible();
    } catch (err) {
      toastStore.show(`Invalid value: ${errMsg(err)}`, 'error');
      await load(); // reset to the stored value
    }
  }

  async function runNow(): Promise<void> {
    if (running) return;
    running = true;
    try {
      const res = await runRetention();
      await refreshEligible();
      toastStore.show(
        res.deleted_jobs > 0
          ? `Removed ${res.deleted_jobs} old job record${res.deleted_jobs === 1 ? '' : 's'}.`
          : 'No job records were old enough to remove.',
        'info',
      );
    } catch (err) {
      toastStore.show(`Cleanup failed: ${errMsg(err)}`, 'error');
    } finally {
      running = false;
    }
  }
</script>

<div class="tab">
  <label class="field narrow">
    <span>Keep finished job records for</span>
    <div class="days-row">
      <input
        type="number"
        min="0"
        max="3650"
        step="1"
        bind:value={jobsDays}
        disabled={!loaded}
        onchange={() => void saveDays()}
      />
      <span class="unit">days</span>
    </div>
    <span class="hint">
      Completed crawls, analyses, and monitor probes leave a tracking record in
      the Activity view. Older records are deleted automatically at startup and
      when you run cleanup below. <strong>0 = keep forever</strong> (off).
    </span>
  </label>

  <div class="runbox">
    <div class="eligible">
      {#if jobsDays > 0}
        <span class="count">{eligible}</span>
        <span class="count-detail">record{eligible === 1 ? '' : 's'} eligible to remove now</span>
      {:else}
        <span class="count-detail">Retention is off — nothing is being removed.</span>
      {/if}
    </div>
    <button
      type="button"
      class="btn"
      onclick={() => void runNow()}
      disabled={running || jobsDays <= 0}
    >
      {running ? 'Cleaning…' : 'Run cleanup now'}
    </button>
  </div>

  <p class="note">
    Only work-tracking bookkeeping is affected. Saved page snapshots, the page
    version history and diffs, analyses, flags, and notes are never deleted by
    retention — that history is part of the investigation record.
  </p>
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
  .days-row {
    display: flex;
    align-items: center;
    gap: 7px;
  }
  .field.narrow input {
    width: 90px;
  }
  .field input {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 3px;
    padding: 5px 7px;
    font: inherit;
    font-size: 12px;
  }
  .field input:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .unit {
    color: var(--muted);
  }
  .hint {
    color: var(--muted);
    font-size: 11px;
  }
  .hint strong {
    color: var(--text);
    font-weight: 600;
  }
  .runbox {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 8px 10px;
  }
  .eligible {
    display: flex;
    align-items: baseline;
    gap: 8px;
    min-width: 0;
  }
  .count {
    color: var(--accent);
    font-size: 16px;
    font-variant-numeric: tabular-nums;
  }
  .count-detail {
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
  .note {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
    line-height: 1.5;
  }
</style>
