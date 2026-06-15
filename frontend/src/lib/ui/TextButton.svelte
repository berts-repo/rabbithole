<script lang="ts">
  // Shared text-label button primitive.
  //
  // Variants: 'primary' (accent bg), 'secondary' (outline), 'ghost'
  // (transparent + accent text on hover).
  // Sizes: 'default' and 'small'.
  // Optional leading icon via the `icon` snippet slot.
  //
  // Usage:
  //   <TextButton onclick={handleClick}>Save</TextButton>
  //   <TextButton variant="primary" onclick={go}>Start Crawl</TextButton>
  //   <TextButton variant="ghost" size="small">Cancel</TextButton>

  import type { Snippet } from 'svelte';

  interface Props {
    variant?: 'primary' | 'secondary' | 'ghost';
    size?: 'default' | 'small';
    disabled?: boolean;
    type?: 'button' | 'submit' | 'reset';
    onclick?: (e: MouseEvent) => void;
    /** Native tooltip text (e.g. why a disabled action is unavailable). */
    title?: string;
    /** Optional icon to render before the label text. */
    icon?: Snippet;
    children: Snippet;
  }

  const {
    variant = 'secondary',
    size = 'default',
    disabled = false,
    type = 'button',
    onclick,
    title,
    icon,
    children,
  }: Props = $props();
</script>

<button
  {type}
  class="text-btn variant-{variant} size-{size}"
  {disabled}
  {title}
  {onclick}
>
  {#if icon}
    <span class="icon-slot" aria-hidden="true">
      {@render icon()}
    </span>
  {/if}
  {@render children()}
</button>

<style>
  .text-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    border-radius: 2px;
    cursor: pointer;
    font: inherit;
    white-space: nowrap;
    outline: none;
    /* Focus ring identical to IconButton */
  }

  .text-btn:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  /* Sizes */
  .size-default {
    font-size: 11px;
    padding: 4px 8px;
  }
  .size-small {
    font-size: 10px;
    padding: 2px 6px;
  }

  /* Variants */
  .variant-primary {
    background: rgba(0, 212, 170, 0.12);
    border: 1px solid var(--accent);
    color: var(--accent);
  }
  .variant-primary:hover:not(:disabled) {
    background: rgba(0, 212, 170, 0.22);
  }

  .variant-secondary {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
  }
  .variant-secondary:hover:not(:disabled) {
    color: var(--accent);
    border-color: var(--accent);
  }

  .variant-ghost {
    background: transparent;
    border: 1px solid transparent;
    color: var(--muted);
  }
  .variant-ghost:hover:not(:disabled) {
    color: var(--accent);
    border-color: var(--accent);
  }

  /* Disabled */
  .text-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    pointer-events: none;
  }

  .icon-slot {
    display: inline-flex;
    align-items: center;
    line-height: 0;
  }
</style>
