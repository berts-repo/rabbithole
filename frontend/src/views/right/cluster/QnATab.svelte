<script lang="ts">
  // Cluster workspace — Q&A tab.
  //
  // Ask one question across the whole cluster. The answer is a single
  // *synthesis* over the members' page content, stored in `cluster_analyses`
  // (decision D1) — not one row per page. It shows up in the bottom-pane
  // Activity tab like every other analysis.
  //
  // Compose stays inline here (no pane jump): the question box calls the
  // shared `createClusterAnalysis` dispatch, then polls the cluster's
  // fingerprint for results. Prior answers for the same membership load on
  // open, so the tab doubles as the cluster's analysis inspect surface.
  //
  // Spec: docs/specs/right-pane.md:368-375.

  import { onDestroy } from 'svelte';
  import {
    createClusterAnalysis,
    listClusterAnalyses,
    type ClusterAnalysisRow,
  } from '$lib/api';
  import { explainError } from '$lib/api/errors';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import {
    fetchMissingNodes,
    resolveFromPayload,
    type NodeBag,
    type NodeBagEntry,
  } from './nodeBag';
  import { clusterFingerprint } from './fingerprint';

  const POLL_MS = 5_000;
  const ANALYSIS_TYPE = 'Cluster Q&A';

  // ---------------- Resolve selection into a bag ----------------

  let bag = $state<NodeBag>(new Map());
  let resolvingMissing = $state(false);
  let resolveGen = 0;

  $effect(() => {
    const ids = Array.from(selectionStore.selectedIds);
    const gen = ++resolveGen;
    const { resolved, missing } = resolveFromPayload(ids, graphStore.payload);
    bag = resolved;
    if (missing.length === 0) return;
    resolvingMissing = true;
    void fetchMissingNodes(missing).then((extra) => {
      if (gen !== resolveGen) return;
      const merged: NodeBag = new Map(bag);
      for (const [id, entry] of extra) {
        if (!merged.has(id)) merged.set(id, entry);
      }
      bag = merged;
      resolvingMissing = false;
    });
  });

  let allRows = $derived.by(() => {
    const ids = Array.from(selectionStore.selectedIds);
    return ids
      .map(
        (id) =>
          bag.get(id) ??
          ({ id, url: `#${id}`, uncrawled: false, domain: null } satisfies NodeBagEntry),
      )
      .sort((a, b) => a.id - b.id);
  });
  // Only crawled members have page content to synthesise over.
  let crawledRows = $derived(allRows.filter((r) => !r.uncrawled));
  let uncrawledCount = $derived(allRows.length - crawledRows.length);

  // ---------------- Fingerprint → load prior answers ----------------

  // The membership's stable key. Recomputed whenever the crawled set changes;
  // each value pins one cluster's analyses (decision D1).
  let fingerprint = $state<string | null>(null);
  let analyses = $state<ClusterAnalysisRow[]>([]);
  // Guards both the fingerprint resolve and the fetches it spawns, so a stale
  // selection's response can never overwrite the current one.
  let loadGen = 0;

  $effect(() => {
    const ids = crawledRows.map((r) => r.id);
    const gen = ++loadGen;
    if (ids.length === 0) {
      fingerprint = null;
      analyses = [];
      stopPolling();
      return;
    }
    void clusterFingerprint(ids).then((fp) => {
      if (gen !== loadGen) return;
      fingerprint = fp;
      void refresh(gen);
    });
  });

  // ---------------- Question + Ask ----------------

  let question = $state('');
  let asking = $state(false);

  let canAsk = $derived(
    !asking && question.trim().length > 0 && crawledRows.length > 0,
  );

  async function ask(): Promise<void> {
    if (!canAsk) return;
    const q = question.trim();
    const ids = crawledRows.map((r) => r.id);
    asking = true;
    try {
      const res = await createClusterAnalysis({
        resource_ids: ids,
        analysis_type: ANALYSIS_TYPE,
        question: q,
      });
      fingerprint = res.fingerprint;
      question = '';
      const gen = ++loadGen;
      await refresh(gen);
      maybeStartPolling();
      toastStore.show('Queued cluster Q&A.');
    } catch (err) {
      toastStore.show(explainError(err, 'Ask failed'), 'error');
    } finally {
      asking = false;
    }
  }

  // ---------------- Polling for results ----------------

  let timer: ReturnType<typeof setInterval> | null = null;

  onDestroy(() => stopPolling());

  async function refresh(gen: number): Promise<void> {
    if (fingerprint === null) return;
    try {
      const res = await listClusterAnalyses(fingerprint);
      if (gen !== loadGen) return;
      analyses = res.analyses;
      if (!hasPending(res.analyses)) stopPolling();
    } catch {
      // Network blip — keep any running timer; the next tick may succeed.
    }
  }

  function hasPending(rows: ClusterAnalysisRow[]): boolean {
    return rows.some(
      (r) => r.status === 'pending' || r.status === 'running' || r.status === null,
    );
  }

  function maybeStartPolling(): void {
    stopPolling();
    timer = setInterval(() => void refresh(loadGen), POLL_MS);
  }

  function stopPolling(): void {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  }
</script>

<div class="root">
  {#if uncrawledCount > 0}
    <p class="notice">
      {uncrawledCount} uncrawled excluded — Q&A synthesises crawled content.
    </p>
  {/if}

  <label class="question-label">
    <span class="block-label">Question</span>
    <textarea
      class="question-input"
      placeholder="Ask a question across all crawled pages in this cluster…"
      bind:value={question}
      onkeydown={(e) => {
        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
          e.preventDefault();
          void ask();
        }
      }}
    ></textarea>
  </label>

  <button
    type="button"
    class="ask-button"
    onclick={ask}
    disabled={!canAsk}
    title={crawledRows.length === 0 ? 'No crawled nodes in selection.' : ''}
  >
    {asking ? 'Queueing…' : `Ask (${crawledRows.length} pages)`}
  </button>

  {#if crawledRows.length === 0}
    <p class="empty">No crawled nodes in selection.</p>
  {/if}

  <section class="block results">
    <span class="block-label">Cluster answers</span>
    {#if analyses.length === 0}
      <p class="empty">No cluster analyses yet. Ask a question to start one.</p>
    {:else}
      {#each analyses as row (row.id)}
        <article class="result">
          {#if row.question}
            <p class="result-q">{row.question}</p>
          {/if}
          {#if row.status === 'done'}
            {#if row.result && row.result.length > 0}
              <pre class="result-body">{row.result}</pre>
            {:else}
              <p class="result-status">No result.</p>
            {/if}
          {:else if row.status === 'running'}
            <p class="result-status">Running…</p>
          {:else if row.status === 'pending' || row.status === null}
            <p class="result-status">In queue…</p>
          {:else if row.status === 'paused'}
            <p class="result-status">Paused.</p>
          {:else if row.status === 'failed'}
            <p class="result-status">Failed.</p>
          {:else if row.status === 'cancelled'}
            <p class="result-status">Cancelled.</p>
          {/if}
        </article>
      {/each}
    {/if}
  </section>

  {#if resolvingMissing}
    <p class="hint">Resolving {selectionStore.selectedIds.size - bag.size} nodes…</p>
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
  .empty {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
    font-style: italic;
  }
  .hint {
    margin: 0;
    color: var(--muted);
    font-size: 10px;
    font-style: italic;
  }

  .question-label {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .block-label {
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .question-input {
    min-height: 60px;
    padding: 6px 8px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 2px;
    color: var(--text);
    font: inherit;
    resize: vertical;
  }
  .question-input:focus {
    border-color: var(--accent);
    outline: none;
  }
  .ask-button {
    padding: 6px 10px;
    background: rgba(0, 212, 170, 0.12);
    border: 1px solid var(--accent);
    border-radius: 2px;
    color: var(--accent);
    font-size: 11px;
    cursor: pointer;
  }
  .ask-button:hover:not(:disabled) {
    background: rgba(0, 212, 170, 0.2);
  }
  .ask-button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .block {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding-top: 6px;
    border-top: 1px solid var(--border);
  }
  .results {
    gap: 8px;
  }
  .result {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 6px 8px;
    background: rgba(0, 0, 0, 0.2);
    border: 1px solid var(--border);
    border-radius: 2px;
  }
  .result-q {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
    font-style: italic;
  }
  .result-status {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
    font-style: italic;
  }
  .result-body {
    margin: 0;
    padding: 6px 8px;
    background: rgba(0, 60, 40, 0.25);
    border: 1px solid rgba(0, 212, 170, 0.2);
    border-radius: 2px;
    color: var(--text);
    font-family: ui-monospace, monospace;
    font-size: 11px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 200px;
    overflow-y: auto;
  }
</style>
