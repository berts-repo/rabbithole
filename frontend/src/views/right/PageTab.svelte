<script lang="ts">
  // Right pane — Page tab (F6 phase 1).
  //
  // Single-node detail view, driven by selectionStore.selectedNodeId.
  // Loads node detail + collections + notes in parallel on every URL
  // change. Stub nodes get a simplified state — most sections collapse
  // away and a prominent "Send to Crawl" leads.
  //
  // Spec: docs/specs/right-pane.md (lines 36-119).

  import { onMount } from 'svelte';
  import { Pencil, Tag, X } from 'lucide-svelte';
  import {
    addItemsToCollection,
    addNodeNote,
    ApiError,
    clearNodeFlags,
    deleteNote,
    getNode,
    getPageVersion,
    getVersionDiff,
    listCollections,
    listNodeCollections,
    listNodeNotes,
    patchFlag,
    patchNodeAnalysisExcluded,
    patchNodeReviewed,
    removeItemFromCollection,
    type Collection,
    type DiffOp,
    type FlagStatus,
    type NodeCollection,
    type NodeRow,
    type NoteRow,
    type PageVersion,
    type UpdateFlagBody,
    type VersionDiff,
  } from '$lib/api';
  import ContextMenu from '$lib/contextMenu/ContextMenu.svelte';
  import RenameAliasPopover from '../../components/graph/RenameAliasPopover.svelte';
  import LabelChips from '../../components/labels/LabelChips.svelte';
  import LabelPickerPopover from '../../components/labels/LabelPickerPopover.svelte';
  import {
    labelPickerModal,
    renameModal,
    renameTarget,
    type LabelPickerModal,
    type RenameModal,
  } from '$lib/contextMenu/actions';
  import { graphPoller } from '$lib/pollers/graph.svelte';
  import { isUncrawled, stateLabel } from '$lib/nodeState';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { buildEntityMenu } from './entityMenu';
  import type { MenuSection } from '$lib/contextMenu/ContextMenu.svelte';
  import { CollapsibleSection, EmptyState, IconButton } from '$lib/ui';
  import { createCollapseStore } from '$lib/stores/sectionCollapse.svelte';
  import { explainError } from '$lib/api/errors';

  const sections = createCollapseStore('rabbithole.right.page');

  // ---------------- Per-selection load ----------------

  let node = $state<NodeRow | null>(null);
  let collections = $state<NodeCollection[]>([]);
  let notes = $state<NoteRow[]>([]);
  let loading = $state(false);
  let loadError = $state<string | null>(null);
  // Versioned fetches — a slow request from a previous selection must not
  // overwrite a newer one. The render path keys off the latest id only.
  let fetchGen = 0;

  // Per-node UI toggles. Spec: "Details toggle starts expanded on every
  // node load."
  let detailsOpen = $state(true);

  // ---------------- Version picker + diff (Phase 5) ----------------

  // A pinned snapshot the analyst pulled up from the timeline. It may lag
  // node.current_version_id — viewing an older version does not change which
  // version is current. Null = showing the current snapshot only.
  let pinned = $state<PageVersion | null>(null);
  let pinnedLoading = $state(false);
  let pinnedError = $state<string | null>(null);

  // Compare bar — diff any two versions of this page. Defaults to the two
  // newest (previous → current) so the common "what changed last crawl"
  // question is one click.
  let diffFrom = $state<number | null>(null);
  let diffTo = $state<number | null>(null);
  let diff = $state<VersionDiff | null>(null);
  let diffLoading = $state(false);
  let diffError = $state<string | null>(null);

  function resetVersionState(): void {
    pinned = null;
    pinnedLoading = false;
    pinnedError = null;
    diff = null;
    diffLoading = false;
    diffError = null;
    diffFrom = null;
    diffTo = null;
  }

  // Seed the compare selects from history once a node loads: newest as the
  // "to" side, second-newest as the "from" side.
  $effect(() => {
    const h = node?.history ?? [];
    if (h.length >= 2 && diffTo === null && diffFrom === null) {
      diffTo = h[0].id;
      diffFrom = h[1].id;
    }
  });

  async function viewVersion(versionId: number): Promise<void> {
    pinnedError = null;
    // Toggle off if the same version is already pinned.
    if (pinned?.id === versionId) {
      pinned = null;
      return;
    }
    pinnedLoading = true;
    try {
      pinned = await getPageVersion(versionId);
    } catch (err) {
      pinned = null;
      pinnedError = explainError(err, 'Snapshot load failed');
    } finally {
      pinnedLoading = false;
    }
  }

  function clearPinned(): void {
    pinned = null;
    pinnedError = null;
  }

  async function runDiff(): Promise<void> {
    if (diffFrom === null || diffTo === null) return;
    if (diffFrom === diffTo) {
      diffError = 'Pick two different versions.';
      diff = null;
      return;
    }
    diffError = null;
    diffLoading = true;
    try {
      diff = await getVersionDiff(diffFrom, diffTo);
    } catch (err) {
      diff = null;
      diffError = explainError(err, 'Diff failed');
    } finally {
      diffLoading = false;
    }
  }

  function clearDiff(): void {
    diff = null;
    diffError = null;
  }

  // ---------------- Effects ----------------

  $effect(() => {
    const id = selectionStore.selectedNodeId;
    void load(id);
  });

  async function load(id: number | null): Promise<void> {
    const gen = ++fetchGen;
    resetVersionState();
    if (id === null) {
      node = null;
      collections = [];
      notes = [];
      loading = false;
      loadError = null;
      return;
    }
    loading = true;
    loadError = null;
    detailsOpen = true;
    try {
      const [n, cRes, nRes] = await Promise.all([
        getNode(id),
        listNodeCollections(id),
        listNodeNotes(id),
      ]);
      if (gen !== fetchGen) return;
      node = n;
      collections = cRes.collections;
      notes = nRes.notes;
    } catch (err) {
      if (gen !== fetchGen) return;
      node = null;
      collections = [];
      notes = [];
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

  // ---------------- Domain alias rename popover ----------------

  let aliasFromNode = $derived.by(() => {
    const host = node?.domain ?? null;
    if (!host) return null;
    // The graph payload carries the alias; node-detail doesn't, so we
    // peek into graphStore by host.
    const match = graphStore.payload?.nodes.find(
      (gn) => gn.domain === host && gn.alias,
    );
    return match?.alias ?? null;
  });

  let aliasPopover = $state<RenameModal | null>(null);

  function openAliasPopover(e: MouseEvent): void {
    if (!node?.domain) return;
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    // Capture the target at open time so the rename completes against the
    // domain the analyst aimed at, even if selection moves on.
    aliasPopover = renameModal(
      { kind: 'domain', host: node.domain },
      { x: r.left + r.width / 2, y: r.bottom + 16 },
      aliasFromNode,
    );
  }
  function closeAliasPopover(): void {
    aliasPopover = null;
  }

  // ---------------- Label picker ----------------

  let labelPopover = $state<LabelPickerModal | null>(null);

  function openLabelPopover(e: MouseEvent): void {
    if (!node) return;
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    labelPopover = labelPickerModal(
      { kind: 'resource', resourceId: node.id, name: node.title ?? node.url },
      { x: r.left + r.width / 2, y: r.bottom + 16 },
      node.label_ids,
    );
  }
  // After the picker closes with changes: refresh the graph (chips on other
  // surfaces) and re-pull this node's membership so the local chips update.
  async function onLabelsChanged(): Promise<void> {
    void graphPoller.refresh();
    if (!node) return;
    const id = node.id;
    try {
      const fresh = await getNode(id);
      if (node?.id === id) {
        node = { ...node, label_ids: fresh.label_ids, domain_label_ids: fresh.domain_label_ids };
      }
    } catch {
      // The graph refresh still carries the change; a failed re-pull is cosmetic.
    }
  }

  // ---------------- Reviewed / Exclude toggles ----------------

  async function toggleReviewed(): Promise<void> {
    if (!node) return;
    const next = !node.reviewed;
    try {
      await patchNodeReviewed(node.id, next);
      node.reviewed = next;
      void graphPoller.refresh();
    } catch (err) {
      toastStore.show(explainError(err, 'Reviewed toggle failed'), 'error');
    }
  }

  async function toggleExcluded(): Promise<void> {
    if (!node) return;
    const next = !node.analysis_excluded;
    try {
      await patchNodeAnalysisExcluded(node.id, next);
      node.analysis_excluded = next;
    } catch (err) {
      toastStore.show(explainError(err, 'Exclude toggle failed'), 'error');
    }
  }

  // ---------------- Collections section ----------------

  let allCollectionsCache = $state<Collection[] | null>(null);
  let pickerOpen = $state(false);
  let pickerLoading = $state(false);
  let pickerError = $state<string | null>(null);

  async function openCollectionPicker(): Promise<void> {
    pickerOpen = true;
    if (allCollectionsCache !== null) return;
    pickerLoading = true;
    pickerError = null;
    try {
      const res = await listCollections();
      allCollectionsCache = res.collections;
    } catch (err) {
      pickerError = explainError(err, 'Load failed');
    } finally {
      pickerLoading = false;
    }
  }

  function closeCollectionPicker(): void {
    pickerOpen = false;
  }

  async function addToCollection(c: Collection): Promise<void> {
    if (!node) return;
    if (collections.some((x) => x.id === c.id)) return;
    try {
      await addItemsToCollection(c.id, [node.id]);
      collections = [...collections, { id: c.id, name: c.name }];
      toastStore.show('Added to collection');
      closeCollectionPicker();
    } catch (err) {
      toastStore.show(explainError(err, 'Add failed'), 'error');
    }
  }

  async function removeFromCollection(cid: number): Promise<void> {
    if (!node) return;
    try {
      await removeItemFromCollection(cid, node.id);
      collections = collections.filter((c) => c.id !== cid);
    } catch (err) {
      toastStore.show(explainError(err, 'Remove failed'), 'error');
    }
  }

  // ---------------- Flag editor ----------------

  // Save debounce for the note textarea — fires on blur. Inline state
  // because the textarea binds two-way and we only want to commit on
  // explicit user action.
  let flagNoteDraft = $state('');
  $effect(() => {
    flagNoteDraft = node?.flag?.note ?? '';
  });

  async function patchActiveFlag(body: UpdateFlagBody): Promise<void> {
    if (!node?.flag) return;
    const flagId = node.flag.id;
    try {
      const updated = await patchFlag(flagId, body);
      if (node.flag && node.flag.id === flagId) {
        node.flag = { ...node.flag, ...updated };
      }
      void graphPoller.refresh();
    } catch (err) {
      toastStore.show(explainError(err, 'Flag update failed'), 'error');
    }
  }

  function onFlagStatusChange(e: Event): void {
    const value = (e.currentTarget as HTMLSelectElement).value as FlagStatus;
    void patchActiveFlag({ status: value });
  }

  function onFlagPriorityChange(e: Event): void {
    const value = Number((e.currentTarget as HTMLSelectElement).value);
    void patchActiveFlag({ priority: value });
  }

  function onFlagNoteBlur(): void {
    if ((node?.flag?.note ?? '') === flagNoteDraft) return;
    void patchActiveFlag({ note: flagNoteDraft || null });
  }

  async function removeFlag(): Promise<void> {
    if (!node) return;
    try {
      await clearNodeFlags(node.id);
      if (node) node.flag = null;
      void graphPoller.refresh();
    } catch (err) {
      toastStore.show(explainError(err, 'Flag removal failed'), 'error');
    }
  }

  // ---------------- Notes ----------------

  let noteDraft = $state('');
  let noteSaving = $state(false);

  async function saveNote(): Promise<void> {
    if (!node) return;
    const body = noteDraft.trim();
    if (!body) return;
    noteSaving = true;
    try {
      await addNodeNote(node.id, body);
      noteDraft = '';
      const res = await listNodeNotes(node.id);
      notes = res.notes;
    } catch (err) {
      toastStore.show(explainError(err, 'Save failed'), 'error');
    } finally {
      noteSaving = false;
    }
  }

  async function removeNote(id: number): Promise<void> {
    if (!node) return;
    try {
      await deleteNote(id);
      const res = await listNodeNotes(node.id);
      notes = res.notes;
    } catch (err) {
      toastStore.show(explainError(err, 'Delete failed'), 'error');
    }
  }

  // ---------------- Entity context menu ----------------

  let entityMenu = $state<{
    x: number;
    y: number;
    sections: MenuSection[];
  } | null>(null);
  let rootEl = $state<HTMLDivElement | null>(null);

  function openEntityMenu(e: MouseEvent, type: string, value: string): void {
    e.preventDefault();
    const sections = buildEntityMenu(type, value);
    // Coords relative to the positioned ancestor (the panel root). The
    // shared ContextMenu auto-flips off the parent edges.
    const parent = rootEl;
    if (!parent) return;
    const r = parent.getBoundingClientRect();
    entityMenu = {
      x: e.clientX - r.left,
      y: e.clientY - r.top,
      sections,
    };
  }
  function closeEntityMenu(): void {
    entityMenu = null;
  }

  // ---------------- Helpers ----------------

  // The spec's status dropdown is 4-valued (pending / investigating /
  // done / dismissed); the watchlist auto-flagger writes 'flagged', which
  // we fold into 'pending' for display. On save the user-picked value
  // wins, so 'flagged' is a one-way fold.
  function statusForSelect(s: FlagStatus): FlagStatus {
    return s === 'flagged' ? 'pending' : s;
  }

  function formatTimestamp(iso: string | null): string {
    if (!iso) return '';
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }

  // Gutter character for a diff line, mirroring a unified diff.
  function diffGutter(op: DiffOp): string {
    if (op === 'add') return '+';
    if (op === 'remove') return '−';
    if (op === 'hunk') return '';
    return ' ';
  }

  let responseHeaderEntries = $derived.by(() => {
    if (!node?.response_headers) return [] as [string, string][];
    return Object.entries(node.response_headers);
  });

  // Close the picker on outside click — the dropdown is non-modal.
  onMount(() => {
    function onDocPointerDown(e: PointerEvent) {
      if (!pickerOpen) return;
      const t = e.target;
      if (t instanceof Element && t.closest('.picker, .add-button')) return;
      closeCollectionPicker();
    }
    document.addEventListener('pointerdown', onDocPointerDown);
    return () => document.removeEventListener('pointerdown', onDocPointerDown);
  });
</script>

<div class="root" bind:this={rootEl}>
  {#if selectionStore.selectedNodeId === null}
    <EmptyState title="No node selected." />
  {:else if loading && !node}
    <EmptyState title="Loading…" />
  {:else if loadError}
    <EmptyState title={loadError} error />
  {:else if node}
    {@const uncrawled = isUncrawled(node)}

    <!-- Header block -->
    <header class="head">
      <a class="url" href={node.url} target="_blank" rel="noreferrer">
        {node.url}
      </a>
      {#if node.domain}
        <div class="alias-row">
          {#if aliasFromNode}
            <span class="alias">{aliasFromNode}</span>
          {:else}
            <span class="alias unset">no alias</span>
          {/if}
          <IconButton label="Rename alias" variant="ghost" size="small" onclick={openAliasPopover}>
            <Pencil size={11} />
          </IconButton>
        </div>
      {/if}
      {#if !uncrawled && node.title}
        <h2 class="title">{node.title}</h2>
      {/if}
      <div class="label-row">
        <LabelChips labelIds={node.label_ids} domainLabelIds={node.domain_label_ids} />
        <IconButton label="Labels" variant="ghost" size="small" onclick={openLabelPopover}>
          <Tag size={11} />
        </IconButton>
      </div>
      <div class="chips">
        {#if uncrawled}
          <span class="chip uncrawled">{stateLabel(node.state)}</span>
        {:else}
          {#if node.status_code !== null}
            <span class="chip">HTTP {node.status_code}</span>
          {/if}
          {#if node.category}
            <span class="chip">{node.category}</span>
          {/if}
        {/if}
        <button
          type="button"
          class="chip toggle"
          class:active={node.reviewed}
          onclick={toggleReviewed}
          aria-pressed={node.reviewed}
        >
          ✓ Reviewed
        </button>
        <button
          type="button"
          class="chip toggle"
          class:active={node.analysis_excluded}
          onclick={toggleExcluded}
          aria-pressed={node.analysis_excluded}
        >
          ⊘ Exclude
        </button>
      </div>
      {#if !uncrawled && node.summary}
        <p class="summary">{node.summary}</p>
      {/if}
    </header>

    <!-- Collections section -->
    <CollapsibleSection
      title="In collections"
      collapsed={sections.isCollapsed('collections')}
      onToggle={() => sections.toggle('collections')}
    >
      {#snippet actions()}
        <button
          type="button"
          class="add-button"
          onclick={() => (pickerOpen ? closeCollectionPicker() : openCollectionPicker())}
        >
          + Add
        </button>
      {/snippet}
      {#if collections.length === 0}
        <EmptyState title="Not in any collection." />
      {:else}
        <div class="pills">
          {#each collections as c (c.id)}
            <span class="pill">
              {c.name}
              <IconButton label="Remove from {c.name}" variant="ghost" size="small" onclick={() => removeFromCollection(c.id)}>
                <X size={10} />
              </IconButton>
            </span>
          {/each}
        </div>
      {/if}
      {#if pickerOpen}
        <div class="picker">
          {#if pickerLoading}
            <EmptyState title="Loading…" />
          {:else if pickerError}
            <EmptyState title={pickerError} error />
          {:else if (allCollectionsCache ?? []).length === 0}
            <EmptyState title="No collections yet." />
          {:else}
            {#each allCollectionsCache ?? [] as c (c.id)}
              {@const joined = collections.some((x) => x.id === c.id)}
              <button
                type="button"
                class="picker-row"
                class:joined
                disabled={joined}
                onclick={() => addToCollection(c)}
              >
                <span>{c.name}</span>
                {#if joined}<span class="check">✓</span>{/if}
              </button>
            {/each}
          {/if}
        </div>
      {/if}
    </CollapsibleSection>

    <!-- Flag section -->
    {#if node.flag}
      <CollapsibleSection
        title="Flag"
        collapsed={sections.isCollapsed('flag')}
        onToggle={() => sections.toggle('flag')}
      >
        {#snippet actions()}
          <button type="button" class="add-button danger" onclick={removeFlag}>
            Remove flag
          </button>
        {/snippet}
        <div class="flag-grid">
          <label>
            <span>Status</span>
            <select
              value={statusForSelect(node.flag.status)}
              onchange={onFlagStatusChange}
            >
              <option value="pending">pending</option>
              <option value="investigating">investigating</option>
              <option value="done">done</option>
              <option value="dismissed">dismissed</option>
            </select>
          </label>
          <label>
            <span>Priority</span>
            <select value={String(node.flag.priority)} onchange={onFlagPriorityChange}>
              <option value="1">High</option>
              <option value="2">Medium</option>
              <option value="3">Low</option>
            </select>
          </label>
        </div>
        <textarea
          class="flag-note"
          placeholder="Notes about this flag…"
          bind:value={flagNoteDraft}
          onblur={onFlagNoteBlur}
        ></textarea>
      </CollapsibleSection>
    {/if}

    <!-- Details toggle + expanded block (skipped for uncrawled) -->
    {#if !uncrawled}
      <button
        type="button"
        class="details-toggle"
        onclick={() => (detailsOpen = !detailsOpen)}
      >
        {detailsOpen ? '▾' : '▸'} Details
      </button>

      {#if detailsOpen}
        <!-- Entities -->
        {#if node.entities.length > 0}
          <CollapsibleSection
            title="Entities ({node.entities.length})"
            collapsed={sections.isCollapsed('entities')}
            onToggle={() => sections.toggle('entities')}
          >
            <div class="entities">
              {#each node.entities as e, i (i)}
                <button
                  type="button"
                  class="entity-row"
                  onclick={(ev) => openEntityMenu(ev, e.type, e.value)}
                  oncontextmenu={(ev) => openEntityMenu(ev, e.type, e.value)}
                >
                  <span class="entity-type">{e.type}</span>
                  <span class="entity-value">{e.value}</span>
                </button>
              {/each}
            </div>
          </CollapsibleSection>
        {/if}

        <!-- Response headers -->
        {#if responseHeaderEntries.length > 0}
          <CollapsibleSection
            title="Response Headers ({responseHeaderEntries.length})"
            collapsed={sections.isCollapsed('headers')}
            onToggle={() => sections.toggle('headers')}
          >
            <table class="headers">
              <tbody>
                {#each responseHeaderEntries as [k, v] (k)}
                  <tr>
                    <td class="hk">{k}</td>
                    <td class="hv">{v}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </CollapsibleSection>
        {/if}

        <!-- Versions — timeline + snapshot picker + diff (Phase 5) -->
        {#if node.history.length > 0}
          <CollapsibleSection
            title="Versions ({node.history.length})"
            collapsed={sections.isCollapsed('versions')}
            onToggle={() => sections.toggle('versions')}
          >

            <!-- Compare bar (only meaningful with two or more versions) -->
            {#if node.history.length >= 2}
              <div class="compare-bar">
                <select aria-label="Diff from version" bind:value={diffFrom}>
                  {#each node.history as v (v.id)}
                    <option value={v.id}>{formatTimestamp(v.fetched_at)}</option>
                  {/each}
                </select>
                <span class="arrow">→</span>
                <select aria-label="Diff to version" bind:value={diffTo}>
                  {#each node.history as v (v.id)}
                    <option value={v.id}>{formatTimestamp(v.fetched_at)}</option>
                  {/each}
                </select>
                <button
                  type="button"
                  class="add-button"
                  onclick={runDiff}
                  disabled={diffLoading || diffFrom === diffTo}
                >
                  {diffLoading ? '…' : 'Diff'}
                </button>
              </div>
            {/if}

            <!-- Timeline — newest first; click a row to pin its snapshot -->
            <ul class="timeline">
              {#each node.history as v (v.id)}
                {@const isCurrent = v.id === node.current_version_id}
                {@const isPinned = pinned?.id === v.id}
                <li>
                  <button
                    type="button"
                    class="ver-row"
                    class:active={isPinned}
                    onclick={() => viewVersion(v.id)}
                  >
                    <span class="ver-when">{formatTimestamp(v.fetched_at)}</span>
                    <span class="ver-meta">
                      {#if v.content_changed}
                        <span class="ver-dot" title="Content changed from previous version"></span>
                      {/if}
                      <span class="ver-status">{v.http_status ?? '—'}</span>
                      {#if isCurrent}<span class="ver-current">current</span>{/if}
                    </span>
                  </button>
                </li>
              {/each}
            </ul>

            <!-- Pinned snapshot (may lag the current version) -->
            {#if pinnedLoading}
              <EmptyState title="Loading snapshot…" />
            {:else if pinnedError}
              <EmptyState title={pinnedError} error />
            {:else if pinned}
              <div class="snapshot">
                <div class="snapshot-head">
                  <span class="block-label">
                    Snapshot · {formatTimestamp(pinned.fetched_at)}{pinned.id === node.current_version_id ? ' (current)' : ''}
                  </span>
                  <IconButton label="Close snapshot" variant="ghost" size="small" onclick={clearPinned}>
                    <X size={10} />
                  </IconButton>
                </div>
                {#if pinned.title}
                  <p class="snapshot-title">{pinned.title}</p>
                {/if}
                {#if pinned.body_text_clean}
                  <pre class="preview tall">{pinned.body_text_clean}</pre>
                {:else}
                  <p class="empty muted">No text captured for this version.</p>
                {/if}
              </div>
            {/if}

            <!-- Diff between two versions -->
            {#if diffError}
              <EmptyState title={diffError} error />
            {:else if diff}
              <div class="diffbox">
                <div class="snapshot-head">
                  <span class="block-label">
                    Diff · {formatTimestamp(diff.a.fetched_at)} → {formatTimestamp(diff.b.fetched_at)}
                  </span>
                  <IconButton label="Close diff" variant="ghost" size="small" onclick={clearDiff}>
                    <X size={10} />
                  </IconButton>
                </div>
                {#if diff.identical}
                  <p class="empty muted">No content changes between these versions.</p>
                {:else}
                  <p class="diff-stats">
                    <span class="add">+{diff.added}</span>
                    <span class="rem">−{diff.removed}</span>
                    {#if diff.truncated}<span class="muted">truncated</span>{/if}
                  </p>
                  <div class="difflines">
                    {#each diff.lines as ln, i (i)}
                      <div class="dl {ln.op}">
                        <span class="g">{diffGutter(ln.op)}</span><span class="t">{ln.text}</span>
                      </div>
                    {/each}
                  </div>
                {/if}
              </div>
            {/if}
          </CollapsibleSection>
        {/if}
      {/if}
    {/if}

    <!-- Notes (always shown, on uncrawled too) -->
    {#if !uncrawled ? detailsOpen : true}
      <CollapsibleSection
        title="Notes ({notes.length})"
        collapsed={sections.isCollapsed('notes')}
        onToggle={() => sections.toggle('notes')}
      >
        {#if notes.length > 0}
          <ul class="notes">
            {#each notes as n (n.id)}
              <li>
                <span class="note-body">{n.body}</span>
                <IconButton label="Delete note" variant="ghost" size="small" onclick={() => removeNote(n.id)}>
                  <X size={10} />
                </IconButton>
              </li>
            {/each}
          </ul>
        {/if}
        <textarea
          class="note-input"
          placeholder="Add a note…"
          bind:value={noteDraft}
        ></textarea>
        <button
          type="button"
          class="save-note"
          onclick={saveNote}
          disabled={!noteDraft.trim() || noteSaving}
        >
          Save note
        </button>
      </CollapsibleSection>
    {/if}
  {/if}

  {#if aliasPopover}
    {@const rename = aliasPopover}
    <RenameAliasPopover
      x={rename.x}
      y={rename.y}
      target={rename.target}
      currentName={rename.currentName}
      onClose={closeAliasPopover}
      onSave={(alias) => renameTarget(rename.target, alias)}
    />
  {/if}

  {#if labelPopover}
    {@const picker = labelPopover}
    <LabelPickerPopover
      x={picker.x}
      y={picker.y}
      target={picker.target}
      currentIds={picker.currentIds}
      onClose={() => (labelPopover = null)}
      onChanged={onLabelsChanged}
    />
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
    gap: 10px;
    font-size: 11px;
    color: var(--text);
  }
  /* Header */
  .head {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .url {
    font-size: 11px;
    color: var(--accent);
    word-break: break-all;
    text-decoration: none;
  }
  .url:hover {
    text-decoration: underline;
  }
  .alias-row {
    display: flex;
    align-items: center;
    gap: 4px;
    font-style: italic;
  }
  .alias {
    font-size: 11px;
    color: var(--muted);
  }
  .alias.unset {
    opacity: 0.6;
  }
  .label-row {
    display: flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;
    margin-top: 4px;
  }
  .title {
    margin: 2px 0 2px;
    font-size: 13px;
    font-weight: 400;
    color: var(--text);
    line-height: 1.3;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    align-items: center;
    margin-top: 4px;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    padding: 2px 6px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: transparent;
    color: var(--muted);
    font-size: 10px;
    cursor: default;
  }
  .chip.uncrawled {
    border-color: #b08a3a;
    color: #e0b860;
  }
  .chip.toggle {
    cursor: pointer;
  }
  .chip.toggle:hover {
    color: var(--text);
  }
  .chip.toggle.active {
    background: rgba(0, 212, 170, 0.15);
    border-color: var(--accent);
    color: var(--accent);
  }
  .summary {
    margin: 6px 0 0;
    color: var(--text);
    line-height: 1.4;
  }

  /* Blocks */
  .block-label {
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .add-button {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 2px;
    color: var(--muted);
    font-size: 10px;
    padding: 2px 6px;
    cursor: pointer;
  }
  .add-button:hover {
    color: var(--accent);
    border-color: var(--accent);
  }
  .add-button.danger:hover {
    color: #ff6b6b;
    border-color: #ff6b6b;
  }

  /* Pills */
  .pills {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 6px;
    border: 1px solid var(--accent);
    border-radius: 8px;
    background: rgba(0, 212, 170, 0.1);
    color: var(--accent);
    font-size: 10px;
  }
  /* Picker */
  .picker {
    display: flex;
    flex-direction: column;
    border: 1px solid var(--border);
    border-radius: 2px;
    background: rgba(10, 15, 13, 0.97);
    max-height: 180px;
    overflow-y: auto;
  }
  .picker-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 8px;
    background: transparent;
    border: none;
    color: var(--text);
    font-size: 11px;
    text-align: left;
    cursor: pointer;
  }
  .picker-row:hover:not(.joined) {
    background: rgba(0, 212, 170, 0.12);
  }
  .picker-row.joined {
    color: var(--muted);
    cursor: default;
  }
  .check {
    color: var(--accent);
  }

  /* Flag editor */
  .flag-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .flag-grid label {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 10px;
    color: var(--muted);
  }
  .flag-grid select,
  .flag-note {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 2px;
    color: var(--text);
    font: inherit;
    padding: 3px 5px;
  }
  .flag-grid select:focus,
  .flag-note:focus {
    border-color: var(--accent);
    outline: none;
  }
  .flag-note {
    min-height: 40px;
    resize: vertical;
  }

  /* Details toggle */
  .details-toggle {
    align-self: flex-start;
    background: transparent;
    border: none;
    color: var(--muted);
    font-size: 11px;
    cursor: pointer;
    padding: 4px 0;
  }
  .details-toggle:hover {
    color: var(--accent);
  }

  /* Version snapshot body text */
  .preview {
    margin: 0;
    padding: 6px 8px;
    background: rgba(0, 0, 0, 0.25);
    border-radius: 2px;
    color: var(--text);
    font-family: ui-monospace, monospace;
    font-size: 11px;
    line-height: 1.4;
    max-height: 80px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .preview.tall {
    max-height: 240px;
  }

  /* Versions — compare bar, timeline, snapshot, diff */
  .compare-bar {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .compare-bar select {
    flex: 1 1 0;
    min-width: 0;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 2px;
    color: var(--text);
    font: inherit;
    font-size: 10px;
    padding: 2px 4px;
  }
  .compare-bar select:focus {
    border-color: var(--accent);
    outline: none;
  }
  .compare-bar .arrow {
    color: var(--muted);
    flex: 0 0 auto;
  }
  .timeline {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    border: 1px solid var(--border);
    border-radius: 2px;
    max-height: 180px;
    overflow-y: auto;
  }
  .ver-row {
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    padding: 4px 6px;
    background: transparent;
    border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    color: var(--text);
    font-size: 11px;
    text-align: left;
    cursor: pointer;
  }
  .ver-row:last-child {
    border-bottom: none;
  }
  .ver-row:hover {
    background: rgba(0, 212, 170, 0.06);
  }
  .ver-row.active {
    background: rgba(0, 212, 170, 0.14);
  }
  .ver-when {
    font-family: ui-monospace, monospace;
    word-break: break-word;
  }
  .ver-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    flex: 0 0 auto;
    color: var(--muted);
    font-size: 10px;
  }
  .ver-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent);
  }
  .ver-current {
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .snapshot,
  .diffbox {
    display: flex;
    flex-direction: column;
    gap: 4px;
    border: 1px solid var(--border);
    border-radius: 2px;
    padding: 6px;
    background: rgba(0, 0, 0, 0.2);
  }
  .snapshot-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .snapshot-title {
    margin: 0;
    color: var(--text);
    font-size: 12px;
    line-height: 1.3;
  }
  .muted {
    color: var(--muted);
  }
  .diff-stats {
    margin: 0;
    display: flex;
    gap: 8px;
    font-family: ui-monospace, monospace;
    font-size: 10px;
  }
  .diff-stats .add {
    color: var(--accent);
  }
  .diff-stats .rem {
    color: #ff6b6b;
  }
  .difflines {
    max-height: 280px;
    overflow: auto;
    font-family: ui-monospace, monospace;
    font-size: 11px;
    line-height: 1.35;
  }
  .dl {
    display: flex;
    gap: 6px;
    padding: 0 2px;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .dl .g {
    flex: 0 0 0.8em;
    text-align: center;
    color: var(--muted);
    user-select: none;
  }
  .dl .t {
    flex: 1 1 auto;
  }
  .dl.add {
    background: rgba(0, 212, 170, 0.12);
  }
  .dl.add .g {
    color: var(--accent);
  }
  .dl.remove {
    background: rgba(255, 107, 107, 0.12);
  }
  .dl.remove .g {
    color: #ff6b6b;
  }
  .dl.hunk {
    color: var(--muted);
    margin-top: 4px;
  }
  .dl.context {
    color: var(--text);
  }

  /* Entities */
  .entities {
    display: flex;
    flex-direction: column;
  }
  .entity-row {
    display: flex;
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
  .entity-type {
    flex: 0 0 64px;
    color: var(--muted);
    text-transform: lowercase;
    font-size: 10px;
  }
  .entity-value {
    font-family: ui-monospace, monospace;
    word-break: break-all;
  }

  /* Headers + versions tables */
  .headers {
    width: 100%;
    border-collapse: collapse;
    margin-top: 4px;
  }
  .headers td {
    padding: 2px 4px;
    font-family: ui-monospace, monospace;
    font-size: 11px;
    vertical-align: top;
  }
  .hk {
    color: var(--accent);
    white-space: nowrap;
  }
  .hv {
    color: var(--muted);
    word-break: break-all;
  }

  /* Notes */
  .notes {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .notes li {
    display: flex;
    justify-content: space-between;
    gap: 6px;
    padding: 4px 6px;
    background: rgba(0, 0, 0, 0.2);
    border-radius: 2px;
  }
  .note-body {
    flex: 1;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .note-input {
    width: 100%;
    box-sizing: border-box;
    min-height: 40px;
    padding: 4px 6px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 2px;
    color: var(--text);
    font: inherit;
    resize: vertical;
  }
  .note-input:focus {
    border-color: var(--accent);
    outline: none;
  }
  .save-note {
    align-self: flex-start;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 2px;
    color: var(--muted);
    font-size: 11px;
    padding: 3px 8px;
    cursor: pointer;
  }
  .save-note:not(:disabled):hover {
    color: var(--accent);
    border-color: var(--accent);
  }
  .save-note:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
