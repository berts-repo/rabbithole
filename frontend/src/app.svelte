<script lang="ts">
  import AppShell from './views/AppShell.svelte';
  import { projectsStore } from '$lib/stores/projects.svelte';
  import { servicesStore } from '$lib/stores/services.svelte';
  import { graphFiltersStore } from '$lib/stores/graphFilters.svelte';
  import { graphPinsStore } from '$lib/stores/graphPins.svelte';
  import { graphLayoutStore } from '$lib/stores/graphLayout.svelte';
  import { workspaceStore } from '$lib/stores/workspace.svelte';
  import { navigationStore } from '$lib/stores/navigation.svelte';
  import { labelsStore } from '$lib/stores/labels.svelte';
  import { labelFilterStore } from '$lib/stores/labelFilter.svelte';
  import { graphCollapseStore } from '$lib/stores/graphCollapse.svelte';
  import { torStatusPoller } from '$lib/pollers/torStatus.svelte';
  import { statsPoller } from '$lib/pollers/stats.svelte';
  import { killSwitchPoller } from '$lib/pollers/killSwitch.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { getSetting, getTorStatus } from '$lib/api';

  // Bootstrap on mount: load projects, hydrate kill-switch enforcement
  // setting, snapshot kill-switch state from /api/tor/status (so a
  // refresh while tripped keeps the FSM in tripped), subscribe to SSE
  // for live transitions, start pollers.
  $effect(() => {
    void projectsStore.load();
    void getSetting<boolean>('tor.kill_switch')
      .then((s) => {
        servicesStore.setKillSwitchEnabled(s.value ?? true);
      })
      .catch((e) => {
        const msg = e instanceof Error ? e.message : String(e);
        toastStore.show(`Settings load failed: ${msg}`, 'warn');
      });
    void graphFiltersStore.load();
    void graphPinsStore.load();
    void graphLayoutStore.load();
    void workspaceStore.load();
    void navigationStore.load();
    // Label catalog (item 11) — the source of truth for chips/picker/color.
    // Project-scoped; a project switch reloads the page, so loading once here
    // is enough.
    void labelsStore.ensureLoaded();
    // Persisted label include/exclude filter (item 11, Phase 3c).
    void labelFilterStore.load();
    // Persisted per-tab graph collapse state (item 11, Phase 3d).
    void graphCollapseStore.load();
    void getTorStatus()
      .then((s) => {
        if (s.engaged) servicesStore.tripKillSwitch('tor_lost');
        servicesStore.setTor({ reachable: s.ok, lastPoll: Date.now() });
      })
      .catch(() => {
        // Pollers will retry; nothing to surface here.
      });
    killSwitchPoller.start();
    torStatusPoller.start();
    statsPoller.start();
    return () => {
      killSwitchPoller.stop();
      torStatusPoller.stop();
      statsPoller.stop();
    };
  });
</script>

<AppShell />
