<script lang="ts">
  // Labels sub-tab (item 11, Phase 3a) — the analyst's home for the label
  // taxonomy's *rank* ordering and a browse-by-label surface.
  //
  // The single-row list is the D5 rank list: drag a label up or down and the
  // new order is written to `rank` (labelsStore.reorder, server-authoritative).
  // Expanding a label fetches its members lazily; clicking a member is
  // HIGHLIGHT-ONLY (per the plan — browsing a label is exploration, like the
  // Domains tab, not a full select). A resource highlights its node; a domain
  // highlights every node of that host currently in the graph.
  //
  // The trailing graph-icon opens "all resources labeled X" as its own
  // workspace tab (the `label` NodeSetSource), capturing the resource node ids.

  import { onMount } from 'svelte';
  import {
    ChevronDown,
    ChevronRight,
    GripVertical,
    Network,
    RefreshCw,
  } from 'lucide-svelte';
  import { listLabelMembers, type Label, type LabelMembers } from '$lib/api';
  import { labelsStore } from '$lib/stores/labels.svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { domainVisibilityStore } from '$lib/stores/domainVisibility.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { workspaceStore } from '$lib/stores/workspace.svelte';
  import BottomPaneRow from './BottomPaneRow.svelte';
  import { reorderedIds } from '$lib/labels/order';
  import { domainDisplayName, labelTabLabel, memberDisplayName } from './labels';

  // Catalog loads at boot; ensure + a manual refresh path for member counts
  // that drift as the analyst tags from elsewhere.
  let refreshing = $state(false);

  onMount(() => {
    void labelsStore.ensureLoaded();
  });

  async function refresh(): Promise<void> {
    refreshing = true;
    try {
      await labelsStore.refresh();
      members.clear();
      members = new Map(members);
    } catch (err) {
      toastStore.show(
        `Labels refresh failed: ${err instanceof Error ? err.message : String(err)}`,
        'warn',
      );
    } finally {
      refreshing = false;
    }
  }

  // Expansion + lazily-fetched member cache, keyed by label id.
  let expanded = $state<Set<number>>(new Set());
  let members = $state<Map<number, LabelMembers>>(new Map());
  let loadingId = $state<number | null>(null);

  async function ensureMembers(id: number): Promise<LabelMembers | null> {
    const cached = members.get(id);
    if (cached) return cached;
    loadingId = id;
    try {
      const m = await listLabelMembers(id);
      members.set(id, m);
      members = new Map(members);
      return m;
    } catch (err) {
      toastStore.show(
        `Couldn't load members: ${err instanceof Error ? err.message : String(err)}`,
        'error',
      );
      return null;
    } finally {
      loadingId = null;
    }
  }

  function toggleExpand(id: number): void {
    const next = new Set(expanded);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
      void ensureMembers(id);
    }
    expanded = next;
  }

  // host → node ids in the current graph, for highlighting a domain member.
  const nodesByHost = $derived.by<Map<string, number[]>>(() => {
    const map = new Map<string, number[]>();
    for (const n of graphStore.payload?.nodes ?? []) {
      if (!n.domain) continue;
      const arr = map.get(n.domain);
      if (arr) arr.push(n.id);
      else map.set(n.domain, [n.id]);
    }
    return map;
  });

  function highlightResource(id: number): void {
    selectionStore.highlight(id);
  }

  function highlightDomain(host: string): void {
    const ids = nodesByHost.get(host);
    if (!ids || ids.length === 0) {
      toastStore.show(`No graph nodes for ${host} in this workspace.`, 'info');
      return;
    }
    selectionStore.replaceMulti(ids);
  }

  async function openLabelAsTab(label: Label): Promise<void> {
    const m = await ensureMembers(label.id);
    if (!m) return;
    const ids = m.resources.map((r) => r.id);
    if (ids.length === 0) {
      toastStore.show(`No resources labeled “${label.name}” to open.`, 'info');
      return;
    }
    workspaceStore.openNodeSetTab(
      { kind: 'label', labelId: label.id, nodeIds: ids, summary: String(label.id) },
      labelTabLabel(label.name),
    );
  }

  // --- drag reorder (writes rank) -------------------------------------------

  let dragId = $state<number | null>(null);
  let overId = $state<number | null>(null);

  function onDragStart(e: DragEvent, id: number): void {
    dragId = id;
    e.dataTransfer?.setData('text/plain', String(id));
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
  }

  function onDragOver(e: DragEvent, id: number): void {
    if (dragId === null) return;
    e.preventDefault();
    overId = id;
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
  }

  async function onDrop(e: DragEvent, targetId: number): Promise<void> {
    e.preventDefault();
    const from = labelsStore.labels.findIndex((l) => l.id === dragId);
    const to = labelsStore.labels.findIndex((l) => l.id === targetId);
    dragId = null;
    overId = null;
    if (from === -1 || to === -1 || from === to) return;
    const order = reorderedIds(
      labelsStore.labels.map((l) => l.id),
      from,
      to,
    );
    try {
      await labelsStore.reorder(order);
    } catch (err) {
      toastStore.show(
        `Reorder failed: ${err instanceof Error ? err.message : String(err)}`,
        'error',
      );
    }
  }

  function onDragEnd(): void {
    dragId = null;
    overId = null;
  }
</script>

<section class="labels">
  <header class="head">
    <span class="title">Labels</span>
    <span class="count">{labelsStore.labels.length}</span>
    <span class="spacer"></span>
    <button
      type="button"
      class="icon"
      aria-label="Refresh"
      title="Refresh counts"
      onclick={() => void refresh()}
      disabled={refreshing}
    >
      <RefreshCw size={12} />
    </button>
  </header>

  {#if !labelsStore.loaded}
    <p class="empty">Loading labels…</p>
  {:else if labelsStore.labels.length === 0}
    <p class="empty">No labels yet — create one from a label picker.</p>
  {:else}
    <p class="hint">Drag to reorder — higher in the list ranks higher.</p>
    <ul class="list">
      {#each labelsStore.labels as label (label.id)}
        {@const isOpen = expanded.has(label.id)}
        {@const mem = members.get(label.id)}
        <li
          class:dragover={overId === label.id && dragId !== label.id}
          class:dragging={dragId === label.id}
          ondragover={(e) => onDragOver(e, label.id)}
          ondrop={(e) => void onDrop(e, label.id)}
          role="presentation"
        >
          <div class="label-row">
            <span
              class="grip"
              draggable="true"
              role="button"
              tabindex="-1"
              aria-label="Drag to reorder {label.name}"
              title="Drag to reorder"
              ondragstart={(e) => onDragStart(e, label.id)}
              ondragend={onDragEnd}
            >
              <GripVertical size={12} />
            </span>
            <button
              type="button"
              class="disclose"
              aria-label={isOpen ? 'Collapse' : 'Expand'}
              aria-expanded={isOpen}
              onclick={() => toggleExpand(label.id)}
            >
              {#if isOpen}<ChevronDown size={12} />{:else}<ChevronRight size={12} />{/if}
            </button>
            <span
              class="dot"
              style:background={label.color ?? 'var(--accent)'}
              aria-hidden="true"
            ></span>
            <button type="button" class="name" onclick={() => toggleExpand(label.id)}>
              {label.name}
              {#if label.hidden}<span class="tag">hidden</span>{/if}
            </button>
            <span class="counts" title="Resources · Domains">
              {label.resource_count}·{label.domain_count}
            </span>
            <button
              type="button"
              class="icon open"
              aria-label="Open resources labeled {label.name} as a graph tab"
              title="Open as graph tab"
              onclick={() => void openLabelAsTab(label)}
              disabled={label.resource_count === 0}
            >
              <Network size={12} />
            </button>
          </div>

          {#if isOpen}
            <div class="members">
              {#if loadingId === label.id && !mem}
                <p class="sub-empty">Loading…</p>
              {:else if mem && mem.resources.length === 0 && mem.domains.length === 0}
                <p class="sub-empty">No members.</p>
              {:else if mem}
                {#each mem.domains as d (d.host)}
                  {@const visible = domainVisibilityStore.isVisible(d.host)}
                  <BottomPaneRow
                    {visible}
                    active={false}
                    visibilityLabel={visible ? `Hide ${d.host}` : `Show ${d.host}`}
                    onToggleVisibility={() => domainVisibilityStore.toggle(d.host)}
                    onSelect={() => highlightDomain(d.host)}
                  >
                    <span class="m-domain" title={d.host}>{domainDisplayName(d)}</span>
                    <span class="m-kind">domain</span>
                  </BottomPaneRow>
                {/each}
                {#each mem.resources as r (r.id)}
                  {@const visible = domainVisibilityStore.isVisible(r.host)}
                  {@const active =
                    selectionStore.selectMode === 'highlight' &&
                    selectionStore.selectedNodeId === r.id}
                  <BottomPaneRow
                    {visible}
                    {active}
                    visibilityLabel={visible ? `Hide ${r.host}` : `Show ${r.host}`}
                    onToggleVisibility={() => domainVisibilityStore.toggle(r.host)}
                    onSelect={() => highlightResource(r.id)}
                  >
                    <span class="m-name" title={r.url}>{memberDisplayName(r)}</span>
                  </BottomPaneRow>
                {/each}
              {/if}
            </div>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .labels {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-height: 0;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .title {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }
  .count {
    font-size: 11px;
    color: var(--muted);
  }
  .spacer {
    flex: 1;
  }
  .icon {
    background: transparent;
    border: 1px solid transparent;
    color: var(--muted);
    padding: 2px 4px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 2px;
  }
  .icon:hover:not(:disabled) {
    border-color: var(--border);
    color: var(--accent);
  }
  .icon:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .hint {
    margin: 0;
    font-size: 10px;
    color: var(--muted);
  }
  .empty {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
    padding: 6px 4px;
  }
  .list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .list > li {
    border-radius: 2px;
  }
  .list > li.dragover {
    box-shadow: inset 0 2px 0 var(--accent);
  }
  .list > li.dragging {
    opacity: 0.5;
  }
  .label-row {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 3px 4px;
    border-radius: 2px;
  }
  .label-row:hover {
    background: rgba(0, 212, 170, 0.06);
  }
  .grip {
    flex: 0 0 auto;
    display: inline-flex;
    color: var(--muted);
    cursor: grab;
  }
  .grip:active {
    cursor: grabbing;
  }
  .disclose {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    background: transparent;
    border: none;
    color: var(--muted);
    cursor: pointer;
    padding: 0;
  }
  .disclose:hover {
    color: var(--accent);
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .name {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 6px;
    background: transparent;
    border: none;
    color: var(--text);
    font: inherit;
    font-size: 12px;
    text-align: left;
    cursor: pointer;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .name:hover {
    color: var(--accent);
  }
  .tag {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
  }
  .counts {
    flex: 0 0 auto;
    font-size: 10px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .members {
    margin: 1px 0 3px 22px;
    display: flex;
    flex-direction: column;
    gap: 1px;
    border-left: 1px solid var(--border);
    padding-left: 4px;
  }
  .sub-empty {
    margin: 0;
    font-size: 10px;
    color: var(--muted);
    padding: 3px 4px;
  }
  .m-name,
  .m-domain {
    color: var(--accent);
    font-size: 11px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .m-kind {
    margin-left: 6px;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
  }
</style>
