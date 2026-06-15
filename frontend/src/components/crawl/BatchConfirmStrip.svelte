<script lang="ts">
  import { X } from 'lucide-svelte';
  import {
    enqueueCrawl,
    listCollections,
    createCollection,
    ApiError,
    type Collection,
    type CrawlQueueMode,
    type EnqueueBody,
    type EnqueueResult,
  } from '$lib/api';
  import { batchConfirmStore } from '$lib/stores/batchConfirm.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';

  // Re-using the mode list from CrawlControls would force a shared module
  // for one constant; for now mirror the labels here so the strip stays
  // self-contained. CrawlControls remains the source of truth for the
  // default selection — that's snapshotted at stage time.
  const MODES: { id: CrawlQueueMode; label: string }[] = [
    { id: 'Cross-site', label: 'Cross-site' },
    { id: 'BFS', label: 'BFS' },
    { id: 'DFS', label: 'DFS' },
    { id: 'Diverse', label: 'Diverse' },
    { id: 'Focused', label: 'Focused' },
  ];

  // Local form state, hydrated whenever a new batch is staged.
  let mode = $state<CrawlQueueMode>('Cross-site');
  let stayOnDomain = $state(false);
  let maxDepth = $state(3);
  let depthUnlimited = $state(false);
  // 'none' | 'new' | numeric id — matches CrawlControls' shape.
  let collectionId = $state<'none' | 'new' | number>('none');
  let newCollectionName = $state('');

  let collections = $state<Collection[]>([]);
  let queuing = $state(false);

  // Tracks which staged batch object the form is hydrated from. Re-running
  // hydrate while the same batch is staged would wipe the analyst's edits.
  let hydratedFrom = $state<object | null>(null);

  $effect(() => {
    void refreshCollections();
  });

  $effect(() => {
    const staged = batchConfirmStore.staged;
    if (!staged) {
      hydratedFrom = null;
      return;
    }
    if (hydratedFrom === staged) return;
    const d = staged.defaults;
    mode = d.mode;
    stayOnDomain = d.stayOnDomain;
    if (d.maxDepth === null) {
      depthUnlimited = true;
      maxDepth = 3;
    } else {
      depthUnlimited = false;
      maxDepth = d.maxDepth;
    }
    if (d.collectionId !== null) {
      collectionId = d.collectionId;
      newCollectionName = '';
    } else if (d.collectionNamePending) {
      collectionId = 'new';
      newCollectionName = d.collectionNamePending;
    } else {
      collectionId = 'none';
      newCollectionName = '';
    }
    hydratedFrom = staged;
  });

  // Cross-site forces stayOnDomain off (parity with CrawlControls).
  $effect(() => {
    if (mode === 'Cross-site') stayOnDomain = false;
  });

  async function refreshCollections() {
    try {
      const r = await listCollections();
      collections = r.collections;
    } catch {
      collections = [];
    }
  }

  function summariseResults(results: EnqueueResult[]): string {
    let inserted = 0;
    let dupActive = 0;
    let dupBatch = 0;
    let bad = 0;
    for (const r of results) {
      if (r.inserted) inserted++;
      else if (r.reason === 'duplicate_active') dupActive++;
      else if (r.reason === 'duplicate_in_batch') dupBatch++;
      else if (r.reason === 'bad_url') bad++;
    }
    const parts: string[] = [`Queued ${inserted}`];
    if (dupActive) parts.push(`${dupActive} already in queue`);
    if (dupBatch) parts.push(`${dupBatch} duplicate in batch`);
    if (bad) parts.push(`${bad} invalid`);
    return parts.join(' · ');
  }

  async function onQueue() {
    const staged = batchConfirmStore.staged;
    if (!staged || queuing) return;
    queuing = true;
    try {
      let resolvedCollectionId: number | null = null;
      let collectionNamePending: string | null = null;
      if (typeof collectionId === 'number') {
        resolvedCollectionId = collectionId;
      } else if (collectionId === 'new') {
        const trimmed = newCollectionName.trim();
        if (!trimmed) {
          toastStore.show('Name the new collection or pick one.', 'warn');
          queuing = false;
          return;
        }
        // Resolve up-front when we have a name in hand. The backend can
        // also take `collection_name_pending` and resolve at claim time;
        // doing it here means the post-queue refresh picks up the new
        // collection immediately. If the name already exists (409), fall
        // back to pending-name so the runner does the case-insensitive
        // match.
        try {
          const created = await createCollection({ name: trimmed });
          resolvedCollectionId = created.id;
          await refreshCollections();
        } catch (e) {
          if (e instanceof ApiError && e.status === 409) {
            collectionNamePending = trimmed;
          } else {
            throw e;
          }
        }
      }

      const body: EnqueueBody = {
        urls: staged.urls,
        mode,
        source: staged.source,
        stay_on_domain: stayOnDomain,
        max_depth: depthUnlimited ? null : maxDepth,
        collection_id: resolvedCollectionId,
        collection_name_pending: collectionNamePending,
      };
      const r = await enqueueCrawl(body);
      toastStore.show(summariseResults(r.results), 'info');
      batchConfirmStore.clear();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Queue failed: ${msg}`, 'error');
    } finally {
      queuing = false;
    }
  }

  function onDiscard() {
    batchConfirmStore.discard();
  }

  const staged = $derived(batchConfirmStore.staged);
</script>

{#if staged}
  <div class="strip">
    <header>
      <span class="title">
        Batch from {staged.sourceLabel} — {staged.urls.length} URL{staged.urls.length === 1 ? '' : 's'}
      </span>
      <button
        type="button"
        class="discard"
        aria-label="Discard staged batch"
        title="Discard staged batch"
        onclick={onDiscard}
        disabled={queuing}
      >
        <X size={12} />
      </button>
    </header>

    <div class="row">
      <label class="field">
        <span>Mode</span>
        <select bind:value={mode} disabled={queuing}>
          {#each MODES as m (m.id)}
            <option value={m.id}>{m.label}</option>
          {/each}
        </select>
      </label>

      <label class="field">
        <span>Collection</span>
        <select bind:value={collectionId} disabled={queuing}>
          <option value="none">— none —</option>
          {#each collections as c (c.id)}
            <option value={c.id}>{c.name}</option>
          {/each}
          <option value="new">+ New collection…</option>
        </select>
      </label>

      <label class="field">
        <span>Max depth</span>
        <div class="depth-row">
          <input
            type="number"
            min="1"
            max="20"
            bind:value={maxDepth}
            disabled={depthUnlimited || queuing}
          />
          <label class="depth-toggle">
            <input
              type="checkbox"
              bind:checked={depthUnlimited}
              disabled={queuing}
            />
            <span>Unlimited</span>
          </label>
        </div>
      </label>

      <label
        class="field checkbox"
        title={mode === 'Cross-site'
          ? 'Cross-site mode follows links across domains — disable it to use Stay on domain.'
          : ''}
      >
        <input
          type="checkbox"
          bind:checked={stayOnDomain}
          disabled={mode === 'Cross-site' || queuing}
        />
        <span>Stay on domain</span>
      </label>
    </div>

    {#if collectionId === 'new'}
      <div class="new-collection">
        <input
          type="text"
          bind:value={newCollectionName}
          placeholder="Collection name"
          disabled={queuing}
        />
      </div>
    {/if}

    {#if depthUnlimited}
      <p class="note warn">
        ⚠ Unlimited depth — these crawls can run indefinitely.
      </p>
    {/if}

    <div class="actions">
      <button
        type="button"
        class="primary"
        onclick={onQueue}
        disabled={queuing}
      >
        {queuing ? 'Queuing…' : `Queue ${staged.urls.length}`}
      </button>
    </div>
  </div>
{/if}

<style>
  .strip {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 8px;
    border: 1px solid var(--accent);
    background: var(--accent-bg-subtle);
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .title {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--accent);
  }
  .discard {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 2px 4px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
  }
  .discard:hover:not(:disabled) {
    color: #ff5577;
    border-color: #ff5577;
  }
  .discard:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 3px;
    font-size: 10px;
    color: var(--muted);
  }
  .field.checkbox {
    flex-direction: row;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: var(--text);
  }
  .field.checkbox input {
    width: auto;
  }
  input,
  select {
    background: #17191f;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 5px 7px;
    font-size: 11px;
    width: 100%;
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
  .depth-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .depth-row input[type='number'] {
    flex: 0 0 64px;
  }
  .depth-row input[type='number']:disabled {
    opacity: 0.45;
  }
  .depth-toggle {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    color: var(--text);
    cursor: pointer;
  }
  .depth-toggle input {
    width: auto;
  }
  .new-collection input {
    width: 100%;
  }
  .note {
    margin: 0;
    padding: 6px 8px;
    border-left: 2px solid var(--accent);
    background: var(--accent-bg-subtle);
    font-size: 11px;
    color: var(--text);
  }
  .note.warn {
    border-left-color: #ffb347;
    background: rgba(255, 179, 71, 0.06);
    color: #ffd58a;
  }
  .actions {
    display: flex;
    justify-content: flex-end;
  }
  .primary {
    background: transparent;
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 6px 12px;
    cursor: pointer;
    font-size: 11px;
  }
  .primary:hover:not(:disabled) {
    background: var(--accent-bg);
  }
  .primary:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
</style>
