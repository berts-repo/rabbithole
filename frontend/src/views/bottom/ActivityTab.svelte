<script lang="ts">
  // Activity sub-tab — the unified `jobs` view. One row per piece of work
  // across every kind (crawl / schedule / analysis / probe / live-crawl /
  // batch), under one status vocabulary, live via the jobs SSE store.
  // Replaces the old Analyses tab and absorbs the crawl-queue list.
  //
  // Subscription lifecycle mirrors LiveCrawlTab: subscribe on mount,
  // unsubscribe on teardown. The store is ref-counted and reload-per-event,
  // so the list is always authoritative and tab switches are instant.
  //
  // Filter (by kind) / sort (recency) / group (none/status/target) live in
  // the pure activity.ts helpers; this component only wires them to reactive
  // state, resolves target labels from graphStore.payload, and runs the row
  // actions (cancel/retry/pause/resume) which call the jobs API then force a
  // store refresh.
  //
  // Selection model: a url-target row click is a FULL selection (bottom-pane
  // row click per CLAUDE.md) — fullSelect(target_id) + the right tab that
  // matches the kind. Non-url targets (domain/collection/cluster) have no
  // node id to focus yet, so their rows are not clickable in v1.

  import { onMount } from 'svelte';
  import { Ban, Pause, Play, Rocket, RotateCcw } from 'lucide-svelte';
  import {
    cancelJob,
    retryJob,
    pauseJob,
    resumeJob,
    runBatch,
    stageBatch,
    ApiError,
    type Job,
    type GraphNode,
  } from '$lib/api';
  import { EmptyState, IconButton, StatusBadge, TextButton } from '$lib/ui';
  import { jobsStore } from '$lib/stores/jobs.svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { navigationStore } from '$lib/stores/navigation.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import {
    KIND_FILTER_OPTIONS,
    batchUrlCount,
    canCancel,
    canOpenTarget,
    canPause,
    canResume,
    canRetry,
    canRunBatch,
    filterByKind,
    formatJobTime,
    groupJobs,
    sortJobsByRecency,
    toActivityRow,
    type GroupMode,
    type KindFilterValue,
  } from './activity';

  // Crawl modes the batch composer offers — mirrors crawl_db.VALID_MODES.
  const BATCH_MODES = ['Cross-site', 'BFS', 'DFS', 'Diverse', 'Focused'];

  let kindFilter = $state<KindFilterValue>('all');
  let groupMode = $state<GroupMode>('none');

  // Batch-intake composer state.
  let composerOpen = $state(false);
  let batchText = $state('');
  let batchMode = $state('Cross-site');
  let staging = $state(false);

  onMount(() => {
    const unsubscribe = jobsStore.subscribe();
    return () => unsubscribe();
  });

  const jobs = $derived(jobsStore.jobs);

  // id → node lookup so url-target rows can show the real URL and full-select
  // on click. Rebuilds whenever the payload changes.
  const nodeById = $derived.by<Map<number, GraphNode>>(() => {
    const map = new Map<number, GraphNode>();
    const nodes = graphStore.payload?.nodes;
    if (!nodes) return map;
    for (const n of nodes) map.set(n.id, n);
    return map;
  });

  // Target label resolver (design decision 1): a url target enriches from the
  // graph payload when present, otherwise every kind falls back to a
  // `{type} #{id}` placeholder. Richer domain/collection/cluster lookups are
  // deferred.
  function labelFor(job: Job): string {
    if (job.kind === 'batch') {
      const n = batchUrlCount(job);
      return n === null ? 'batch' : `${n} URL${n === 1 ? '' : 's'}`;
    }
    if (job.target_type === 'url') {
      const node = nodeById.get(job.target_id);
      if (node) return node.raw_url;
    }
    return `${job.target_type} #${job.target_id}`;
  }

  const filtered = $derived(filterByKind(jobs, kindFilter));
  const sorted = $derived(sortJobsByRecency(filtered));
  const groups = $derived(groupJobs(sorted, groupMode, labelFor));

  function onRowClick(job: Job): void {
    if (!canOpenTarget(job)) return;
    selectionStore.fullSelect(job.target_id);
    navigationStore.setRight(job.kind === 'analysis' ? 'analysis' : 'page');
  }

  // Stage a batch from the pasted URL list (one URL per line). The backend
  // validates + de-dupes; we surface staged/rejected counts via toast and
  // collapse the composer on success.
  async function onStage(): Promise<void> {
    const urls = batchText
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l.length > 0);
    if (urls.length === 0) {
      toastStore.show('Paste at least one URL to stage a batch.', 'info');
      return;
    }
    staging = true;
    try {
      const res = await stageBatch({ urls, mode: batchMode, source: 'bulk' });
      const rejected = res.rejected.length;
      toastStore.show(
        `Staged ${res.staged} URL${res.staged === 1 ? '' : 's'}` +
          (rejected ? ` (${rejected} rejected)` : ''),
        rejected ? 'warn' : 'info',
      );
      batchText = '';
      composerOpen = false;
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) {
        const body = e.body as { message?: string } | null;
        toastStore.show(body?.message ?? 'No valid URLs to stage.', 'warn');
      } else {
        const msg = e instanceof Error ? e.message : String(e);
        toastStore.show(`Stage failed: ${msg}`, 'error');
      }
    } finally {
      staging = false;
      void jobsStore.refresh();
    }
  }

  async function onRun(job: Job): Promise<void> {
    try {
      const res = await runBatch(job.id);
      toastStore.show(
        `Spawned ${res.spawned} crawl${res.spawned === 1 ? '' : 's'}` +
          (res.skipped ? ` (${res.skipped} already queued)` : ''),
        'info',
      );
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const body = e.body as { message?: string } | null;
        toastStore.show(body?.message ?? 'Batch can no longer run.', 'warn');
      } else {
        const msg = e instanceof Error ? e.message : String(e);
        toastStore.show(`Run failed: ${msg}`, 'error');
      }
    } finally {
      void jobsStore.refresh();
    }
  }

  // Row actions. Each calls the jobs API then forces an authoritative store
  // refresh so the row reflects the transition without waiting for the SSE
  // round-trip. A 409 surfaces the backend's `{error,message}` body via toast
  // (the action raced another writer); other failures toast the error string.
  async function runAction(
    label: string,
    fn: () => Promise<unknown>,
  ): Promise<void> {
    try {
      await fn();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const body = e.body as { message?: string } | null;
        toastStore.show(body?.message ?? `${label} not allowed.`, 'warn');
      } else {
        const msg = e instanceof Error ? e.message : String(e);
        toastStore.show(`${label} failed: ${msg}`, 'error');
      }
    } finally {
      void jobsStore.refresh();
    }
  }

  const onCancel = (job: Job) =>
    runAction('Cancel', () => cancelJob(job.id));
  const onRetry = (job: Job) => runAction('Retry', () => retryJob(job.id));
  const onPause = (job: Job) => runAction('Pause', () => pauseJob(job.id));
  const onResume = (job: Job) => runAction('Resume', () => resumeJob(job.id));

  const activeNodeId = $derived(
    selectionStore.selectMode === 'full' ? selectionStore.selectedNodeId : null,
  );
</script>

<section class="activity">
  <header class="head">
    <select
      class="select"
      bind:value={kindFilter}
      aria-label="Filter by kind"
    >
      {#each KIND_FILTER_OPTIONS as o (o.value)}
        <option value={o.value}>{o.label}</option>
      {/each}
    </select>
    <select class="select" bind:value={groupMode} aria-label="Group rows">
      <option value="none">No grouping</option>
      <option value="status">Group by status</option>
      <option value="target">Group by target</option>
    </select>
    <span class="count" title="Filtered / total">
      {filtered.length}{filtered.length === jobs.length
        ? ''
        : ` / ${jobs.length}`}
    </span>
    {#if jobsStore.loading && jobsStore.loaded}
      <span class="poll" title="Refreshing">⟳</span>
    {/if}
    <span class="spacer"></span>
    <TextButton
      size="small"
      variant={composerOpen ? 'primary' : 'secondary'}
      onclick={() => (composerOpen = !composerOpen)}
    >
      {composerOpen ? 'Close' : 'New batch'}
    </TextButton>
  </header>

  {#if composerOpen}
    <div class="composer">
      <textarea
        class="batch-urls"
        rows="3"
        placeholder="Paste onion URLs, one per line…"
        bind:value={batchText}
        aria-label="Batch URLs"
      ></textarea>
      <div class="composer-row">
        <select class="select" bind:value={batchMode} aria-label="Crawl mode">
          {#each BATCH_MODES as m (m)}
            <option value={m}>{m}</option>
          {/each}
        </select>
        <span class="spacer"></span>
        <TextButton
          size="small"
          variant="primary"
          disabled={staging}
          onclick={onStage}
        >
          {staging ? 'Staging…' : 'Stage batch'}
        </TextButton>
      </div>
    </div>
  {/if}

  {#if jobsStore.error && !jobsStore.loaded}
    <EmptyState title="Couldn't load activity." body={jobsStore.error} error />
  {:else if !jobsStore.loaded}
    <EmptyState title="Loading activity…" />
  {:else if jobs.length === 0}
    <EmptyState
      title="No activity yet."
      body="Crawls, analyses, probes, and schedules appear here as they run."
    />
  {:else if filtered.length === 0}
    <EmptyState title="No activity matches this filter." />
  {:else}
    {#each groups as group (group.key)}
      {#if group.label}
        <div class="group-head">
          <span class="group-label">{group.label}</span>
          <span class="group-count">{group.jobs.length}</span>
        </div>
      {/if}
      <ul class="list">
        {#each group.jobs as job (job.id)}
          {@const row = toActivityRow(job, labelFor(job))}
          {@const clickable = canOpenTarget(job)}
          {@const active =
            clickable &&
            job.target_id === activeNodeId}
          <li>
            <div class="row" class:active class:clickable>
              {#if clickable}
                <button
                  type="button"
                  class="rowmain"
                  onclick={() => onRowClick(job)}
                  title="Open target in right pane"
                >
                  <span class="kind" title={row.kind}>{row.kind}</span>
                  <span class="target" title={row.target.label}>
                    {row.target.label}
                  </span>
                </button>
              {:else}
                <div class="rowmain static">
                  <span class="kind" title={row.kind}>{row.kind}</span>
                  <span class="target placeholder" title={row.target.label}>
                    {row.target.label}
                  </span>
                </div>
              {/if}

              {#if row.progress}
                <span
                  class="progress"
                  title="{row.progress.current} / {row.progress.total}"
                >
                  {row.progress.current}/{row.progress.total}
                </span>
              {:else if row.contentChanged}
                <span class="progress changed" title="Content changed since the previous probe">
                  changed
                </span>
              {:else}
                <span class="progress muted">—</span>
              {/if}

              <span class="time" title={row.finishedAt ?? row.startedAt ?? ''}>
                {formatJobTime(row.finishedAt ?? row.startedAt)}
              </span>

              <StatusBadge status={row.status} tooltip={row.error ?? undefined} />

              <div class="actions">
                {#if job.kind === 'batch'}
                  {#if canRunBatch(job)}
                    <IconButton
                      label="Run batch"
                      size="small"
                      variant="ghost"
                      onclick={() => onRun(job)}
                    >
                      <Rocket size={11} />
                    </IconButton>
                  {/if}
                  {#if canCancel(job.status)}
                    <IconButton
                      label="Discard batch"
                      size="small"
                      variant="ghost"
                      onclick={() => onCancel(job)}
                    >
                      <Ban size={11} />
                    </IconButton>
                  {/if}
                {:else}
                {#if canPause(job.status)}
                  <IconButton
                    label="Pause job"
                    size="small"
                    variant="ghost"
                    onclick={() => onPause(job)}
                  >
                    <Pause size={11} />
                  </IconButton>
                {/if}
                {#if canResume(job.status)}
                  <IconButton
                    label="Resume job"
                    size="small"
                    variant="ghost"
                    onclick={() => onResume(job)}
                  >
                    <Play size={11} />
                  </IconButton>
                {/if}
                {#if canRetry(job.status)}
                  <IconButton
                    label="Retry job"
                    size="small"
                    variant="ghost"
                    onclick={() => onRetry(job)}
                  >
                    <RotateCcw size={11} />
                  </IconButton>
                {/if}
                {#if canCancel(job.status)}
                  <IconButton
                    label="Cancel job"
                    size="small"
                    variant="ghost"
                    onclick={() => onCancel(job)}
                  >
                    <Ban size={11} />
                  </IconButton>
                {/if}
                {/if}
              </div>
            </div>
          </li>
        {/each}
      </ul>
    {/each}
  {/if}
</section>

<style>
  .activity {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-height: 0;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }
  .select {
    background: #17191f;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 3px 6px;
    font-size: 11px;
  }
  .select:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .count {
    color: var(--muted);
    font-size: 11px;
    padding: 0 4px;
  }
  .spacer {
    flex: 1 1 auto;
  }
  .composer {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: rgba(0, 212, 170, 0.03);
  }
  .batch-urls {
    width: 100%;
    box-sizing: border-box;
    resize: vertical;
    background: #17191f;
    border: 1px solid var(--border);
    color: var(--text);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 11px;
    padding: 6px 7px;
  }
  .batch-urls:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .composer-row {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .poll {
    color: var(--accent);
    font-size: 12px;
    animation: spin 1.2s linear infinite;
    display: inline-block;
  }
  @keyframes spin {
    from {
      transform: rotate(0);
    }
    to {
      transform: rotate(360deg);
    }
  }
  .group-head {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 4px 1px;
    border-bottom: 1px solid var(--border);
  }
  .group-label {
    color: var(--muted);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .group-count {
    color: var(--muted);
    font-size: 10px;
  }
  .list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 64px 72px 70px auto;
    align-items: center;
    gap: 6px;
    padding: 2px 4px;
    border-radius: 2px;
  }
  .row.clickable:hover {
    background: rgba(0, 212, 170, 0.06);
  }
  .row.active {
    background: rgba(0, 212, 170, 0.14);
  }
  .rowmain {
    display: grid;
    grid-template-columns: 64px minmax(0, 1fr);
    align-items: center;
    gap: 6px;
    min-width: 0;
    background: transparent;
    border: none;
    color: var(--text);
    font: inherit;
    padding: 2px 0;
    text-align: left;
  }
  .rowmain:not(.static) {
    cursor: pointer;
  }
  .kind {
    color: var(--text);
    font-size: 10px;
    background: rgba(0, 212, 170, 0.08);
    padding: 1px 6px;
    border-radius: 8px;
    text-align: center;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .target {
    color: var(--accent);
    font-size: 11px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .target.placeholder {
    color: var(--muted);
    font-style: italic;
  }
  .progress {
    color: var(--text);
    font-size: 10px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    text-align: right;
  }
  .progress.muted {
    color: var(--muted);
  }
  .progress.changed {
    color: #e0b860;
  }
  .time {
    color: var(--muted);
    font-size: 10px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    text-align: right;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 2px;
    justify-content: flex-end;
  }
</style>
