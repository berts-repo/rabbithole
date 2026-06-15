<script lang="ts">
  import { onMount } from 'svelte';
  import CrawlControls from './crawl/CrawlControls.svelte';
  import BatchConfirmStrip from './crawl/BatchConfirmStrip.svelte';
  import BulkImport from './crawl/BulkImport.svelte';
  import { crawlStore } from '$lib/stores/crawl.svelte';
  import { crawlStatusPoller } from '$lib/pollers/crawlStatus.svelte';
  import { batchConfirmStore } from '$lib/stores/batchConfirm.svelte';
  import { createCollapseStore } from '$lib/stores/sectionCollapse.svelte';
  import { CollapsibleSection } from '$lib/ui';

  const sections = createCollapseStore('rabbithole.left.crawl');

  type Props = { onOpenSettings: () => void };
  const { onOpenSettings }: Props = $props();

  // Shared seed input — Bulk Import's ▶ Send to Crawl button (and every
  // other single-URL intake surface, via batchConfirmStore.loadIntoControls)
  // lifts a URL into the controls section. State lives here so the click
  // can update the child without forcing a global store for the input
  // itself.
  let seedUrl = $state('');

  function focusSeedInput() {
    const el = document.querySelector<HTMLInputElement>('input[data-crawl-seed-url]');
    el?.focus();
    el?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  function liftSeed(url: string) {
    seedUrl = url;
    requestAnimationFrame(focusSeedInput);
  }

  onMount(() => {
    crawlStore.subscribe();
    crawlStatusPoller.start();
    // Expose the seed-input lift to every intake surface through the
    // shared store so single-URL "Send to Crawl" actions outside the
    // Crawl sub-tab can route here without a prop chain.
    batchConfirmStore.setLoadIntoControls(liftSeed);
    // Cross-tab triggers (e.g. graph right-click while the Crawl sub-tab
    // is hidden) buffer the URL in the store; flush it now that we own
    // the lift handler.
    const pending = batchConfirmStore.consumePendingLoad();
    if (pending) liftSeed(pending);
    return () => {
      batchConfirmStore.setLoadIntoControls(null);
      crawlStatusPoller.stop();
      crawlStore.unsubscribe();
    };
  });
</script>

<div class="crawl">
  <CollapsibleSection
    title="Crawl"
    collapsed={sections.isCollapsed('crawl')}
    onToggle={() => sections.toggle('crawl')}
  >
    <CrawlControls bind:seedUrl onOpenSettings={onOpenSettings} />
  </CollapsibleSection>

  <!-- Transient: only renders while a batch is staged, so it stays a bare
       strip rather than a permanent (often empty) section. -->
  <BatchConfirmStrip />

  <CollapsibleSection
    title="Bulk Import"
    collapsed={sections.isCollapsed('bulk')}
    onToggle={() => sections.toggle('bulk')}
  >
    <BulkImport onSendToCrawl={liftSeed} />
  </CollapsibleSection>
</div>

<style>
  .crawl {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
</style>
