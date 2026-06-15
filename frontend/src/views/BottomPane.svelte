<script lang="ts">
  import { ChevronDown, ChevronUp } from 'lucide-svelte';
  import { workspaceStore, isBottomTab } from '$lib/stores/workspace.svelte';
  import { layoutStore } from '$lib/stores/layout.svelte';
  import { statsPoller } from '$lib/pollers/stats.svelte';
  import { IconButton, PaneTabs } from '$lib/ui';
  import ActivityTab from './bottom/ActivityTab.svelte';
  import AnalyzedTab from './bottom/AnalyzedTab.svelte';
  import BookmarksTab from './bottom/BookmarksTab.svelte';
  import BottomTabsMenu from './bottom/BottomTabsMenu.svelte';
  import CollectionTab from './bottom/CollectionTab.svelte';
  import DomainsTab from './bottom/DomainsTab.svelte';
  import FindResultsTab from './bottom/FindResultsTab.svelte';
  import FingerprintsTab from './bottom/FingerprintsTab.svelte';
  import FlagsTab from './bottom/FlagsTab.svelte';
  import InventoryTab from './bottom/InventoryTab.svelte';
  import LabelsTab from './bottom/LabelsTab.svelte';
  import LiveCrawlTab from './bottom/LiveCrawlTab.svelte';
  import MonitorsTab from './bottom/MonitorsTab.svelte';
  import ScheduledCrawlsTab from './bottom/ScheduledCrawlsTab.svelte';

  // Flags and Monitors carry a project-wide count chip, sourced from the
  // shared /api/stats poll. These two lists are project-scoped, so a
  // project-level count belongs here — unlike the workspace-scoped
  // domain/page totals on the graph tab bar. The badge stays hidden until
  // the poll lands and whenever a count is zero (falsy → not rendered).
  const tabs = $derived(
    workspaceStore.visibleTabDefs.map((t) => {
      if (t.id === 'flags') return { ...t, badge: statsPoller.data?.flags || undefined };
      if (t.id === 'monitors') return { ...t, badge: statsPoller.data?.monitors || undefined };
      return t;
    }),
  );
</script>

{#if layoutStore.bottomCollapsed}
  <section class="collapsed" aria-label="Bottom pane (collapsed)">
    <IconButton
      label="Expand bottom pane"
      variant="subtle"
      onclick={() => layoutStore.expandBottom()}
    >
      <ChevronUp size={14} />
    </IconButton>
    <span class="hlabel">Lists</span>
  </section>
{:else}
  <section class="bottom">
    <header class="head">
      <PaneTabs
        {tabs}
        active={workspaceStore.bottomTab}
        onSelect={(id) => {
          if (isBottomTab(id)) workspaceStore.setBottom(id);
        }}
        ariaLabel="Bottom pane tabs"
      />
      <BottomTabsMenu />
      <div class="collapse">
        <IconButton
          label="Collapse bottom pane"
          variant="subtle"
          onclick={() => layoutStore.collapseBottom()}
        >
          <ChevronDown size={14} />
        </IconButton>
      </div>
    </header>
    <div class="body">
      {#if workspaceStore.bottomTab === 'bookmarks'}
        <BookmarksTab />
      {:else if workspaceStore.bottomTab === 'collection'}
        <CollectionTab />
      {:else if workspaceStore.bottomTab === 'activity'}
        <ActivityTab />
      {:else if workspaceStore.bottomTab === 'scheduled_crawls'}
        <ScheduledCrawlsTab />
      {:else if workspaceStore.bottomTab === 'monitors'}
        <MonitorsTab />
      {:else if workspaceStore.bottomTab === 'inventory'}
        <InventoryTab />
      {:else if workspaceStore.bottomTab === 'domains'}
        <DomainsTab />
      {:else if workspaceStore.bottomTab === 'fingerprints'}
        <FingerprintsTab />
      {:else if workspaceStore.bottomTab === 'flags'}
        <FlagsTab />
      {:else if workspaceStore.bottomTab === 'labels'}
        <LabelsTab />
      {:else if workspaceStore.bottomTab === 'analyzed'}
        <AnalyzedTab />
      {:else if workspaceStore.bottomTab === 'live_crawl'}
        <LiveCrawlTab />
      {:else if workspaceStore.bottomTab === 'find'}
        <FindResultsTab />
      {/if}
    </div>
  </section>
{/if}

<style>
  .bottom,
  .collapsed {
    display: flex;
    flex-direction: column;
    height: 100%;
    border-top: 1px solid var(--border);
    overflow: hidden;
  }
  .collapsed {
    flex-direction: row;
    align-items: center;
    gap: 8px;
    padding: 0 8px;
  }
  .hlabel {
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  .head {
    display: flex;
    align-items: stretch;
    gap: 4px;
    height: 31px;
    padding-right: 4px;
    border-bottom: 1px solid var(--border);
  }
  .collapse {
    display: flex;
    align-items: center;
    padding: 0 2px;
  }
  .body {
    flex: 1;
    padding: 12px;
    overflow: auto;
  }
</style>
