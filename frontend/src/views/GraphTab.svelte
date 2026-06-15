<script lang="ts">
  // Centre column of the Explore tab. Starts/stops the /api/graph
  // poller for as long as the tab is mounted, owns the toolbar's
  // volatile pause/fit/reset state (per the F4a plan, persistence to
  // settings.graph.* lands in F4b), and composes the canvas + toolbar.

  import { onMount, untrack } from 'svelte';
  import GraphCanvas from '../components/graph/GraphCanvas.svelte';
  import GraphToolbar from '../components/graph/GraphToolbar.svelte';
  import WorkspaceTabs from '../components/graph/WorkspaceTabs.svelte';
  import { graphPoller } from '$lib/pollers/graph.svelte';
  import { workspaceStore } from '$lib/stores/workspace.svelte';
  import { workspaceSnapshots } from '$lib/stores/workspaceSnapshots.svelte';

  // Monotonic tokens so the canvas can $effect on them — the canvas
  // doesn't need to know about the toolbar's button identity.
  let fitToken = $state(0);
  let resetToken = $state(0);

  onMount(() => {
    graphPoller.start();
    return () => graphPoller.stop();
  });

  // Bridge effect: when activeWorkspaceId changes, capture the previous
  // workspace's UI state and schedule a deferred restore for the new
  // one. The actual restore lands after the next applyPayload — see
  // workspaceSnapshots.consumePending().
  let prevWorkspaceId: string | null = null;
  $effect(() => {
    const next = workspaceStore.activeWorkspaceId;
    untrack(() => {
      if (prevWorkspaceId === null) {
        prevWorkspaceId = next;
        return;
      }
      if (prevWorkspaceId === next) return;
      workspaceSnapshots.onSwitch(prevWorkspaceId, next);
      prevWorkspaceId = next;
      void graphPoller.refresh();
    });
  });

  // Prune effect: drop snapshots for tabs that are no longer open
  // (close + reconcileCollections both reduce openTabs).
  $effect(() => {
    const ids = new Set(workspaceStore.openTabs.map((t) => t.id));
    untrack(() => {
      for (const id of workspaceSnapshots.knownIds()) {
        if (!ids.has(id)) workspaceSnapshots.drop(id);
      }
    });
  });
</script>

<div class="tab">
  <WorkspaceTabs />
  <GraphToolbar
    onFit={() => (fitToken += 1)}
    onReset={() => {
      // Reset re-fetches so a stale view re-baselines, then re-runs
      // the synchronous layout against the fresh data.
      void graphPoller.refresh();
      resetToken += 1;
    }}
  />
  <div class="canvas">
    <GraphCanvas {fitToken} {resetToken} />
  </div>
</div>

<style>
  .tab {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .canvas {
    flex: 1;
    min-height: 0;
    position: relative;
  }
</style>
