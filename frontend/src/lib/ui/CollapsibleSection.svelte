<script lang="ts">
  // Shared collapsible section — the bordered card + chevron header used
  // across the left (Intel, Crawl) and right (Page/Domain/Analysis) panes.
  //
  // Controlled: the consumer owns collapse state (typically via a
  // `createCollapseStore` instance) and passes `collapsed` + `onToggle`.
  // The section body is a snippet so any content can live inside.
  //
  // Optional `actions` snippet renders header-level controls (e.g. an
  // "+ Add" button) to the right of the title, as a sibling of the toggle
  // button so the markup stays valid (no nested buttons).
  //
  // Usage:
  //   <CollapsibleSection
  //     title="Analyse"
  //     collapsed={sections.isCollapsed('analyse')}
  //     onToggle={() => sections.toggle('analyse')}
  //   >
  //     <ComposeForm />
  //   </CollapsibleSection>

  import { ChevronDown, ChevronRight } from 'lucide-svelte';
  import type { Snippet } from 'svelte';

  interface Props {
    title: string;
    collapsed: boolean;
    onToggle: () => void;
    children: Snippet;
    /** Optional header-level controls, right-aligned beside the title. */
    actions?: Snippet;
  }

  const { title, collapsed, onToggle, children, actions }: Props = $props();
</script>

<section class="section">
  <div class="head">
    <button type="button" class="toggle" aria-expanded={!collapsed} onclick={onToggle}>
      {#if collapsed}
        <ChevronRight size={13} />
      {:else}
        <ChevronDown size={13} />
      {/if}
      <span>{title}</span>
    </button>
    {#if actions}
      <div class="actions">{@render actions()}</div>
    {/if}
  </div>
  {#if !collapsed}
    <div class="body">
      {@render children()}
    </div>
  {/if}
</section>

<style>
  .section {
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
  }
  .head {
    display: flex;
    align-items: center;
    background: rgba(255, 255, 255, 0.02);
  }
  .toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    flex: 1;
    min-width: 0;
    padding: 6px 8px;
    background: transparent;
    border: none;
    color: var(--text);
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    text-align: left;
    cursor: pointer;
  }
  .toggle:hover {
    color: var(--accent);
  }
  .toggle span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 0 6px;
    flex: 0 0 auto;
  }
  .body {
    padding: 10px 8px;
    border-top: 1px solid var(--border);
  }
</style>
