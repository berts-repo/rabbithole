<script lang="ts">
  // Intel · Collection Analysis section. Runs analysis across a named
  // collection in two modes (spec §4):
  //   · per-URL  — one job per crawled member (stubs excluded), via the batch
  //     endpoint, exactly like the compose form's nodes path.
  //   · synthesis — one collection-scoped job over the whole set, via the
  //     collection-analyses endpoint (the multi_page analyzer types).

  import {
    createAnalysesBatch,
    createCollectionAnalysis,
    getCollection,
    listCollections,
    type AnalysisType,
    type CollectionDetail,
    type CollectionListRow,
  } from '$lib/api';
  import { explainError } from '$lib/api/errors';
  import { isCrawled } from '$lib/nodeState';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { EmptyState, TextButton } from '$lib/ui';

  // Per-URL types queue one job per crawled member; synthesis types are the
  // multi_page analyzers (backend PROMPTS multi_page=True) and queue one job.
  const PER_URL: AnalysisType[] = [
    'Summary',
    'Risk Score',
    'Entities (LLM)',
    'Category',
    'Domain Label',
  ];
  const SYNTHESIS = [
    'Cluster Summary',
    'Site Relationships',
    'Investigation Digest',
    'Seed Suggestions',
  ];

  let collections = $state<CollectionListRow[]>([]);
  let selectedId = $state<number | null>(null);
  let detail = $state<CollectionDetail | null>(null);
  let analysisType = $state<string>('Summary');
  let busy = $state(false);

  const isSynthesis = $derived(SYNTHESIS.includes(analysisType));
  const crawled = $derived(detail?.items.filter(isCrawled) ?? []);
  const stubs = $derived((detail?.items.length ?? 0) - crawled.length);
  const canQueue = $derived(
    !busy &&
      selectedId !== null &&
      (isSynthesis || crawled.length > 0),
  );

  $effect(() => {
    void (async () => {
      try {
        const r = await listCollections();
        collections = r.collections;
        if (selectedId === null && collections.length > 0) {
          selectedId = collections[0].id;
        }
      } catch {
        // Empty state covers the no-collections case; a load error reads the same.
      }
    })();
  });

  // Load member detail whenever the selected collection changes — needed for
  // the per-URL stub-exclusion count and the batch node ids.
  $effect(() => {
    const id = selectedId;
    if (id === null) {
      detail = null;
      return;
    }
    void (async () => {
      try {
        detail = await getCollection(id);
      } catch {
        detail = null;
      }
    })();
  });

  async function submit(): Promise<void> {
    if (!canQueue || selectedId === null) return;
    busy = true;
    try {
      if (isSynthesis) {
        await createCollectionAnalysis(selectedId, { analysis_type: analysisType });
        toastStore.show(`Queued ${analysisType} synthesis for collection`);
      } else {
        const res = await createAnalysesBatch({
          node_ids: crawled.map((i) => i.id),
          analysis_type: analysisType as AnalysisType,
          skip_existing: true,
        });
        const parts = [`Queued ${analysisType} — ${res.queued} page(s)`];
        if (res.skipped > 0) parts.push(`${res.skipped} skipped`);
        toastStore.show(parts.join(' · '));
      }
    } catch (e) {
      toastStore.show(explainError(e, 'Collection analysis failed'), 'error');
    } finally {
      busy = false;
    }
  }
</script>

{#if collections.length === 0}
  <EmptyState
    title="No collections"
    body="Pin sites into a collection to run analysis across the set."
  />
{:else}
  <form
    class="ca"
    onsubmit={(e) => {
      e.preventDefault();
      void submit();
    }}
  >
    <label class="row">
      <span>Collection</span>
      <select bind:value={selectedId}>
        {#each collections as c (c.id)}
          <option value={c.id}>{c.name} ({c.item_count})</option>
        {/each}
      </select>
    </label>

    <label class="row">
      <span>Type</span>
      <select bind:value={analysisType}>
        <optgroup label="Per-URL (one job per page)">
          {#each PER_URL as t (t)}
            <option value={t}>{t}</option>
          {/each}
        </optgroup>
        <optgroup label="Synthesis (one job over the set)">
          {#each SYNTHESIS as t (t)}
            <option value={t}>{t}</option>
          {/each}
        </optgroup>
      </select>
    </label>

    {#if !isSynthesis && detail}
      <p class="note">
        {crawled.length} of {detail.items.length} items will be analysed{#if stubs > 0}
          ({stubs} {stubs === 1 ? 'stub' : 'stubs'} excluded){/if}.
      </p>
    {/if}

    <TextButton type="submit" variant="primary" disabled={!canQueue}>
      {isSynthesis ? 'Queue synthesis' : `Queue (${crawled.length})`}
    </TextButton>
  </form>
{/if}

<style>
  .ca {
    display: flex;
    flex-direction: column;
    gap: 8px;
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
  select {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text);
    font: inherit;
    font-size: 12px;
    padding: 4px 6px;
  }
  .note {
    margin: 0;
    font-size: 10px;
    color: var(--muted);
  }
</style>
