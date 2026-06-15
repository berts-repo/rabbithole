<script lang="ts">
  // Bottom pane — Scheduled Crawls recipe tab.
  //
  // Relocated from the left sidebar by the pane-responsibility-reset
  // package: the left pane composes work, the bottom pane manages work that
  // already exists. Recipe-list pattern — an add form plus rows with
  // pause/resume + delete. Widened for the bottom pane's horizontal space.

  import { Pause, Play, X } from 'lucide-svelte';
  import { EmptyState, IconButton } from '$lib/ui';
  import {
    createSchedule,
    deleteSchedule,
    listSchedules,
    patchSchedule,
    ApiError,
    type Schedule,
  } from '$lib/api';
  import { isSupportedUrl } from '$lib/onionUrl';
  import { toastStore } from '$lib/stores/toast.svelte';

  type Mode = 'Cross-site' | 'BFS' | 'DFS' | 'Diverse' | 'Focused';
  const MODES: Mode[] = ['Cross-site', 'BFS', 'DFS', 'Diverse', 'Focused'];
  const MIN_INTERVAL_HOURS = 0.25;

  let schedules = $state<Schedule[]>([]);
  let url = $state('');
  let label = $state('');
  let intervalHours = $state<number>(24);
  let mode = $state<Mode>('BFS');
  let adding = $state(false);
  let refreshTimer: ReturnType<typeof setInterval> | null = null;

  $effect(() => {
    void refresh();
    refreshTimer = setInterval(() => void refresh(), 30_000);
    return () => {
      if (refreshTimer !== null) clearInterval(refreshTimer);
    };
  });

  async function refresh() {
    try {
      const r = await listSchedules();
      schedules = r.schedules;
    } catch {
      // Background refresh — silent on failure.
    }
  }

  async function onAdd(e: SubmitEvent) {
    e.preventDefault();
    if (!isSupportedUrl(url)) {
      toastStore.show('Enter a valid .onion or .i2p URL first.', 'warn');
      return;
    }
    if (!Number.isFinite(intervalHours) || intervalHours < MIN_INTERVAL_HOURS) {
      toastStore.show(`Interval must be at least ${MIN_INTERVAL_HOURS} h.`, 'warn');
      return;
    }
    adding = true;
    try {
      await createSchedule({
        url: url.trim(),
        label: label.trim() || null,
        interval_hours: intervalHours,
        mode,
      });
      url = '';
      label = '';
      await refresh();
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? String((e.body as { message?: string })?.message ?? e.message)
          : String(e);
      toastStore.show(`Add failed: ${msg}`, 'error');
    } finally {
      adding = false;
    }
  }

  async function togglePause(s: Schedule) {
    try {
      await patchSchedule(s.url, { active: !s.active });
      await refresh();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Update failed: ${msg}`, 'error');
    }
  }

  async function onDelete(s: Schedule) {
    if (!confirm(`Remove schedule for ${s.url}?`)) return;
    try {
      await deleteSchedule(s.url);
      await refresh();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Delete failed: ${msg}`, 'error');
    }
  }
</script>

<div class="sched">
  <form class="add" onsubmit={onAdd}>
    <input class="grow" type="text" bind:value={url} placeholder="http://…onion/" />
    <input class="grow" type="text" bind:value={label} placeholder="Label (optional)" />
    <label class="field">
      <span>Interval (h)</span>
      <input
        type="number"
        step="0.25"
        min={MIN_INTERVAL_HOURS}
        bind:value={intervalHours}
      />
    </label>
    <label class="field">
      <span>Mode</span>
      <select bind:value={mode}>
        {#each MODES as m (m)}
          <option value={m}>{m}</option>
        {/each}
      </select>
    </label>
    <button type="submit" class="add-btn" disabled={adding}>
      {adding ? 'Adding…' : '+ Add'}
    </button>
  </form>

  {#if schedules.length === 0}
    <EmptyState title="No scheduled crawls." />
  {:else}
    <ul>
      {#each schedules as s (s.url)}
        <li>
          <div class="info">
            <div class="primary">
              <span class="label">{s.label || s.url}</span>
              <span class="mode">{s.mode}</span>
            </div>
            <div class="meta">every {s.interval_hours}h · {s.url}</div>
          </div>
          <IconButton
            label={s.active ? 'Pause schedule' : 'Resume schedule'}
            size="small"
            onclick={() => togglePause(s)}
          >
            {#if s.active}
              <Pause size={12} />
            {:else}
              <Play size={12} />
            {/if}
          </IconButton>
          <IconButton
            label="Remove schedule"
            size="small"
            onclick={() => onDelete(s)}
          >
            <X size={12} />
          </IconButton>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .sched {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .add {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: 8px;
    padding: 10px;
    border: 1px solid var(--border);
  }
  .grow {
    flex: 1 1 200px;
    min-width: 160px;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 3px;
    font-size: 10px;
    color: var(--muted);
  }
  .field input,
  .field select {
    width: 110px;
  }
  input,
  select {
    background: #17191f;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 4px 7px;
    font-size: 11px;
  }
  option {
    background: #17191f;
    color: var(--text);
  }
  input:focus-visible,
  select:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .add-btn {
    background: transparent;
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 5px 14px;
    cursor: pointer;
    font-size: 11px;
  }
  .add-btn:disabled {
    opacity: 0.55;
    cursor: progress;
  }
  .add-btn:hover:not(:disabled) {
    background: var(--accent-bg);
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  li {
    display: flex;
    gap: 6px;
    align-items: stretch;
    padding: 6px 8px;
    border: 1px solid var(--border);
  }
  .info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .primary {
    display: flex;
    gap: 8px;
    min-width: 0;
    font-size: 11px;
  }
  .label {
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .mode {
    color: var(--accent);
    font-size: 10px;
  }
  .meta {
    color: var(--muted);
    font-size: 10px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
