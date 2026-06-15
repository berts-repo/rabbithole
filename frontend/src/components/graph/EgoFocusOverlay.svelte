<script lang="ts">
  // Floating top-centre overlay for ego-focus. Shows the focus node's
  // domain, a depth slider, and an exit button. Escape also exits (the
  // canvas owns the keyboard listener).

  import { X } from 'lucide-svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import type { GraphNode } from '$lib/api';

  interface Props {
    onExit: () => void;
    onDepthChange: (depth: 1 | 2 | 3) => void;
  }

  let { onExit, onDepthChange }: Props = $props();

  const focusNode = $derived.by<GraphNode | null>(() => {
    const f = graphStore.egoFocus;
    if (!f) return null;
    const payload = graphStore.payload;
    if (!payload) return null;
    return payload.nodes.find((n) => n.id === f.nodeId) ?? null;
  });

  const depth = $derived(graphStore.egoFocus?.depth ?? 2);
  const domain = $derived(focusNode?.domain ?? focusNode?.raw_url ?? '');

  function onSlider(e: Event): void {
    const v = Number((e.target as HTMLInputElement).value);
    if (v === 1 || v === 2 || v === 3) onDepthChange(v);
  }
</script>

<div class="overlay" role="status">
  <span class="label">Focus:</span>
  <span class="domain">{domain}</span>
  <span class="divider">·</span>
  <label class="depth">
    Depth:
    <input
      type="range"
      min="1"
      max="3"
      step="1"
      value={depth}
      oninput={onSlider}
    />
    <span class="num">{depth}</span>
  </label>
  <button type="button" class="close" aria-label="Exit ego-focus" onclick={onExit}>
    <X size={12} />
  </button>
</div>

<style>
  .overlay {
    position: absolute;
    top: 8px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 8px;
    background: rgba(16, 17, 20, 0.92);
    border: 1px solid var(--accent);
    border-radius: 3px;
    padding: 4px 10px;
    font-size: 11px;
    color: var(--text);
    z-index: 6;
    box-shadow: 0 4px 14px rgba(0, 212, 170, 0.12);
  }
  .label {
    color: var(--muted);
  }
  .domain {
    color: var(--accent);
    max-width: 280px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .divider {
    color: var(--border);
  }
  .depth {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: var(--muted);
  }
  .depth input {
    width: 60px;
    accent-color: var(--accent);
  }
  .num {
    color: var(--text);
    min-width: 1ch;
  }
  .close {
    background: transparent;
    border: none;
    color: var(--muted);
    cursor: pointer;
    padding: 2px;
    display: inline-flex;
  }
  .close:hover {
    color: var(--accent);
  }
</style>
