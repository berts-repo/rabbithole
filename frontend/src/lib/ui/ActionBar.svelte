<script lang="ts">
  // Shared action bar container primitive.
  //
  // A flex strip for a pane's primary action group. The `primary` slot
  // holds the main action buttons; the `overflow` slot holds secondary
  // actions (typically a "More…" button). If no overflow is provided,
  // the primary group fills the full width.
  //
  // This primitive owns padding, border, and focus order.
  // The action buttons inside should use <IconButton> or <TextButton>.
  //
  // Usage:
  //   <ActionBar>
  //     {#snippet primary()}
  //       <TextButton onclick={…}>Crawl</TextButton>
  //       <TextButton onclick={…}>Flag</TextButton>
  //     {/snippet}
  //     {#snippet overflow()}
  //       <IconButton label="More" onclick={…}><MoreHorizontal /></IconButton>
  //     {/snippet}
  //   </ActionBar>

  import type { Snippet } from 'svelte';

  interface Props {
    primary: Snippet;
    overflow?: Snippet;
  }

  const { primary, overflow }: Props = $props();
</script>

<div class="action-bar">
  <div class="primary-group">
    {@render primary()}
  </div>
  {#if overflow}
    <div class="overflow-group">
      {@render overflow()}
    </div>
  {/if}
</div>

<style>
  .action-bar {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 6px 8px;
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
  }
  .primary-group {
    display: flex;
    align-items: center;
    gap: 4px;
    flex: 1;
    flex-wrap: wrap;
    min-width: 0;
  }
  .overflow-group {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-left: auto;
    position: relative;
  }
</style>
