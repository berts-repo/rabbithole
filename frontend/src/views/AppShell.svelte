<script lang="ts">
  import AppHeader from '../components/AppHeader.svelte';
  import KillSwitchAlert from '../components/KillSwitchAlert.svelte';
  import Toast from '../components/Toast.svelte';
  import PaneSplitter from '../components/PaneSplitter.svelte';
  import ProjectPickerModal from '../components/ProjectPickerModal.svelte';
  import SettingsModal from '../components/modals/SettingsModal.svelte';
  import RowContextMenu from '$lib/contextMenu/RowContextMenu.svelte';
  import LeftSidebar from './LeftSidebar.svelte';
  import RightPanel from './RightPanel.svelte';
  import BottomPane from './BottomPane.svelte';
  import GraphTab from './GraphTab.svelte';
  import SearchTab from './SearchTab.svelte';
  import { layoutStore } from '$lib/stores/layout.svelte';
  import { workspaceStore } from '$lib/stores/workspace.svelte';
  import { projectsStore } from '$lib/stores/projects.svelte';

  let settingsOpen = $state(false);
  let projectPickerOpen = $state(false);

  function onResize() {
    layoutStore.reclamp();
  }

  // Recompute the bottom-pane max when the viewport shrinks. Vertical
  // pane already clamps on every drag, but the saved value can outgrow
  // 60% of the new height after a window resize.
  $effect(() => {
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  });

  // Auto-open when there's no active project (initial-load case from
  // app-shell.md). Manual-open via the header chip uses projectPickerOpen.
  const showProjectPicker = $derived(
    projectPickerOpen || (projectsStore.activeId === null && !projectsStore.loading),
  );

  const leftPx = $derived(`${layoutStore.leftEffective}px`);
  const rightPx = $derived(`${layoutStore.rightEffective}px`);
  const bottomPx = $derived(`${layoutStore.bottomEffective}px`);
</script>

<div
  class="shell"
  style:--left-w={leftPx}
  style:--right-w={rightPx}
  style:--bottom-h={bottomPx}
>
  <AppHeader
    onOpenSettings={() => (settingsOpen = true)}
    onOpenProjects={() => (projectPickerOpen = true)}
  />
  <div class="main">
    <LeftSidebar onOpenSettings={() => (settingsOpen = true)} />
    <div class="left-splitter-slot" class:hidden={layoutStore.leftCollapsed}>
      <PaneSplitter
        axis="col"
        label="Resize left sidebar"
        onDrag={(d) => layoutStore.setLeftLive(layoutStore.left + d)}
        onCommit={() => layoutStore.commitLeft()}
      />
    </div>

    <div class="center">
      {#if workspaceStore.centerTab === 'search'}
        <SearchTab />
      {:else}
        <GraphTab />
      {/if}
    </div>

    <div class="right-splitter-slot" class:hidden={layoutStore.rightCollapsed}>
      <PaneSplitter
        axis="col"
        label="Resize right panel"
        onDrag={(d) => layoutStore.setRightLive(layoutStore.right - d)}
        onCommit={() => layoutStore.commitRight()}
      />
    </div>
    <div class="right-slot"><RightPanel /></div>
  </div>

  <div class="bottom-splitter-slot" class:hidden={layoutStore.bottomCollapsed}>
    <PaneSplitter
      axis="row"
      label="Resize bottom pane"
      onDrag={(d) => layoutStore.setBottomLive(layoutStore.bottom - d)}
      onCommit={() => layoutStore.commitBottom()}
    />
  </div>

  <div class="bottom">
    <BottomPane />
  </div>
</div>

{#if showProjectPicker}
  <ProjectPickerModal onClose={() => (projectPickerOpen = false)} />
{/if}

{#if settingsOpen}
  <SettingsModal onClose={() => (settingsOpen = false)} />
{/if}

<!-- Shared row right-click menu — every row surface (bottom-pane sub-tabs,
     the Search tab) opens it via `rowContextMenu.openAt(target, event)`.
     Mounted once at the shell so it survives a surface unmounting and its
     fixed overlay escapes every pane's overflow. -->
<RowContextMenu />

<KillSwitchAlert />

<Toast />

<style>
  .shell {
    /* Row tracks: header · main · bottom-splitter · bottom. Every child
       below is unconditionally rendered, so the track count is fixed —
       do not add a conditionally-rendered direct child here without
       also giving it a permanent slot, or the rows shift. */
    display: grid;
    grid-template-rows: auto 1fr auto var(--bottom-h);
    height: 100vh;
    width: 100vw;
    overflow: hidden;
  }
  .main {
    display: grid;
    grid-template-columns: var(--left-w) auto 1fr auto var(--right-w);
    min-height: 0;
    overflow: hidden;
  }
  .center {
    min-width: 0;
    overflow: hidden;
    position: relative;
  }
  .bottom {
    min-height: 0;
    overflow: hidden;
  }
  .left-splitter-slot,
  .right-splitter-slot {
    /* Keeps the splitter in its grid column so the panes always land in
       the right slot. When collapsed, hide the splitter visually but keep
       the slot in place — the `auto` column shrinks to 0. */
    display: flex;
    align-items: stretch;
    justify-content: center;
  }
  .left-splitter-slot.hidden,
  .right-splitter-slot.hidden {
    visibility: hidden;
    width: 0;
    overflow: hidden;
  }
  .bottom-splitter-slot {
    display: flex;
    justify-content: stretch;
  }
  .bottom-splitter-slot.hidden {
    visibility: hidden;
    height: 0;
    overflow: hidden;
  }
  .right-slot {
    min-width: 0;
    overflow: hidden;
  }
</style>
