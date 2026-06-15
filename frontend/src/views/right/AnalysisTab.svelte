<script lang="ts">
  // Right pane — Analysis tab (F6 phase 3).
  //
  // Lists analysis records for the selected node and shows the result of
  // whichever row is currently selected. Polls every 5 s while any row is
  // pending or running; stops when the work settles. Queue Analysis
  // opens the existing modal so the form / model / Q&A wiring stays in
  // one place. Stub nodes get the same Queue button plus a notice that
  // jobs fire automatically after the URL is crawled.
  //
  // Spec: docs/specs/right-pane.md:191-223.

  import { RefreshCw, X } from 'lucide-svelte';
  import { onDestroy } from 'svelte';
  import {
    ApiError,
    deleteAnalysis,
    getNode,
    listAnalyses,
    rerunAnalysis,
    type AnalysisRow,
    type GraphNode,
    type NodeRow,
  } from '$lib/api';
  import { queueAnalysis, selectionFromNodes } from '$lib/contextMenu/actions';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { isUncrawled } from '$lib/nodeState';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import {
    resultPlaceholder,
    shouldPoll,
  } from './analysisStatus';
  import {
    CollapsibleSection,
    EmptyState,
    IconButton,
    StatusBadge,
    TextButton,
  } from '$lib/ui';
  import { createCollapseStore } from '$lib/stores/sectionCollapse.svelte';
  import { explainError } from '$lib/api/errors';

  const POLL_MS = 5_000;

  const sections = createCollapseStore('rabbithole.right.analysis');

  // ---------------- Per-selection load ----------------

  let node = $state<NodeRow | null>(null);
  let rows = $state<AnalysisRow[]>([]);
  let selectedId = $state<number | null>(null);
  let loading = $state(false);
  let loadError = $state<string | null>(null);
  let fetchGen = 0;

  // Polling lifecycle. We always restart the timer after a fetch lands
  // so a row flipping from pending → done settles the loop within one
  // tick. ``timer === null`` means "no poll scheduled" — both "haven't
  // started yet" and "settled, stopped on purpose".
  let timer: ReturnType<typeof setInterval> | null = null;

  $effect(() => {
    const id = selectionStore.selectedNodeId;
    void load(id);
  });

  onDestroy(() => {
    stopPolling();
  });

  async function load(id: number | null): Promise<void> {
    stopPolling();
    const gen = ++fetchGen;
    if (id === null) {
      node = null;
      rows = [];
      selectedId = null;
      loading = false;
      loadError = null;
      return;
    }
    loading = true;
    loadError = null;
    try {
      const [n, res] = await Promise.all([
        getNode(id),
        listAnalyses({ nodeId: id, limit: 200 }),
      ]);
      if (gen !== fetchGen) return;
      node = n;
      rows = res.analyses;
      // Keep the previously selected row if it's still present; otherwise
      // auto-pick the first done row so the result pane has something
      // useful to show.
      const stillThere = selectedId !== null && rows.some((r) => r.id === selectedId);
      if (!stillThere) {
        selectedId = rows.find((r) => r.status === 'done')?.id ?? null;
      }
      maybeStartPolling();
    } catch (err) {
      if (gen !== fetchGen) return;
      node = null;
      rows = [];
      selectedId = null;
      loadError =
        err instanceof ApiError && err.status === 404
          ? 'Node not found'
          : err instanceof Error
            ? err.message
            : 'Load failed';
    } finally {
      if (gen === fetchGen) loading = false;
    }
  }

  async function refresh(): Promise<void> {
    const id = selectionStore.selectedNodeId;
    if (id === null) return;
    const gen = ++fetchGen;
    try {
      const res = await listAnalyses({ nodeId: id, limit: 200 });
      if (gen !== fetchGen) return;
      rows = res.analyses;
      // If the currently selected row vanished (e.g. deleted by another
      // surface), drop the selection.
      if (selectedId !== null && !rows.some((r) => r.id === selectedId)) {
        selectedId = null;
      }
      maybeStartPolling();
    } catch (err) {
      // A poll failure is transient — toast once but don't tear the list
      // down. The next tick may succeed.
      if (gen !== fetchGen) return;
      const msg = err instanceof Error ? err.message : String(err);
      toastStore.show(`Analyses refresh failed: ${msg}`, 'warn');
    }
  }

  function maybeStartPolling(): void {
    stopPolling();
    if (!shouldPoll(rows)) return;
    timer = setInterval(() => void refresh(), POLL_MS);
  }

  function stopPolling(): void {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  }

  // ---------------- Row actions ----------------

  async function onRerun(row: AnalysisRow): Promise<void> {
    try {
      await rerunAnalysis(row.id);
      // Optimistic flip — the poll will reconcile.
      rows = rows.map((r) =>
        r.id === row.id ? { ...r, status: 'pending', result: null } : r,
      );
      toastStore.show('Re-queued.');
      maybeStartPolling();
    } catch (err) {
      toastStore.show(explainError(err, 'Re-run failed'), 'error');
    }
  }

  async function onDelete(row: AnalysisRow): Promise<void> {
    try {
      await deleteAnalysis(row.id);
      rows = rows.filter((r) => r.id !== row.id);
      if (selectedId === row.id) selectedId = null;
      toastStore.show('Analysis removed.');
    } catch (err) {
      toastStore.show(explainError(err, 'Delete failed'), 'error');
    }
  }

  // ---------------- Queue Analysis (funnel to Intel) ----------------

  // The compose UI lives in one place (Intel · Analyse); this tab is
  // inspect-only. "Queue Analysis" stages the selection there via the shared
  // funnel. Prefer the live GraphNode from the payload so metric fields
  // (flag_status, reviewed, etc.) are accurate; fall back to a minimal
  // construction so a node filtered out of the current graph view can still
  // be queued.
  function queueTarget(): GraphNode[] {
    if (!node) return [];
    const live = graphStore.payload?.nodes.find((gn) => gn.id === node!.id);
    if (live) return [live];
    return [
      {
        id: node.id,
        label: node.title ?? node.url,
        alias: null,
        title_text: node.title ?? '',
        raw_url: node.url,
        color: '#000',
        domain: node.domain,
        network: node.network,
        depth: null,
        flag_status: node.flag?.status ?? null,
        is_bridge: false,
        betweenness: 0,
        pagerank: 0,
        cluster_id: null,
        infra_cluster_id: null,
        first_seen: node.first_seen,
        is_cluster: false,
        state: node.state,
        analysis_excluded: node.analysis_excluded,
        reviewed: node.reviewed,
        category: node.category,
        in_degree_count: 0,
        out_degree_count: 0,
        label_ids: node.label_ids,
        domain_label_ids: node.domain_label_ids,
      },
    ];
  }

  function openQueue(): void {
    if (!node) return;
    queueAnalysis(selectionFromNodes(queueTarget()));
  }

  let selectedRow = $derived.by(() => {
    if (selectedId === null) return null;
    return rows.find((r) => r.id === selectedId) ?? null;
  });

  let resultView = $derived(resultPlaceholder(selectedRow));
</script>

<div class="root">
  {#if selectionStore.selectedNodeId === null}
    <EmptyState title="No node selected." />
  {:else if loading && !node}
    <EmptyState title="Loading…" />
  {:else if loadError}
    <EmptyState title={loadError} error />
  {:else if node}
    {@const isStub = isUncrawled(node)}

    <header class="head">
      <button type="button" class="queue" onclick={openQueue}>
        + Queue Analysis
      </button>
      <IconButton label="Refresh analyses" onclick={() => void refresh()}>
        <RefreshCw size={11} />
      </IconButton>
    </header>

    {#if isStub}
      <p class="notice">Jobs will run when this URL is crawled.</p>
    {/if}

    <CollapsibleSection
      title="Analyses ({rows.length})"
      collapsed={sections.isCollapsed('list')}
      onToggle={() => sections.toggle('list')}
    >
      {#if rows.length === 0}
        <EmptyState title="No analyses yet." body="Use Queue Analysis to start one." />
      {:else}
        <ul class="rows">
          {#each rows as r (r.id)}
            {@const active = r.id === selectedId}
            <li>
              <button
                type="button"
                class="row"
                class:active
                onclick={() => (selectedId = r.id)}
              >
                <span class="type">{r.analysis_type}</span>
                {#if r.status}
                  <StatusBadge status={r.status} />
                {/if}
                {#if r.model}
                  <span class="model">{r.model}</span>
                {/if}
              </button>
              <div class="row-actions">
                {#if r.status === 'done'}
                  <TextButton size="small" onclick={() => void onRerun(r)}>
                    Re-run
                  </TextButton>
                {/if}
                <IconButton label="Delete analysis" size="small" onclick={() => void onDelete(r)}>
                  <X size={11} />
                </IconButton>
              </div>
            </li>
          {/each}
        </ul>
      {/if}
    </CollapsibleSection>

    {#if selectedRow && resultView}
      <CollapsibleSection
        title="Result"
        collapsed={sections.isCollapsed('result')}
        onToggle={() => sections.toggle('result')}
      >
        <div class="result-inner">
          <div class="result-meta">
            <span>{selectedRow.analysis_type}</span>
            {#if selectedRow.model}<span>· {selectedRow.model}</span>{/if}
            <span class="meta-status" class:done={selectedRow.status === 'done'}>
              · {selectedRow.status}
            </span>
          </div>
          {#if selectedRow.question}
            <p class="question">{selectedRow.question}</p>
          {/if}
          <div class="result-body" class:placeholder={resultView.kind === 'message'}>
            {#if resultView.kind === 'show'}
              <pre>{resultView.body}</pre>
            {:else}
              <p>{resultView.text}</p>
            {/if}
          </div>
        </div>
      </CollapsibleSection>
    {/if}
  {/if}

</div>

<style>
  .root {
    display: flex;
    flex-direction: column;
    gap: 10px;
    font-size: 11px;
    color: var(--text);
  }
  .notice {
    margin: 0;
    padding: 6px 8px;
    border: 1px solid #b08a3a;
    border-radius: 2px;
    background: rgba(176, 138, 58, 0.1);
    color: #e0b860;
    font-size: 11px;
  }

  .head {
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .queue {
    flex: 1;
    padding: 6px 8px;
    background: rgba(0, 212, 170, 0.12);
    border: 1px solid var(--accent);
    border-radius: 2px;
    color: var(--accent);
    font-size: 11px;
    cursor: pointer;
  }
  .queue:hover {
    background: rgba(0, 212, 170, 0.2);
  }
  /* List */
  .rows {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .rows li {
    display: flex;
    align-items: stretch;
    gap: 4px;
  }
  .row {
    flex: 1;
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: center;
    column-gap: 8px;
    row-gap: 2px;
    padding: 4px 6px;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    color: var(--text);
    text-align: left;
    cursor: pointer;
  }
  .row:hover {
    background: rgba(0, 212, 170, 0.06);
  }
  .row.active {
    background: rgba(0, 212, 170, 0.14);
    border-color: var(--accent);
  }
  .type {
    color: var(--text);
    font-size: 11px;
  }
  .model {
    grid-column: 1 / -1;
    color: var(--muted);
    font-size: 10px;
  }

  .row-actions {
    display: flex;
    align-items: center;
    gap: 2px;
  }
  /* Result pane */
  .result-inner {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .result-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    color: var(--muted);
    font-size: 10px;
  }
  .meta-status.done {
    color: var(--accent);
  }
  .question {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
    font-style: italic;
  }
  .result-body {
    margin: 0;
    padding: 8px 10px;
    background: rgba(0, 60, 40, 0.25);
    border: 1px solid rgba(0, 212, 170, 0.2);
    border-radius: 2px;
    color: var(--text);
    max-height: 220px;
    overflow-y: auto;
  }
  .result-body.placeholder {
    background: transparent;
    border-style: dashed;
    color: var(--muted);
    font-style: italic;
  }
  .result-body pre {
    margin: 0;
    font-family: ui-monospace, monospace;
    font-size: 11px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .result-body p {
    margin: 0;
    font-size: 11px;
  }
</style>
