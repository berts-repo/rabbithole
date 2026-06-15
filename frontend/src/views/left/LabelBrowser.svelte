<script lang="ts">
  // Left-pane label browser (item 11, Phase 3b). Lives under the Find composer:
  // the analyst browses the label taxonomy and, with one click, highlights
  // every node in the CURRENT graph workspace carrying that label. This is
  // HIGHLIGHT-ONLY (per the app selection model — exploration, like the
  // bottom-pane Domains/Labels rows), never a full select. A second click on an
  // active label clears the highlight.
  //
  // Counts and membership are read straight off the rendered graph payload (the
  // union of direct + via-domain label ids), so a label only shows what's
  // actually on the canvas right now — switching workspace tabs re-counts.

  import { onMount } from 'svelte';
  import { labelsStore } from '$lib/stores/labels.svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { labelMemberNodeIds, sameIdSet } from './labelBrowser';

  onMount(() => {
    void labelsStore.ensureLoaded();
  });

  // label id → node ids carrying it in the current graph. One pass per payload
  // change backs every row's count + highlight set.
  const membersByLabel = $derived(
    labelMemberNodeIds(graphStore.payload?.nodes ?? []),
  );

  // Picker order: rank-sorted, presets the analyst hid dropped — the analyst's
  // working set, same as the apply picker.
  const rows = $derived(
    labelsStore.visible.map((label) => ({
      label,
      ids: membersByLabel.get(label.id) ?? new Set<number>(),
    })),
  );

  function isActive(ids: Set<number>): boolean {
    return (
      ids.size > 0 &&
      selectionStore.selectMode === 'highlight' &&
      sameIdSet(selectionStore.selectedIds, ids)
    );
  }

  function onClick(ids: Set<number>): void {
    if (ids.size === 0) return;
    if (isActive(ids)) selectionStore.clear();
    else selectionStore.replaceMulti(ids);
  }
</script>

<section class="browser">
  <header class="head">
    <span class="title">Labels in graph</span>
  </header>

  {#if !labelsStore.loaded}
    <p class="empty">Loading…</p>
  {:else if rows.length === 0}
    <p class="empty">No labels yet.</p>
  {:else}
    <ul class="list">
      {#each rows as { label, ids } (label.id)}
        {@const active = isActive(ids)}
        <li>
          <button
            type="button"
            class="row"
            class:active
            class:empty-row={ids.size === 0}
            disabled={ids.size === 0}
            aria-pressed={active}
            title={ids.size === 0
              ? `${label.name} — no nodes in this graph`
              : active
                ? `Clear highlight`
                : `Highlight ${ids.size} node${ids.size === 1 ? '' : 's'} labeled ${label.name}`}
            onclick={() => onClick(ids)}
          >
            <span
              class="dot"
              style:background={label.color ?? 'var(--accent)'}
              aria-hidden="true"
            ></span>
            <span class="name">{label.name}</span>
            <span class="count">{ids.size}</span>
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .browser {
    display: flex;
    flex-direction: column;
    gap: 4px;
    border-top: 1px solid var(--border);
    padding-top: 10px;
    margin-top: 2px;
  }
  .head {
    display: flex;
    align-items: center;
  }
  .title {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }
  .empty {
    margin: 0;
    font-size: 11px;
    color: var(--muted);
    padding: 2px 0;
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 7px;
    width: 100%;
    padding: 4px 6px;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    color: var(--text);
    font: inherit;
    font-size: 12px;
    text-align: left;
    cursor: pointer;
  }
  .row:hover:not(:disabled) {
    background: rgba(0, 212, 170, 0.08);
  }
  .row.active {
    border-color: var(--accent);
    color: var(--accent);
    background: rgba(0, 212, 170, 0.12);
  }
  .row.empty-row {
    opacity: 0.4;
    cursor: default;
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .count {
    flex: 0 0 auto;
    font-size: 10px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .row.active .count {
    color: var(--accent);
  }
</style>
