<script lang="ts">
  // Left pane · Intel sub-tab. The control panel for local AI analysis:
  // compose / monitor / inspect with clear pane ownership (this pane composes
  // and controls). Collapsible sections; collapse state persists to
  // localStorage via intelSectionsStore.
  //
  // Phase 2 ships two sections — LLM Service (worker control + load) and
  // Analyse (the unified compose form). Phase 3 adds Embedding, Collection
  // Analysis, Auto-analysis Rules, and Prompt Templates.

  import { CollapsibleSection } from '$lib/ui';
  import { intelSectionsStore } from '$lib/stores/intelCompose.svelte';
  import AutoAnalysisRules from './intel/AutoAnalysisRules.svelte';
  import CollectionAnalysis from './intel/CollectionAnalysis.svelte';
  import ComposeForm from './intel/ComposeForm.svelte';
  import EmbeddingSection from './intel/EmbeddingSection.svelte';
  import WorkerControls from './intel/WorkerControls.svelte';

  const sections: { id: string; title: string }[] = [
    { id: 'llm', title: 'LLM Service' },
    { id: 'analyse', title: 'Analyse' },
    { id: 'auto', title: 'Auto-analysis Rules' },
    { id: 'collection', title: 'Collection Analysis' },
    { id: 'embedding', title: 'Embedding Model' },
  ];
</script>

<div class="intel">
  {#each sections as section (section.id)}
    <CollapsibleSection
      title={section.title}
      collapsed={intelSectionsStore.isCollapsed(section.id)}
      onToggle={() => intelSectionsStore.toggle(section.id)}
    >
      {#if section.id === 'llm'}
        <WorkerControls />
      {:else if section.id === 'analyse'}
        <ComposeForm />
      {:else if section.id === 'auto'}
        <AutoAnalysisRules />
      {:else if section.id === 'collection'}
        <CollectionAnalysis />
      {:else if section.id === 'embedding'}
        <EmbeddingSection />
      {/if}
    </CollapsibleSection>
  {/each}
</div>

<style>
  .intel {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
</style>
