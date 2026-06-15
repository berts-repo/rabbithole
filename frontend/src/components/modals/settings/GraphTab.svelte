<script lang="ts">
  // Settings → Graph. Authoritative home for graph defaults: layout,
  // the Topology/Colour/Overlay filters (shared with the toolbar filter
  // shelf via GraphFilterControls), and hide-rules management.
  //
  // The hide-rules subsection absorbs the former bottom-pane Hidden tab:
  // CRUD over the server-side `graph_filters` term list, each term a
  // substring matched against node url + title on the backend's
  // /api/graph build. Adding/removing invalidates the graph cache and
  // kicks the poller so the canvas reflects the change without a manual
  // refresh — the same pattern actHideFromGraph uses.
  //
  // Everything autosaves: the layout + filters round-trip through
  // graphLayoutStore / graphFiltersStore (settings.graph.* keys); the
  // hide rules go straight to the graph_filters CRUD routes.

  import { onMount } from 'svelte';
  import { Plus, X } from 'lucide-svelte';
  import {
    addGraphFilter,
    ApiError,
    deleteGraphFilter,
    listGraphFilters,
  } from '$lib/api';
  import { graphPoller } from '$lib/pollers/graph.svelte';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { graphLayoutStore } from '$lib/stores/graphLayout.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { workspaceSnapshots } from '$lib/stores/workspaceSnapshots.svelte';
  import {
    LAYOUT_KINDS,
    LAYOUT_LABELS,
    type LayoutKind,
  } from '$lib/graph/layouts';
  import GraphFilterControls from '../../graph/GraphFilterControls.svelte';
  import { isDuplicate, isValidTerm, normalizeTerm } from './hideRules';

  // --- hide rules (graph_filters) ---
  let terms = $state<string[]>([]);
  let loaded = $state(false);
  let loadError = $state<string | null>(null);
  let draft = $state('');
  let saving = $state(false);

  onMount(() => {
    void loadTerms();
  });

  async function loadTerms(): Promise<void> {
    loadError = null;
    try {
      const res = await listGraphFilters();
      terms = res.terms;
      loaded = true;
    } catch (err) {
      loadError = err instanceof Error ? err.message : String(err);
    }
  }

  function invalidateGraph(): void {
    // The server already invalidated its cache; the client-side snapshot
    // cache and the ego-focus pin need their own poke.
    if (graphStore.egoFocus) graphStore.setEgoFocus(null);
    workspaceSnapshots.invalidatePayloads();
    void graphPoller.refresh();
  }

  async function onAddTerm(): Promise<void> {
    if (saving) return;
    const term = normalizeTerm(draft);
    if (!isValidTerm(term)) {
      toastStore.show('Enter a term first.', 'warn');
      return;
    }
    if (isDuplicate(term, terms)) {
      toastStore.show('Already hidden.', 'info');
      draft = '';
      return;
    }
    saving = true;
    try {
      const res = await addGraphFilter(term);
      terms = [...terms, res.term].sort();
      draft = '';
      invalidateGraph();
      toastStore.show('Filter added — graph rebuilding.', 'info');
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toastStore.show('Already hidden.', 'info');
        draft = '';
      } else {
        const msg = err instanceof Error ? err.message : String(err);
        toastStore.show(`Add failed: ${msg}`, 'error');
      }
    } finally {
      saving = false;
    }
  }

  async function onRemoveTerm(term: string): Promise<void> {
    try {
      await deleteGraphFilter(term);
      terms = terms.filter((t) => t !== term);
      invalidateGraph();
      toastStore.show('Filter removed — graph rebuilding.', 'info');
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        terms = terms.filter((t) => t !== term);
      } else {
        const msg = err instanceof Error ? err.message : String(err);
        toastStore.show(`Remove failed: ${msg}`, 'error');
      }
    }
  }

  function onAddKey(e: KeyboardEvent): void {
    if (e.key === 'Enter') {
      e.preventDefault();
      void onAddTerm();
    }
  }
</script>

<div class="tab">
  <section class="group">
    <h3>Layout</h3>
    <label class="field">
      <span>Default layout</span>
      <select
        value={graphLayoutStore.kind}
        onchange={(e) =>
          graphLayoutStore.setKind(e.currentTarget.value as LayoutKind)}
      >
        {#each LAYOUT_KINDS as kind (kind)}
          <option value={kind}>{LAYOUT_LABELS[kind]}</option>
        {/each}
      </select>
    </label>
  </section>

  <GraphFilterControls />

  <section class="group">
    <h3>Hide rules</h3>
    <p class="hint">
      Substrings matched against node URL and title. Matching nodes are
      hidden from the graph everywhere.
    </p>

    {#if loadError}
      <p class="empty error">{loadError}</p>
    {:else if !loaded}
      <p class="empty">Loading filters…</p>
    {:else if terms.length === 0}
      <p class="empty">No hide rules yet.</p>
    {:else}
      <ul class="list">
        {#each terms as term (term)}
          <li>
            <span class="term" title={term}>{term}</span>
            <button
              type="button"
              class="icon danger"
              aria-label={`Remove rule "${term}"`}
              title="Remove"
              onclick={() => void onRemoveTerm(term)}
            >
              <X size={12} />
            </button>
          </li>
        {/each}
      </ul>
    {/if}

    <div class="add-row">
      <input
        type="text"
        placeholder="Add a substring to hide…"
        bind:value={draft}
        onkeydown={onAddKey}
        aria-label="New hide rule"
        disabled={saving}
      />
      <button
        type="button"
        class="add"
        onclick={() => void onAddTerm()}
        disabled={saving || !isValidTerm(draft)}
      >
        <Plus size={12} />
        Add
      </button>
    </div>
  </section>
</div>

<style>
  .tab {
    display: flex;
    flex-direction: column;
    font-size: 12px;
  }
  /* Match GraphFilterControls' group rhythm so the embedded controls and
     the local Layout / Hide-rules sections read as one stack. */
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
  .field {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .field > span {
    color: var(--muted);
  }
  .field select {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 3px;
    padding: 5px 7px;
    font: inherit;
    font-size: 12px;
  }
  .field select:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .hint {
    margin: 0 0 2px;
    color: var(--muted);
    font-size: 11px;
  }
  .empty {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
    padding: 4px 0;
  }
  .empty.error {
    color: #ff8899;
  }
  .list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .list li {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 2px 4px;
    border-radius: 2px;
  }
  .list li:hover {
    background: rgba(0, 212, 170, 0.06);
  }
  .term {
    flex: 1 1 auto;
    min-width: 0;
    color: var(--text);
    font-size: 11px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
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
  .icon.danger:hover:not(:disabled) {
    color: #ff5577;
    border-color: #ff5577;
  }
  .add-row {
    display: flex;
    gap: 4px;
    padding-top: 6px;
  }
  .add-row input {
    flex: 1;
    min-width: 0;
    background: #17191f;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 4px 7px;
    font-size: 11px;
  }
  .add-row input:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .add-row input:disabled {
    opacity: 0.6;
  }
  .add {
    background: transparent;
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 4px 10px;
    font-size: 11px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .add:hover:not(:disabled) {
    background: rgba(0, 212, 170, 0.1);
  }
  .add:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
</style>
