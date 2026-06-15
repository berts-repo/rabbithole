<script lang="ts">
  // Anchored popover off the graph toolbar's Filter button. The control
  // groups themselves live in GraphFilterControls (shared with the
  // Settings → Graph tab); this component owns only the popover chrome:
  // positioning, the "Filters" header, and dismissal on Escape /
  // click-outside / the toolbar button toggling again (parent owns the
  // open flag).

  import GraphFilterControls from './GraphFilterControls.svelte';

  type Props = { onClose: () => void };
  const { onClose }: Props = $props();

  let popoverEl: HTMLDivElement | null = $state(null);

  function onDocClick(e: MouseEvent) {
    if (!popoverEl) return;
    if (popoverEl.contains(e.target as Node)) return;
    onClose();
  }
  function onKeyDown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onClose();
    }
  }
  $effect(() => {
    document.addEventListener('click', onDocClick, true);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('click', onDocClick, true);
      document.removeEventListener('keydown', onKeyDown);
    };
  });
</script>

<div
  bind:this={popoverEl}
  class="popover"
  role="dialog"
  aria-label="Graph filters"
>
  <header class="head">Filters</header>
  <GraphFilterControls />
</div>

<style>
  .popover {
    position: absolute;
    top: 100%;
    right: 4px;
    z-index: 50;
    width: 260px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
    display: flex;
    flex-direction: column;
    font-size: 12px;
    margin-top: 2px;
    max-height: calc(100vh - 100px);
    overflow-y: auto;
  }
  .head {
    padding: 6px 10px;
    color: var(--muted);
    font-size: 10px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    border-bottom: 1px solid var(--border);
  }
</style>
