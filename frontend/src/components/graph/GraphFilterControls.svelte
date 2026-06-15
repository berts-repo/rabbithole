<script lang="ts">
  // The three graph-filter control groups — Topology, Colour, Overlays —
  // extracted from FilterShelf so the same controls render in two places:
  // the toolbar filter popover (FilterShelf wraps this in an anchored
  // popover) and the Settings → Graph tab (embeds it directly).
  //
  // Every control reads/writes graphFiltersStore, which persists each
  // change to a settings.graph.* key. Critically, nothing here fires a
  // network refetch — the canvas re-renders from the already-fetched
  // payload via reducer hidden flags + colour switching; the only network
  // hit is the store's fire-and-forget PUT /api/settings/<key>.

  import {
    graphFiltersStore,
    type ColorMode,
    type EdgeMode,
  } from '$lib/stores/graphFilters.svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { labelsStore } from '$lib/stores/labels.svelte';
  import { labelFilterStore } from '$lib/stores/labelFilter.svelte';
  import { graphCollapseStore } from '$lib/stores/graphCollapse.svelte';

  const COLOR_MODES: ReadonlyArray<{ id: ColorMode; label: string; tip?: string }> = [
    { id: 'none', label: 'None' },
    { id: 'domain', label: 'Domain' },
    { id: 'cluster', label: 'Cluster', tip: 'No cluster data yet — run a Cluster analysis to populate this' },
    { id: 'depth', label: 'Depth' },
    { id: 'category', label: 'Category', tip: 'No category data yet — queue an AI Category analysis to populate this' },
    { id: 'infra', label: 'Infra cluster', tip: 'No infra cluster data yet — crawled pages with CSP headers populate this automatically' },
    { id: 'label', label: 'Label', tip: 'No labels on any node yet — attach a label to a resource or domain to populate this' },
    { id: 'network', label: 'Network', tip: 'Tor (.onion) vs I2P (.i2p) — every node has a network' },
  ];

  // Set of colour modes that have at least one node with a non-null value
  // for that mode's field. Modes absent from this set get a greyed button
  // and a tooltip explaining how to populate the field.
  const ALL_COLOR_MODES = COLOR_MODES.length; // every mode populated → stop scanning
  const populatedModes = $derived.by(() => {
    const nodes = graphStore.payload?.nodes;
    const set = new Set<ColorMode>(['none', 'domain', 'depth', 'network']); // always populated
    if (!nodes || nodes.length === 0) return set;
    for (const n of nodes) {
      if (n.cluster_id !== null) set.add('cluster');
      if (n.category !== null) set.add('category');
      if (n.infra_cluster_id !== null) set.add('infra');
      if (n.label_ids.length > 0 || n.domain_label_ids.length > 0) set.add('label');
      if (set.size === ALL_COLOR_MODES) break;
    }
    return set;
  });

  // Labels present anywhere in the catalog gate the tri-state filter group —
  // it only renders when there are labels to mark include/exclude.
  const filterableLabels = $derived(labelsStore.visible);

  const EDGE_MODES: ReadonlyArray<{ id: EdgeMode; label: string }> = [
    { id: 'all', label: 'All' },
    { id: 'cross-site', label: 'Cross-site' },
    { id: 'same-site', label: 'Same-site' },
  ];
</script>

<section class="group">
  <h3>Topology</h3>

  <label class="row range">
    <span class="lbl">Max hops</span>
    <input
      type="range"
      min="0"
      max="10"
      step="1"
      value={graphFiltersStore.maxHops}
      oninput={(e) =>
        graphFiltersStore.setMaxHops(Number((e.target as HTMLInputElement).value))}
    />
    <span class="val">
      {graphFiltersStore.maxHops === 0 ? '∞' : graphFiltersStore.maxHops}
    </span>
  </label>

  <label class="row">
    <input
      type="checkbox"
      checked={graphFiltersStore.showUncrawled}
      onchange={(e) =>
        graphFiltersStore.setShowUncrawled((e.target as HTMLInputElement).checked)}
    />
    <span>Show uncrawled</span>
  </label>

  <label class="row">
    <input
      type="checkbox"
      checked={graphFiltersStore.hideOrphans}
      onchange={(e) =>
        graphFiltersStore.setHideOrphans((e.target as HTMLInputElement).checked)}
    />
    <span>Hide orphans</span>
  </label>

  <label class="row">
    <input
      type="checkbox"
      checked={graphFiltersStore.mutualOnly}
      onchange={(e) =>
        graphFiltersStore.setMutualOnly((e.target as HTMLInputElement).checked)}
    />
    <span>Mutual clusters only</span>
  </label>

  <label class="row">
    <input
      type="checkbox"
      checked={graphFiltersStore.groupByDomain}
      onchange={(e) =>
        graphFiltersStore.setGroupByDomain((e.target as HTMLInputElement).checked)}
    />
    <span>Group by domain</span>
  </label>

  <label class="row">
    <input
      type="checkbox"
      checked={!graphFiltersStore.showAllEdges}
      onchange={(e) =>
        graphFiltersStore.setShowAllEdges(
          !(e.target as HTMLInputElement).checked,
        )}
    />
    <span>Dedup edges per domain</span>
  </label>

  <fieldset class="row segmented">
    <legend>Edges</legend>
    {#each EDGE_MODES as m (m.id)}
      <button
        type="button"
        class="seg"
        class:active={graphFiltersStore.edgeMode === m.id}
        onclick={() => graphFiltersStore.setEdgeMode(m.id)}
      >
        {m.label}
      </button>
    {/each}
  </fieldset>
</section>

<section class="group">
  <h3>Colour</h3>
  <fieldset class="row segmented stacked">
    <legend>Mode</legend>
    {#each COLOR_MODES as m (m.id)}
      {@const populated = populatedModes.has(m.id)}
      <button
        type="button"
        class="seg"
        class:active={graphFiltersStore.colorMode === m.id}
        class:unpopulated={!populated}
        title={!populated && m.tip ? m.tip : undefined}
        onclick={() => graphFiltersStore.setColorMode(m.id)}
      >
        {m.label}
      </button>
    {/each}
  </fieldset>
</section>

{#if filterableLabels.length > 0}
  <section class="group">
    <div class="group-head">
      <h3>Labels</h3>
      {#if labelFilterStore.active}
        <button type="button" class="clear" onclick={() => labelFilterStore.clear()}>
          Clear
        </button>
      {/if}
    </div>
    <p class="hint">Click to cycle: include → exclude → off. Exclude wins.</p>
    <div class="chips">
      {#each filterableLabels as l (l.id)}
        {@const mode = labelFilterStore.modeOf(l.id)}
        <button
          type="button"
          class="chip"
          class:include={mode === 'include'}
          class:exclude={mode === 'exclude'}
          onclick={() => labelFilterStore.cycle(l.id)}
          title={mode === 'include'
            ? 'Including — only nodes with this label'
            : mode === 'exclude'
              ? 'Excluding — hiding nodes with this label'
              : 'Click to include'}
        >
          <span class="dot" style:background={l.color ?? 'var(--muted)'}></span>
          {l.name}
        </button>
      {/each}
    </div>
  </section>

  <section class="group">
    <div class="group-head">
      <h3>Fold by label</h3>
      {#if graphCollapseStore.active}
        <button type="button" class="clear" onclick={() => graphCollapseStore.clear()}>
          Expand all
        </button>
      {/if}
    </div>
    <p class="hint">
      Fold every page carrying a label into one node. A page in several folds
      lands in the highest-ranked; the domain is the floor.
    </p>
    <div class="chips">
      {#each filterableLabels as l (l.id)}
        {@const folded = graphCollapseStore.isLabelCollapsed(l.id)}
        <button
          type="button"
          class="chip"
          class:fold={folded}
          onclick={() => graphCollapseStore.toggleLabel(l.id)}
          title={folded ? 'Folded — click to expand' : 'Click to fold into one node'}
        >
          <span class="dot" style:background={l.color ?? 'var(--muted)'}></span>
          {l.name}
        </button>
      {/each}
    </div>
  </section>
{/if}

<section class="group">
  <h3>Overlays</h3>

  <label class="row">
    <input
      type="checkbox"
      checked={graphFiltersStore.flaggedBorders}
      onchange={(e) =>
        graphFiltersStore.setFlaggedBorders(
          (e.target as HTMLInputElement).checked,
        )}
    />
    <span>Flagged borders</span>
  </label>

  <label class="row">
    <input
      type="checkbox"
      checked={graphFiltersStore.isolate}
      onchange={(e) =>
        graphFiltersStore.setIsolate((e.target as HTMLInputElement).checked)}
    />
    <span>Isolate hover/focus</span>
  </label>

  <label class="row">
    <input
      type="checkbox"
      checked={graphFiltersStore.bridgeHighlight}
      onchange={(e) =>
        graphFiltersStore.setBridgeHighlight(
          (e.target as HTMLInputElement).checked,
        )}
    />
    <span>Bridge highlight</span>
  </label>

  {#if graphFiltersStore.bridgeHighlight}
    <label class="row range nested">
      <span class="lbl">min betweenness</span>
      <input
        type="range"
        min="0"
        max="1"
        step="0.05"
        value={graphFiltersStore.bridgeBetweennessMin}
        oninput={(e) =>
          graphFiltersStore.setBridgeBetweennessMin(
            Number((e.target as HTMLInputElement).value),
          )}
      />
      <span class="val">{graphFiltersStore.bridgeBetweennessMin.toFixed(2)}</span>
    </label>

    <label class="row range nested">
      <span class="lbl">min in-degree</span>
      <input
        type="number"
        min="0"
        max="1000"
        step="1"
        value={graphFiltersStore.bridgeInDegreeMin}
        oninput={(e) =>
          graphFiltersStore.setBridgeInDegreeMin(
            Number((e.target as HTMLInputElement).value),
          )}
      />
    </label>
  {/if}
</section>

<style>
  .group {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .group:last-child {
    border-bottom: none;
  }
  h3 {
    margin: 0 0 4px 0;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    font-weight: 500;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--text);
    padding: 2px 0;
    cursor: pointer;
    line-height: 1.4;
  }
  .row.range {
    flex-wrap: nowrap;
  }
  .row.range .lbl {
    min-width: 76px;
    color: var(--muted);
  }
  .row.range input[type='range'] {
    flex: 1;
    accent-color: var(--accent);
  }
  .row.range input[type='number'] {
    width: 60px;
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 2px 4px;
    font: inherit;
    border-radius: 3px;
  }
  .row.range .val {
    min-width: 28px;
    text-align: right;
    color: var(--accent);
    font-variant-numeric: tabular-nums;
  }
  .row.range.nested {
    padding-left: 22px;
  }
  fieldset.segmented {
    display: flex;
    gap: 2px;
    border: none;
    padding: 0;
    margin: 0;
    flex-wrap: wrap;
  }
  fieldset.segmented legend {
    color: var(--muted);
    padding: 0;
    margin-right: 8px;
    flex: 0 0 auto;
  }
  fieldset.segmented.stacked {
    flex-direction: column;
    align-items: stretch;
  }
  fieldset.segmented.stacked legend {
    margin: 0 0 4px 0;
  }
  .seg {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 2px 8px;
    border-radius: 3px;
    cursor: pointer;
    font: inherit;
  }
  .seg:hover {
    color: var(--accent);
    border-color: var(--accent);
  }
  .seg.active {
    background: var(--accent-bg-subtle, rgba(0, 212, 170, 0.12));
    border-color: var(--accent);
    color: var(--accent);
  }
  .seg.unpopulated {
    opacity: 0.4;
  }
  .group-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .group-head h3 {
    margin: 0;
  }
  .clear {
    background: transparent;
    border: none;
    color: var(--muted);
    cursor: pointer;
    font: inherit;
    font-size: 10px;
    padding: 0;
  }
  .clear:hover {
    color: var(--accent);
  }
  .hint {
    margin: 0 0 2px 0;
    font-size: 10px;
    color: var(--muted);
    line-height: 1.3;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 2px 8px;
    border-radius: 10px;
    cursor: pointer;
    font: inherit;
    line-height: 1.4;
  }
  .chip:hover {
    border-color: var(--accent);
    color: var(--text);
  }
  .chip.include {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--accent-bg-subtle, rgba(0, 212, 170, 0.12));
  }
  .chip.exclude {
    border-color: #fb7185;
    color: #fb7185;
    background: rgba(251, 113, 133, 0.12);
    text-decoration: line-through;
  }
  .chip.fold {
    border-color: var(--accent);
    color: var(--text);
    background: var(--accent-bg-subtle, rgba(0, 212, 170, 0.12));
  }
  .chip .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex: 0 0 auto;
  }
</style>
