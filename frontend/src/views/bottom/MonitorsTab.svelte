<script lang="ts">
  // Bottom pane — Monitors recipe tab (pane-responsibility-reset).
  //
  // The global uptime-monitor list. Mirrors the Scheduled Crawls recipe
  // pattern: a toolbar add button plus rows with pause/resume + delete.
  // Today monitors are also created per-domain from the right-pane Domain
  // tab; this tab is the project-wide list. Create flow reuses the shared
  // AddMonitorModal.

  import { Pause, Play, Plus, X } from 'lucide-svelte';
  import {
    deleteMonitor,
    listMonitors,
    patchMonitor,
    type Monitor,
  } from '$lib/api';
  import AddMonitorModal from '../../components/modals/AddMonitorModal.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { explainApiError } from '$lib/contextMenu/actions';
  import { EmptyState, IconButton } from '$lib/ui';

  let monitors = $state<Monitor[]>([]);
  let addOpen = $state(false);
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
      const r = await listMonitors();
      monitors = r.monitors;
    } catch {
      // Background refresh — silent on failure.
    }
  }

  async function toggle(m: Monitor) {
    try {
      const updated = await patchMonitor(m.id, { enabled: !m.enabled });
      monitors = monitors.map((x) => (x.id === m.id ? updated : x));
    } catch (err) {
      toastStore.show(explainApiError(err, 'Monitor toggle failed'), 'error');
    }
  }

  async function remove(m: Monitor) {
    if (!confirm(`Remove monitor for ${m.url}?`)) return;
    try {
      await deleteMonitor(m.id);
      monitors = monitors.filter((x) => x.id !== m.id);
    } catch (err) {
      toastStore.show(explainApiError(err, 'Monitor remove failed'), 'error');
    }
  }

  function statusLabel(s: number | null): {
    text: string;
    tone: 'good' | 'bad' | 'muted';
  } {
    if (s === null) return { text: '—', tone: 'muted' };
    if (s === 200) return { text: 'Up', tone: 'good' };
    return { text: String(s), tone: 'bad' };
  }

  function onAddClose() {
    addOpen = false;
    void refresh();
  }
</script>

<div class="mon">
  <div class="toolbar">
    <button type="button" class="add-btn" onclick={() => (addOpen = true)}>
      <Plus size={12} /> Add monitor
    </button>
  </div>

  {#if monitors.length === 0}
    <EmptyState title="No monitors." />
  {:else}
    <ul>
      {#each monitors as m (m.id)}
        {@const st = statusLabel(m.last_status)}
        <li>
          <div class="info">
            <div class="primary">
              <span class="label">{m.label || m.url}</span>
              <span class="status tone-{st.tone}">{st.text}</span>
            </div>
            <div class="meta">every {m.interval_hours}h · {m.url}</div>
          </div>
          <IconButton
            label={m.enabled ? 'Pause monitor' : 'Resume monitor'}
            size="small"
            onclick={() => toggle(m)}
          >
            {#if m.enabled}
              <Pause size={12} />
            {:else}
              <Play size={12} />
            {/if}
          </IconButton>
          <IconButton
            label="Remove monitor"
            size="small"
            onclick={() => remove(m)}
          >
            <X size={12} />
          </IconButton>
        </li>
      {/each}
    </ul>
  {/if}
</div>

{#if addOpen}
  <AddMonitorModal url="" onClose={onAddClose} />
{/if}

<style>
  .mon {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .toolbar {
    display: flex;
  }
  .add-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: transparent;
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 5px 12px;
    cursor: pointer;
    font-size: 11px;
  }
  .add-btn:hover {
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
  .status {
    font-size: 10px;
  }
  .tone-good {
    color: var(--accent);
  }
  .tone-bad {
    color: #ff5577;
  }
  .tone-muted {
    color: var(--muted);
  }
  .meta {
    color: var(--muted);
    font-size: 10px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
