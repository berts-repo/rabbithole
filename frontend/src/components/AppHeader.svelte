<script lang="ts">
  import { Folder, Settings as SettingsIcon } from 'lucide-svelte';
  import TorPill from './TorPill.svelte';
  import KillSwitchToggle from './KillSwitchToggle.svelte';
  import { workspaceStore, type CenterTab } from '$lib/stores/workspace.svelte';
  import { projectsStore } from '$lib/stores/projects.svelte';

  type Props = { onOpenSettings: () => void; onOpenProjects: () => void };
  const { onOpenSettings, onOpenProjects }: Props = $props();

  const activeName = $derived(
    projectsStore.projects.find((p) => p.id === projectsStore.activeId)?.name ?? '—',
  );

  const tabs: { id: CenterTab; label: string }[] = [
    { id: 'search', label: 'Search' },
    { id: 'explore', label: 'Explore' },
  ];

  // TODO(F5): badge once graph.* settings exist + non-default detection.
</script>

<header class="header">
  <button
    type="button"
    class="project"
    title="Switch project"
    onclick={onOpenProjects}
  >
    <Folder size={13} />
    <span>{activeName}</span>
  </button>

  <nav class="tabs" aria-label="Primary">
    {#each tabs as tab (tab.id)}
      <button
        type="button"
        class="tab"
        class:active={workspaceStore.centerTab === tab.id}
        onclick={() => workspaceStore.setCenter(tab.id)}
      >
        {tab.label}
      </button>
    {/each}
  </nav>

  <div class="spacer"></div>

  <button
    type="button"
    class="gear"
    aria-label="Settings"
    title="Settings"
    onclick={onOpenSettings}
  >
    <SettingsIcon size={16} />
  </button>

  <TorPill />
  <KillSwitchToggle />
</header>

<style>
  .header {
    display: flex;
    align-items: stretch;
    gap: 8px;
    padding: 0 8px;
    border-bottom: 1px solid var(--border);
    background: var(--bg);
    height: 40px;
  }
  .tabs {
    display: flex;
    align-items: stretch;
    gap: 0;
  }
  .tab {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: var(--muted);
    padding: 0 14px;
    font-size: 13px;
    cursor: pointer;
  }
  .tab:hover {
    color: var(--text);
  }
  .tab.active {
    color: var(--accent);
    border-bottom-color: var(--accent);
    background: var(--accent-bg-subtle);
  }
  .spacer {
    flex: 1;
  }
  .gear {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    cursor: pointer;
    padding: 0 8px;
    border-radius: 2px;
    display: inline-flex;
    align-items: center;
    align-self: center;
    height: 26px;
  }
  .gear:hover {
    color: var(--accent);
    border-color: var(--accent);
  }
  .header :global(.pill),
  .header :global(.ks) {
    align-self: center;
  }
  .project {
    display: inline-flex;
    align-items: center;
    align-self: center;
    gap: 6px;
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 0 10px;
    height: 26px;
    border-radius: 2px;
    cursor: pointer;
    font-size: 12px;
    max-width: 180px;
  }
  .project span {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .project:hover {
    color: var(--accent);
    border-color: var(--accent);
  }
</style>
