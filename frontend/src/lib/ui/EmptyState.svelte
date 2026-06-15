<script lang="ts">
  // Shared empty-state block.
  //
  // Replaces ad-hoc "No selection" / "No data" paragraphs across all panes.
  // Only `title` is required; everything else is optional.
  //
  // Usage:
  //   <EmptyState title="No node selected." />
  //   <EmptyState title="No analyses yet." body="Queue a job to start." />
  //
  // The `action` snippet allows callers to pass a CTA button or link:
  //   <EmptyState title="No collections.">
  //     {#snippet action()}<button …>Create one</button>{/snippet}
  //   </EmptyState>

  import type { Snippet } from 'svelte';

  interface Props {
    title: string;
    body?: string;
    /** Optional icon character / emoji to display above the title. */
    icon?: string;
    /** Optional action content (CTA button, link, etc.). */
    action?: Snippet;
    /** Error mode: use red text instead of muted. */
    error?: boolean;
  }

  const { title, body, icon, action, error = false }: Props = $props();
</script>

<div class="empty-state" class:error>
  {#if icon}
    <span class="icon" aria-hidden="true">{icon}</span>
  {/if}
  <p class="title">{title}</p>
  {#if body}
    <p class="body">{body}</p>
  {/if}
  {#if action}
    <div class="action-slot">
      {@render action()}
    </div>
  {/if}
</div>

<style>
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }
  .icon {
    font-size: 18px;
    line-height: 1;
    opacity: 0.5;
    margin-bottom: 2px;
  }
  .title {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
    font-style: italic;
  }
  .empty-state.error .title {
    color: #ff6b6b;
    font-style: normal;
  }
  .body {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
  }
  .action-slot {
    margin-top: 4px;
  }
</style>
