<script lang="ts">
  // Intel · Auto-analysis Rules section (item 7, D2/D4 — simple v1). The single
  // home for auto-analysis:
  //   · Crawl  — toggle "auto-analyze every newly crawled page with X". These
  //     are the seeded crawl rules; toggling flips the rule's enabled flag (the
  //     crawl trigger reads them, replacing the legacy llm.auto_enqueue.*).
  //   · Collection — per-collection rules: queue analyzer X whenever a page is
  //     added to a given collection.
  // Richer label/score predicates wait on the label system (item 11); the
  // typed target_filter column already holds the JSON for that future.

  import {
    createAutoRule,
    deleteAutoRule,
    listAutoRules,
    listCollections,
    updateAutoRule,
    type AutoRule,
    type CollectionListRow,
  } from '$lib/api';
  import { explainError } from '$lib/api/errors';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { IconButton, TextButton } from '$lib/ui';
  import { Trash2 } from 'lucide-svelte';

  // The non-Q&A single-page analyzers — the types that make sense to fire
  // automatically (Q&A needs a question, so it is excluded).
  const AUTO_TYPES = [
    'Summary',
    'Risk Score',
    'Entities (LLM)',
    'Category',
    'Domain Label',
  ];

  let crawlRules = $state<AutoRule[]>([]);
  let collectionRules = $state<AutoRule[]>([]);
  let collections = $state<CollectionListRow[]>([]);
  let newCollectionId = $state<number | null>(null);
  let newType = $state<string>('Summary');
  let busy = $state(false);

  const collectionName = $derived.by(() => {
    const map = new Map(collections.map((c) => [c.id, c.name]));
    return (id: unknown): string =>
      typeof id === 'number' ? (map.get(id) ?? `#${id}`) : 'unknown';
  });

  async function load(): Promise<void> {
    try {
      const [rules, cols] = await Promise.all([
        listAutoRules(),
        listCollections(),
      ]);
      crawlRules = rules.rules.filter((r) => r.trigger_kind === 'crawl');
      collectionRules = rules.rules.filter(
        (r) => r.trigger_kind === 'collection_add',
      );
      collections = cols.collections;
      if (newCollectionId === null && collections.length > 0) {
        newCollectionId = collections[0].id;
      }
    } catch {
      // A load failure leaves the section empty; the analyst can retry by
      // reopening the tab.
    }
  }

  $effect(() => {
    void load();
  });

  async function toggleCrawl(rule: AutoRule): Promise<void> {
    if (busy) return;
    busy = true;
    try {
      await updateAutoRule(rule.id, { enabled: !rule.enabled });
      await load();
    } catch (e) {
      toastStore.show(explainError(e, 'Toggle failed'), 'error');
    } finally {
      busy = false;
    }
  }

  async function addCollectionRule(): Promise<void> {
    if (busy || newCollectionId === null) return;
    busy = true;
    try {
      await createAutoRule({
        trigger_kind: 'collection_add',
        analysis_type: newType,
        target_filter: { collection_id: newCollectionId },
      });
      await load();
      toastStore.show('Rule added');
    } catch (e) {
      toastStore.show(explainError(e, 'Add rule failed'), 'error');
    } finally {
      busy = false;
    }
  }

  async function removeRule(id: number): Promise<void> {
    if (busy) return;
    busy = true;
    try {
      await deleteAutoRule(id);
      await load();
    } catch (e) {
      toastStore.show(explainError(e, 'Remove failed'), 'error');
    } finally {
      busy = false;
    }
  }
</script>

<div class="rules">
  <div class="group">
    <p class="ghead">On crawl</p>
    {#each crawlRules as rule (rule.id)}
      <label class="toggle">
        <input
          type="checkbox"
          checked={!!rule.enabled}
          disabled={busy}
          onchange={() => void toggleCrawl(rule)}
        />
        {rule.analysis_type}
      </label>
    {/each}
  </div>

  <div class="group">
    <p class="ghead">On collection add</p>
    {#each collectionRules as rule (rule.id)}
      <div class="rule-row">
        <span class="rtext">
          {collectionName(rule.target_filter?.collection_id)} → {rule.analysis_type}
        </span>
        <IconButton
          label="Remove rule"
          size="small"
          disabled={busy}
          onclick={() => void removeRule(rule.id)}
        >
          <Trash2 size={13} />
        </IconButton>
      </div>
    {/each}

    {#if collections.length > 0}
      <div class="add">
        <select bind:value={newCollectionId} disabled={busy}>
          {#each collections as c (c.id)}
            <option value={c.id}>{c.name}</option>
          {/each}
        </select>
        <select bind:value={newType} disabled={busy}>
          {#each AUTO_TYPES as t (t)}
            <option value={t}>{t}</option>
          {/each}
        </select>
        <TextButton
          size="small"
          disabled={busy || newCollectionId === null}
          onclick={() => void addCollectionRule()}
        >
          Add
        </TextButton>
      </div>
    {:else}
      <p class="empty">No collections yet.</p>
    {/if}
  </div>
</div>

<style>
  .rules {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .group {
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .ghead {
    margin: 0;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
  }
  .toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--text);
  }
  .rule-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
  }
  .rtext {
    font-size: 12px;
    color: var(--text);
  }
  .add {
    display: flex;
    gap: 4px;
    align-items: center;
    margin-top: 2px;
  }
  select {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text);
    font: inherit;
    font-size: 11px;
    padding: 3px 4px;
    min-width: 0;
  }
  .empty {
    margin: 0;
    font-size: 11px;
    color: var(--muted);
  }
</style>
