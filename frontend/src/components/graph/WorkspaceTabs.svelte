<script lang="ts">
  // Tab bar above the graph toolbar. Renders openTabs from the
  // workspace store; '+' toggles the inline WorkspacePicker popover.
  // Global cannot close (no ✕). Active tab gets aria-current="page".

  import { Plus, X } from 'lucide-svelte';
  import { workspaceStore } from '$lib/stores/workspace.svelte';
  import { IconButton } from '$lib/ui';
  import WorkspacePicker from './WorkspacePicker.svelte';

  let pickerOpen = $state(false);
</script>

<nav class="bar" aria-label="Workspace tabs">
  <div class="tabs">
    {#each workspaceStore.openTabs as tab (tab.id)}
      {@const active = workspaceStore.activeWorkspaceId === tab.id}
      <div class="tab" class:active aria-current={active ? 'page' : undefined}>
        <button
          type="button"
          class="label"
          onclick={() => workspaceStore.setWorkspace(tab.id)}
        >
          {tab.label}
        </button>
        {#if tab.kind !== 'global'}
          <button
            type="button"
            class="close"
            aria-label={`Close ${tab.label}`}
            onclick={() => workspaceStore.closeTab(tab.id)}
          >
            <X size={12} />
          </button>
        {/if}
      </div>
    {/each}
    <div class="add">
      <IconButton
        label="Open collection workspace"
        variant="subtle"
        expanded={pickerOpen}
        onclick={() => (pickerOpen = !pickerOpen)}
      >
        <Plus size={14} />
      </IconButton>
      {#if pickerOpen}
        <WorkspacePicker onClose={() => (pickerOpen = false)} />
      {/if}
    </div>
  </div>
</nav>

<style>
  .bar {
    display: flex;
    align-items: flex-end;
    height: 30px;
    border-bottom: 1px solid var(--border);
    background: var(--bg);
    position: relative;
    padding: 0 4px;
  }
  .tabs {
    display: flex;
    align-items: flex-end;
    flex: 1;
    gap: 2px;
    min-width: 0;
  }
  .tab {
    display: inline-flex;
    align-items: center;
    height: 26px;
    background: transparent;
    border: 1px solid transparent;
    border-bottom: none;
    border-radius: 6px 6px 0 0;
    color: var(--muted);
    font-size: 11px;
    white-space: nowrap;
    position: relative;
  }
  .tab:hover {
    background: rgba(255, 255, 255, 0.03);
    color: var(--text);
  }
  .tab.active {
    background: var(--bg);
    border-color: var(--border);
    color: var(--accent);
    margin-bottom: -1px;
    padding-bottom: 1px;
    z-index: 1;
  }
  .tab.active:hover {
    background: var(--bg);
    color: var(--accent);
  }
  .tab .label {
    background: transparent;
    border: none;
    color: inherit;
    cursor: pointer;
    padding: 0 10px;
    height: 100%;
    font: inherit;
  }
  .close {
    background: transparent;
    border: none;
    color: inherit;
    cursor: pointer;
    padding: 2px;
    margin-right: 4px;
    height: 18px;
    width: 18px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    opacity: 0.6;
    border-radius: 3px;
  }
  .close:hover {
    opacity: 1;
    background: rgba(255, 255, 255, 0.08);
  }
  .add {
    position: relative;
    display: inline-flex;
    align-items: center;
    height: 26px;
    margin-left: 2px;
  }
</style>
