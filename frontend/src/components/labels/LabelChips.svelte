<script lang="ts">
  // Label chips (item 11) — renders a node/domain's labels next to its name in
  // the right panel and lists. Ids in, full labels resolved from the catalog
  // store so a recolor/rename shows everywhere without the payload carrying
  // stale appearance. Direct labels render solid; via-domain ones carry a
  // "via domain" badge (the dedupe already happened server-side, so the two
  // lists never overlap).

  import { labelsStore } from '$lib/stores/labels.svelte';

  interface Props {
    labelIds: readonly number[];
    /** Labels inherited from the domain — rendered with a "via domain" badge. */
    domainLabelIds?: readonly number[];
    /** Smaller chips for dense list rows. */
    compact?: boolean;
  }

  const { labelIds, domainLabelIds = [], compact = false }: Props = $props();

  const direct = $derived(labelsStore.resolve(labelIds));
  const viaDomain = $derived(labelsStore.resolve(domainLabelIds));

  // A label's swatch color, falling back to the accent when unset.
  function swatch(color: string | null): string {
    return color ?? 'var(--accent)';
  }
</script>

{#if direct.length > 0 || viaDomain.length > 0}
  <div class="chips" class:compact role="list" aria-label="Labels">
    {#each direct as label (label.id)}
      <span class="chip" role="listitem" title={label.description ?? label.name}>
        <span class="dot" style:background={swatch(label.color)} aria-hidden="true"></span>
        {label.name}
      </span>
    {/each}
    {#each viaDomain as label (label.id)}
      <span
        class="chip via"
        role="listitem"
        title={`${label.name} — via domain${label.description ? `: ${label.description}` : ''}`}
      >
        <span class="dot" style:background={swatch(label.color)} aria-hidden="true"></span>
        {label.name}
        <span class="via-badge">via domain</span>
      </span>
    {/each}
  </div>
{/if}

<style>
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    align-items: center;
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 1px 7px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: rgba(0, 212, 170, 0.06);
    color: var(--text);
    font-size: 11px;
    white-space: nowrap;
    user-select: none;
  }

  .chips.compact .chip {
    padding: 0 6px;
    font-size: 10px;
  }

  .chip.via {
    background: transparent;
    color: var(--muted);
    border-style: dashed;
  }

  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .chips.compact .dot {
    width: 6px;
    height: 6px;
  }

  .via-badge {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    opacity: 0.8;
  }
</style>
