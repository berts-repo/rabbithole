<script lang="ts">
  // Right pane — Preview tab.
  //
  // Single-node content reader, driven by selectionStore.selectedNodeId.
  // Shows the full cleaned body text (body_text_clean) of the current
  // version, filling the pane height so the analyst can actually read a
  // page without opening it in Tor. This replaces the cramped inline
  // "Content preview" box that used to live in the Page tab.

  import {
    ApiError,
    getNode,
    type NodeRow,
  } from '$lib/api';
  import { isUncrawled } from '$lib/nodeState';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { EmptyState } from '$lib/ui';

  let node = $state<NodeRow | null>(null);
  let loading = $state(false);
  let loadError = $state<string | null>(null);
  // Versioned fetches — a slow request from a previous selection must not
  // overwrite a newer one. The render path keys off the latest id only.
  let fetchGen = 0;

  $effect(() => {
    const id = selectionStore.selectedNodeId;
    void load(id);
  });

  async function load(id: number | null): Promise<void> {
    const gen = ++fetchGen;
    if (id === null) {
      node = null;
      loading = false;
      loadError = null;
      return;
    }
    loading = true;
    loadError = null;
    try {
      const n = await getNode(id);
      if (gen !== fetchGen) return;
      node = n;
    } catch (err) {
      if (gen !== fetchGen) return;
      node = null;
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
</script>

{#if selectionStore.selectedNodeId === null}
  <EmptyState title="No node selected." />
{:else if loading && !node}
  <EmptyState title="Loading…" />
{:else if loadError}
  <EmptyState title={loadError} error />
{:else if node}
  {#if isUncrawled(node)}
    <EmptyState title="Not crawled yet — no content to preview." />
  {:else if node.body_text_clean}
    <pre class="preview">{node.body_text_clean}</pre>
  {:else}
    <EmptyState title="No text captured for this page." />
  {/if}
{/if}

<style>
  .preview {
    margin: 0;
    padding: 8px 10px;
    background: rgba(0, 0, 0, 0.25);
    border-radius: 2px;
    color: var(--text);
    font-family: ui-monospace, monospace;
    font-size: 11px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
  }
</style>
