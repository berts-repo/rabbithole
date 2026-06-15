<script lang="ts">
  // Cluster workspace — Common tab.
  //
  // Shared entities across the selected nodes. Fetched once on tab open
  // (crawled-only via the backend's HAVING matches >= 2 query); ⟳
  // refresh re-runs the query. Each row shows: type chip · value
  // (monospace) · "seen on N / M nodes" count. Click / right-click
  // opens the same per-type entity menu used by the Page and Domain
  // tabs.
  //
  // Spec: docs/specs/right-pane.md:377-385.

  import { RefreshCw } from 'lucide-svelte';
  import { onMount } from 'svelte';
  import {
    ApiError,
    listCommonEntities,
    type CommonEntity,
  } from '$lib/api';
  import ContextMenu from '$lib/contextMenu/ContextMenu.svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { buildEntityMenu } from '../entityMenu';
  import { resolveFromPayload } from './nodeBag';
  import type { MenuSection } from '$lib/contextMenu/ContextMenu.svelte';

  let rows = $state<CommonEntity[]>([]);
  let total = $state(0);
  let uncrawledCount = $state(0);
  let loading = $state(false);
  let loadError = $state<string | null>(null);
  let fetchGen = 0;

  let rootEl = $state<HTMLDivElement | null>(null);

  // Re-fetch whenever the selected set changes.
  $effect(() => {
    const ids = Array.from(selectionStore.selectedIds);
    void load(ids);
  });

  onMount(() => {
    // Compute uncrawled count once on mount; the $effect above will
    // overwrite as the selection settles.
  });

  async function load(ids: number[]): Promise<void> {
    const gen = ++fetchGen;
    if (ids.length === 0) {
      rows = [];
      total = 0;
      uncrawledCount = 0;
      return;
    }

    // Uncrawled nodes are visible to the analyst even though the backend
    // skips them. Compute the count from the resolvable payload so we can
    // surface the "N uncrawled excluded" notice without an extra fetch.
    const { resolved } = resolveFromPayload(ids, graphStore.payload);
    uncrawledCount = Array.from(resolved.values()).filter((r) => r.uncrawled).length;

    loading = true;
    loadError = null;
    try {
      const res = await listCommonEntities(ids);
      if (gen !== fetchGen) return;
      rows = res.entities;
      total = rows[0]?.total ?? 0;
    } catch (err) {
      if (gen !== fetchGen) return;
      rows = [];
      total = 0;
      loadError = explainError(err, 'Load failed');
    } finally {
      if (gen === fetchGen) loading = false;
    }
  }

  function refresh(): void {
    void load(Array.from(selectionStore.selectedIds));
  }

  // ---------------- Grouping ----------------

  let grouped = $derived.by(() => {
    const out = new Map<string, CommonEntity[]>();
    for (const r of rows) {
      const list = out.get(r.type) ?? [];
      list.push(r);
      out.set(r.type, list);
    }
    return Array.from(out.entries()).map(([type, items]) => ({
      type,
      items,
    }));
  });

  // ---------------- Entity menu ----------------

  let entityMenu = $state<{
    x: number;
    y: number;
    sections: MenuSection[];
  } | null>(null);

  function openEntityMenu(e: MouseEvent, type: string, value: string): void {
    e.preventDefault();
    const parent = rootEl;
    if (!parent) return;
    const r = parent.getBoundingClientRect();
    entityMenu = {
      x: e.clientX - r.left,
      y: e.clientY - r.top,
      sections: buildEntityMenu(type, value),
    };
  }
  function closeEntityMenu(): void {
    entityMenu = null;
  }

  // ---------------- Helpers ----------------

  function explainError(err: unknown, fallback: string): string {
    if (err instanceof ApiError) return `${fallback}: ${err.message}`;
    if (err instanceof Error) return `${fallback}: ${err.message}`;
    return fallback;
  }
</script>

<div class="root" bind:this={rootEl}>
  <header class="head">
    <span class="block-label">
      Shared entities ({rows.length}{total > 0 ? ` over ${total} crawled` : ''})
    </span>
    <button
      type="button"
      class="refresh"
      aria-label="Refresh"
      onclick={refresh}
      disabled={loading}
    >
      <RefreshCw size={11} />
    </button>
  </header>

  {#if uncrawledCount > 0}
    <p class="notice">
      {uncrawledCount} uncrawled excluded — no entities available until crawled.
    </p>
  {/if}

  {#if loading && rows.length === 0}
    <p class="empty">Loading…</p>
  {:else if loadError}
    <p class="empty error">{loadError}</p>
  {:else if rows.length === 0}
    <p class="empty">No shared entities across selected nodes.</p>
  {:else}
    <div class="groups">
      {#each grouped as g (g.type)}
        <section class="group">
          <span class="group-label">{g.type}</span>
          <div class="entities">
            {#each g.items as e, i (i)}
              <button
                type="button"
                class="entity-row"
                onclick={(ev) => openEntityMenu(ev, e.type, e.value)}
                oncontextmenu={(ev) => openEntityMenu(ev, e.type, e.value)}
              >
                <span class="entity-value">{e.value}</span>
                <span class="entity-count">{e.matches} / {e.total}</span>
              </button>
            {/each}
          </div>
        </section>
      {/each}
    </div>
  {/if}

  {#if entityMenu}
    <ContextMenu
      sections={entityMenu.sections}
      x={entityMenu.x}
      y={entityMenu.y}
      onClose={closeEntityMenu}
    />
  {/if}
</div>

<style>
  .root {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: 8px;
    font-size: 11px;
    color: var(--text);
  }
  .head {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .block-label {
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .refresh {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 2px;
    color: var(--muted);
    padding: 3px 6px;
    cursor: pointer;
    line-height: 0;
  }
  .refresh:hover:not(:disabled) {
    color: var(--accent);
    border-color: var(--accent);
  }
  .refresh:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .notice {
    margin: 0;
    padding: 6px 8px;
    border: 1px solid #b08a3a;
    border-radius: 2px;
    background: rgba(176, 138, 58, 0.1);
    color: #e0b860;
    font-size: 11px;
  }
  .empty {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
    font-style: italic;
  }
  .empty.error {
    color: #ff6b6b;
    font-style: normal;
  }

  .groups {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .group {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .group-label {
    align-self: flex-start;
    padding: 1px 6px;
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--muted);
    font-size: 9px;
    text-transform: lowercase;
  }
  .entities {
    display: flex;
    flex-direction: column;
  }
  .entity-row {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    align-items: baseline;
    padding: 3px 4px;
    background: transparent;
    border: none;
    color: var(--text);
    font-size: 11px;
    text-align: left;
    cursor: pointer;
    border-radius: 2px;
  }
  .entity-row:hover {
    background: rgba(0, 212, 170, 0.08);
  }
  .entity-value {
    font-family: ui-monospace, monospace;
    word-break: break-all;
  }
  .entity-count {
    color: var(--muted);
    font-size: 10px;
    white-space: nowrap;
  }
</style>
