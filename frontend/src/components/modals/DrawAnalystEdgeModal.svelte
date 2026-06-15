<script lang="ts">
  // Draw Analyst Edge modal. Two modes:
  //   batch       — connect every pair in a selection (fully-connected set)
  //   sequential  — connect one source → destination pair
  // The edge "type" is a preset (or Custom free text); it is stored in the
  // edge's label column — no schema change. Spec: explore-graph.md:56-62.

  import Modal from './Modal.svelte';
  import { createEdge, type GraphNode } from '$lib/api';
  import { toastStore } from '$lib/stores/toast.svelte';

  interface Props {
    mode: 'batch' | 'sequential';
    nodes?: GraphNode[];
    source?: GraphNode;
    dest?: GraphNode;
    onClose: () => void;
    onCreated: () => void;
  }

  let {
    mode,
    nodes = [],
    source,
    dest,
    onClose,
    onCreated,
  }: Props = $props();

  const PRESETS = ['Same operator', 'Shared wallet', 'Mirrors', 'Affiliate'];

  let edgeType = $state<string>('Same operator');
  let customLabel = $state('');
  let busy = $state(false);

  const isCustom = $derived(edgeType === '__custom__');
  const invalid = $derived(isCustom && customLabel.trim().length === 0);

  // Unordered node pairs to connect.
  const pairs = $derived.by<[GraphNode, GraphNode][]>(() => {
    if (mode === 'sequential') {
      return source && dest ? [[source, dest]] : [];
    }
    const out: [GraphNode, GraphNode][] = [];
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        out.push([nodes[i], nodes[j]]);
      }
    }
    return out;
  });

  async function submit(): Promise<void> {
    if (busy || invalid || pairs.length === 0) return;
    busy = true;
    const label = isCustom ? customLabel.trim() : edgeType;
    const results = await Promise.allSettled(
      pairs.map(([a, b]) =>
        createEdge({ from_id: a.id, to_id: b.id, label }),
      ),
    );
    const ok = results.filter((r) => r.status === 'fulfilled').length;
    const failed = results.length - ok;
    if (ok > 0) {
      toastStore.show(
        failed > 0
          ? `Created ${ok} analyst edge(s) — ${failed} failed`
          : `Created ${ok} analyst edge(s)`,
        failed > 0 ? 'warn' : 'info',
      );
      onCreated();
      onClose();
    } else {
      toastStore.show('Edge creation failed', 'error');
      busy = false;
    }
  }
</script>

<Modal
  title="Draw Analyst Edge"
  {onClose}
  onConfirm={() => void submit()}
  confirmLabel={pairs.length > 1 ? `Create (${pairs.length})` : 'Create'}
  confirmDisabled={invalid || pairs.length === 0}
  {busy}
>
  {#if mode === 'sequential' && source && dest}
    <p class="hint">
      <span class="count">{source.raw_url}</span>
      →
      <span class="count">{dest.raw_url}</span>
    </p>
  {:else}
    <p class="hint">
      Connect <span class="count">{nodes.length}</span> selected nodes — will
      create {pairs.length} edge(s).
    </p>
  {/if}

  <label class="row">
    <span>Type</span>
    <select bind:value={edgeType}>
      {#each PRESETS as p (p)}
        <option value={p}>{p}</option>
      {/each}
      <option value="__custom__">Custom…</option>
    </select>
  </label>

  {#if isCustom}
    <label class="row">
      <span>Label</span>
      <input type="text" bind:value={customLabel} placeholder="Edge label" />
    </label>
  {/if}
</Modal>
