<script lang="ts">
  // Right pane shell. Two top-level branches drive what renders:
  //
  //   - selectionStore.selectMode === 'cluster'  → cluster workspace
  //     (Nodes / Q&A / Common). The normal tab bar is hidden.
  //   - otherwise                                → normal three-tab
  //     view (Page / Domain / Analysis), keyed by navigationStore.rightTab.
  //
  // The cluster trigger gates on selectMode, not selectedIds.size, so
  // multi-highlight surfaces (bottom-pane Domains row) never trip the
  // workspace. The store's mode rules guarantee cluster mode drops back
  // to 'highlight' the moment the count drops to 1, so the panel snaps
  // back to its single-node view automatically.

  import { ChevronLeft, ChevronRight } from 'lucide-svelte';
  import { navigationStore, type RightTab } from '$lib/stores/navigation.svelte';
  import { layoutStore } from '$lib/stores/layout.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import ActionBar from './right/ActionBar.svelte';
  import { IconButton, PaneTabs } from '$lib/ui';
  import AnalysisTab from './right/AnalysisTab.svelte';
  import DomainTab from './right/DomainTab.svelte';
  import PageTab from './right/PageTab.svelte';
  import PreviewTab from './right/PreviewTab.svelte';
  import CommonTab from './right/cluster/CommonTab.svelte';
  import NodesTab from './right/cluster/NodesTab.svelte';
  import QnATab from './right/cluster/QnATab.svelte';

  const tabs: { id: RightTab; label: string }[] = [
    { id: 'page', label: 'Page' },
    { id: 'preview', label: 'Preview' },
    { id: 'domain', label: 'Domain' },
    { id: 'analysis', label: 'Analysis' },
  ];

  type ClusterTab = 'nodes' | 'qna' | 'common';
  const clusterTabs: { id: ClusterTab; label: string }[] = [
    { id: 'nodes', label: 'Nodes' },
    { id: 'qna', label: 'Q&A' },
    { id: 'common', label: 'Common' },
  ];
  let clusterTab = $state<ClusterTab>('nodes');

  // F6 — auto-expand the panel whenever a new node is selected, unless
  // the analyst explicitly collapsed the panel this session. The store
  // guards the suppression flag internally so this can fire blindly.
  $effect(() => {
    if (selectionStore.selectedNodeId !== null) {
      layoutStore.expandRightForSelection();
    }
  });

  // Snap the cluster tab back to Nodes whenever a fresh cluster opens.
  // Without this, re-entering cluster mode after a clear would keep the
  // analyst on whichever cluster tab they last viewed — disorienting
  // when the selection content is different.
  let inCluster = $derived(selectionStore.selectMode === 'cluster');
  let wasInCluster = $state(false);
  $effect(() => {
    if (inCluster && !wasInCluster) clusterTab = 'nodes';
    wasInCluster = inCluster;
  });
</script>

{#if layoutStore.rightCollapsed}
  <aside class="collapsed" aria-label="Right panel (collapsed)">
    <IconButton
      label="Expand right panel"
      variant="subtle"
      onclick={() => layoutStore.expandRight()}
    >
      <ChevronLeft size={14} />
    </IconButton>
    <span class="vlabel">Detail</span>
  </aside>
{:else}
  <aside class="panel">
    {#if !inCluster}
      <ActionBar />
    {/if}
    <header class="head">
      {#if inCluster}
        <PaneTabs
          tabs={clusterTabs}
          active={clusterTab}
          onSelect={(id) => (clusterTab = id as typeof clusterTab)}
          ariaLabel="Cluster workspace"
        />
      {:else}
        <PaneTabs
          tabs={tabs}
          active={navigationStore.rightTab}
          onSelect={(id) => navigationStore.setRight(id as RightTab)}
          ariaLabel="Right pane"
        />
      {/if}
      <div class="collapse">
        <IconButton
          label="Collapse right panel"
          variant="subtle"
          onclick={() => layoutStore.collapseRight()}
        >
          <ChevronRight size={14} />
        </IconButton>
      </div>
    </header>
    <div class="body">
      {#if inCluster}
        {#if clusterTab === 'nodes'}
          <NodesTab />
        {:else if clusterTab === 'qna'}
          <QnATab />
        {:else}
          <CommonTab />
        {/if}
      {:else if navigationStore.rightTab === 'page'}
        <PageTab />
      {:else if navigationStore.rightTab === 'preview'}
        <PreviewTab />
      {:else if navigationStore.rightTab === 'domain'}
        <DomainTab />
      {:else if navigationStore.rightTab === 'analysis'}
        <AnalysisTab />
      {/if}
    </div>
  </aside>
{/if}

<style>
  .panel,
  .collapsed {
    display: flex;
    flex-direction: column;
    height: 100%;
    border-left: 1px solid var(--border);
    overflow: hidden;
  }
  .collapsed {
    align-items: center;
    padding: 6px 0;
    gap: 8px;
    width: 24px;
  }
  .vlabel {
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  .head {
    display: flex;
    align-items: flex-end;
    border-bottom: 1px solid var(--border);
    height: 30px;
  }
  .collapse {
    display: flex;
    align-items: center;
    padding: 0 6px 2px;
  }
  .body {
    flex: 1;
    padding: 12px;
    overflow: auto;
  }
</style>
