<script lang="ts">
  // Intel · Analyse section — the node compose form. Queues one analyzer
  // against the staged node set (or the live graph selection) through the
  // batch endpoint. It's the single funnel for *node* analyses: the graph
  // menu, right-pane action bar, and right-pane Analysis tab all stage a node
  // target here rather than calling the batch endpoint themselves. Collection
  // and cluster analyses compose in their own sections (Collection Analysis,
  // cluster Q&A) since each writes to a different table.
  //
  // The prompt-template picker is deferred until the worker consumes a
  // template body — until then selecting one would not affect output.

  import {
    createAnalysesBatch,
    type AnalysisType,
  } from '$lib/api';
  import { explainError } from '$lib/api/errors';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import {
    intelComposeStore,
    targetCount,
    type ComposeTarget,
  } from '$lib/stores/intelCompose.svelte';
  import { EmptyState, TextButton } from '$lib/ui';

  const TYPES: { value: AnalysisType; label: string }[] = [
    { value: 'Summary', label: 'Summary' },
    { value: 'Risk Score', label: 'Risk Score' },
    { value: 'Entities (LLM)', label: 'Entities' },
    { value: 'Category', label: 'Category' },
    { value: 'Domain Label', label: 'Domain Label' },
    { value: 'Q&A', label: 'Q&A' },
  ];

  let analysisType = $state<AnalysisType>('Summary');
  let question = $state('');
  let model = $state('');
  let skipExisting = $state(true);
  let busy = $state(false);

  // A target staged by another surface wins until the analyst clears it; with
  // nothing staged the form tracks the live graph selection.
  let staged = $state<ComposeTarget | null>(null);

  $effect(() => {
    if (intelComposeStore.staged) {
      staged = intelComposeStore.consume();
    }
  });

  const selectionTarget = $derived.by((): ComposeTarget => {
    const ids = [...selectionStore.selectedIds];
    return { kind: 'nodes', nodeIds: ids };
  });

  const target = $derived(staged ?? selectionTarget);
  const count = $derived(targetCount(target));

  const targetLabel = $derived(staged?.label ?? 'Current selection');

  const isQA = $derived(analysisType === 'Q&A');
  const hasTarget = $derived(count > 0);
  const invalid = $derived(
    !hasTarget || busy || (isQA && question.trim().length === 0),
  );

  function clearStaged(): void {
    staged = null;
  }

  async function dispatch(t: ComposeTarget): Promise<string> {
    const m = model.trim() || null;
    const q = isQA ? question.trim() : null;
    const res = await createAnalysesBatch({
      node_ids: t.nodeIds,
      analysis_type: analysisType,
      question: q,
      model: m,
      skip_existing: skipExisting,
    });
    const parts = [`Queued ${analysisType} — ${res.queued} node(s)`];
    if (res.skipped > 0) parts.push(`${res.skipped} skipped`);
    if (res.unknown > 0) parts.push(`${res.unknown} unknown`);
    return parts.join(' · ');
  }

  async function submit(): Promise<void> {
    if (invalid) return;
    busy = true;
    try {
      const msg = await dispatch(target);
      toastStore.show(msg);
      clearStaged();
    } catch (e) {
      toastStore.show(explainError(e, 'Queue analysis failed'), 'error');
    } finally {
      busy = false;
    }
  }
</script>

<form
  class="compose"
  onsubmit={(e) => {
    e.preventDefault();
    void submit();
  }}
>
  <div class="target">
    <span class="tlabel">{targetLabel}</span>
    <span class="tcount">{count} {count === 1 ? 'target' : 'targets'}</span>
    {#if staged}
      <button type="button" class="link" onclick={clearStaged}>
        use selection
      </button>
    {/if}
  </div>

  {#if !hasTarget}
    <EmptyState
      title="No target"
      body="Select nodes in the graph, or use “Queue Analysis” from a menu, to compose an analysis."
    />
  {:else}
    <label class="row">
      <span>Type</span>
      <select bind:value={analysisType}>
        {#each TYPES as t (t.value)}
          <option value={t.value}>{t.label}</option>
        {/each}
      </select>
    </label>

    {#if isQA}
      <label class="row">
        <span>Question</span>
        <textarea
          bind:value={question}
          rows="2"
          placeholder="Ask a question about each target page…"
        ></textarea>
      </label>
    {/if}

    <label class="row">
      <span>Model</span>
      <input
        type="text"
        bind:value={model}
        placeholder="default (llm.model setting)"
      />
    </label>

    <label class="check">
      <input type="checkbox" bind:checked={skipExisting} />
      Skip targets already queued for this type
    </label>

    <TextButton type="submit" variant="primary" disabled={invalid}>
      Queue ({count})
    </TextButton>
  {/if}
</form>

<style>
  .compose {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .target {
    display: flex;
    align-items: baseline;
    gap: 8px;
    flex-wrap: wrap;
  }
  .tlabel {
    font-size: 11px;
    color: var(--text);
  }
  .tcount {
    font-size: 10px;
    color: var(--muted);
  }
  .link {
    background: none;
    border: none;
    padding: 0;
    color: var(--accent);
    font-size: 10px;
    cursor: pointer;
  }
  .link:hover {
    text-decoration: underline;
  }
  .row {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .row span {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
  }
  select,
  input[type='text'],
  textarea {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text);
    font: inherit;
    font-size: 12px;
    padding: 4px 6px;
  }
  textarea {
    resize: vertical;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: var(--muted);
  }
</style>
