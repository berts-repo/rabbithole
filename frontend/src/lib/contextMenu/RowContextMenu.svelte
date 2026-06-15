<script lang="ts">
  // Single-mount renderer for the shared row right-click menu. Any row
  // surface (bottom-pane sub-tabs, the Search tab) writes to
  // `rowContextMenu` via openAt(); this component subscribes and renders
  // the shared $lib/contextMenu/ContextMenu in a fixed overlay so the menu
  // can escape a pane's `overflow: auto` and so x/y land in viewport coords
  // directly (no parent-coord math). Mounted once in AppShell.
  //
  // What lives here:
  //   - Menu state (via the store).
  //   - Rename / Add Monitor / Add to Collection modals — the same generic
  //     popovers and modals GraphCanvas uses, but with their own mount
  //     points so the row menu can open them without coupling to
  //     GraphCanvas's activeModal.
  //   - Handler factory that turns the row target into the
  //     SingleTargetMenuHandlers the shared builder consumes. id-bound
  //     actions resolve a node id on demand: an existing node, a known id,
  //     or — for a URL-only row (an uncrawled Search result, a Bookmark
  //     that hasn't been crawled) — a freshly-minted stub. Stubs are
  //     created only when the analyst actually invokes an id-bound action,
  //     never speculatively, so the graph isn't polluted with every row.

  import { servicesStore } from '$lib/stores/services.svelte';
  import { graphPoller } from '$lib/pollers/graph.svelte';
  import ContextMenu from '$lib/contextMenu/ContextMenu.svelte';
  import {
    buildSingleTargetSections,
    type MenuSection,
    type SingleTargetMenuHandlers,
  } from '$lib/contextMenu';
  import {
    actAddToGraph,
    actCopyUrl,
    actFlag,
    actHideFromGraph,
    actOpenInTor,
    actQueueCrawl,
    actRemoveFlag,
    actSaveSeedBookmark,
    actToggleReviewed,
    explainApiError,
    labelPickerModal,
    queueAnalysisIds,
    renameModal,
    renameTarget,
    type LabelPickerModal,
    type RenameModal,
  } from '$lib/contextMenu/actions';
  import LabelPickerPopover from '../../components/labels/LabelPickerPopover.svelte';
  import { createStubNode } from '$lib/api';
  import { graphStore } from '$lib/stores/graph.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { workspaceSnapshots } from '$lib/stores/workspaceSnapshots.svelte';
  import RenameAliasPopover from '../../components/graph/RenameAliasPopover.svelte';
  import AddMonitorModal from '../../components/modals/AddMonitorModal.svelte';
  import CollectionPickerModal from '../../components/modals/CollectionPickerModal.svelte';
  import { rowContextMenu, type RowMenuTarget } from './rowMenu.svelte';

  // Modal state lives here rather than on the menu store — the modal
  // typically opens *after* the menu closes (the menu item activate
  // path closes the menu before invoking onSelect), so the two are
  // independent open-states.
  type ActiveModal =
    | RenameModal
    | LabelPickerModal
    | { kind: 'monitor'; url: string }
    | { kind: 'collection'; ids: number[] }
    | null;
  let activeModal = $state<ActiveModal>(null);

  // Resolve the target to a node id for id-bound actions. A row that
  // already maps to a node (or carries a known id) resolves instantly; a
  // URL-only row mints a stub on first use so Open in Tor / Flag / Queue
  // Analysis / Add to Collection all work without a prior crawl. On stub
  // failure the user sees a toast and the action no-ops (returns null).
  async function ensureNodeId(t: RowMenuTarget): Promise<number | null> {
    if (t.node) return t.node.id;
    if (t.nodeId != null) return t.nodeId;
    try {
      const { id } = await createStubNode({ url: t.url });
      // A minted stub changes the node set — drop the SWR payload cache so
      // the next graph tab switch can't re-apply a snapshot that predates
      // it (mirrors actHideFromGraph / actAddToGraph).
      workspaceSnapshots.invalidatePayloads();
      void graphPoller.refresh();
      return id;
    } catch (err) {
      toastStore.show(explainApiError(err, 'Action failed'), 'error');
      return null;
    }
  }

  function makeHandlers(target: RowMenuTarget): SingleTargetMenuHandlers {
    const node = target.node;
    return {
      copyUrl: () => actCopyUrl(target.url),
      openInTor: async () => {
        const id = await ensureNodeId(target);
        if (id != null) await actOpenInTor(id);
      },
      queueCrawl: () => actQueueCrawl(target.url),
      saveSeedBookmark: () => actSaveSeedBookmark(target.url),
      flag: async (priority) => {
        const id = await ensureNodeId(target);
        if (id != null) await actFlag(id, priority);
      },
      removeFlag: async () => {
        const id = await ensureNodeId(target);
        if (id != null) await actRemoveFlag(id);
      },
      toggleReviewed: async () => {
        const id = await ensureNodeId(target);
        if (id != null) await actToggleReviewed(id, !!node?.reviewed);
      },
      addMonitor: () => {
        activeModal = { kind: 'monitor', url: target.url };
      },
      renameAlias: () => {
        if (!node?.domain) {
          toastStore.show('Rename alias needs a domain.', 'warn');
          return;
        }
        const open = rowContextMenu.current;
        if (!open) return;
        // Anchor the popover at the right-click coords so it lands near
        // the row the analyst aimed at, matching how the graph's popover
        // anchors at the node's viewport position.
        activeModal = renameModal(
          { kind: 'domain', host: node.domain },
          { x: open.x, y: open.y },
          node.alias ?? null,
        );
      },
      applyLabels: async () => {
        const open = rowContextMenu.current;
        if (!open) return;
        const id = await ensureNodeId(target);
        if (id == null) return;
        activeModal = labelPickerModal(
          { kind: 'resource', resourceId: id, name: node?.label ?? target.url },
          { x: open.x, y: open.y },
          node?.label_ids ?? [],
        );
      },
      queueAnalysis: async () => {
        const id = await ensureNodeId(target);
        if (id != null) queueAnalysisIds([id], 'Row');
      },
      addToCollection: async () => {
        const id = await ensureNodeId(target);
        if (id != null) activeModal = { kind: 'collection', ids: [id] };
      },
      focus: async () => {
        const id = await ensureNodeId(target);
        if (id == null) return;
        // Ego-focus is graph state — opening it here drives the graph
        // canvas's reducers via the shared store. The canvas refreshes
        // on the store change.
        const current = graphStore.egoFocus;
        graphStore.setEgoFocus({ nodeId: id, depth: current?.depth ?? 2 });
        selectionStore.highlight(id);
      },
      hideFromGraph: () => actHideFromGraph(target.url),
      addToGraph: () => actAddToGraph(target.url),
      removeFromCollection: target.onRemoveFromCollection,
    };
  }

  const sections = $derived.by<MenuSection[] | null>(() => {
    const open = rowContextMenu.current;
    if (!open) return null;
    return buildSingleTargetSections(
      // The builder reads stub / flag_status / reviewed / domain off the
      // target. For a no-node row those flags read as undefined which is
      // fine — Hide-from-Graph stays enabled (URL-based), Flag defaults
      // to the "set" branch, and the id-bound handlers mint a stub on use.
      open.target.node ?? { domain: null },
      {
        torArmed: servicesStore.killSwitch.phase === 'armed',
        inCollection: !!open.target.inCollection,
        capabilities: open.target.capabilities,
      },
      makeHandlers(open.target),
    );
  });

</script>

{#if rowContextMenu.current && sections}
  <div class="layer">
    <ContextMenu
      sections={sections}
      x={rowContextMenu.current.x}
      y={rowContextMenu.current.y}
      onClose={() => rowContextMenu.close()}
    />
  </div>
{/if}

{#if activeModal?.kind === 'rename'}
  {@const rename = activeModal}
  <RenameAliasPopover
    x={rename.x}
    y={rename.y}
    target={rename.target}
    currentName={rename.currentName}
    onClose={() => (activeModal = null)}
    onSave={(alias) => renameTarget(rename.target, alias)}
  />
{/if}

{#if activeModal?.kind === 'labelPicker'}
  {@const picker = activeModal}
  <LabelPickerPopover
    x={picker.x}
    y={picker.y}
    target={picker.target}
    currentIds={picker.currentIds}
    onClose={() => (activeModal = null)}
    onChanged={() => void graphPoller.refresh()}
  />
{/if}

{#if activeModal?.kind === 'monitor'}
  <AddMonitorModal url={activeModal.url} onClose={() => (activeModal = null)} />
{/if}

{#if activeModal?.kind === 'collection'}
  <CollectionPickerModal
    nodeIds={activeModal.ids}
    onClose={() => (activeModal = null)}
  />
{/if}

<style>
  .layer {
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: 100;
  }
  .layer :global(.menu) {
    pointer-events: auto;
  }
</style>
