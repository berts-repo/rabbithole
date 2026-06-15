<script lang="ts">
  // Shared icon-only button primitive.
  //
  // `label` is required — it becomes both aria-label and the native
  // `title` tooltip. Omitting it is a TypeScript error.
  //
  // Sizes: 'default' (24 px touch target) and 'small' (20 px).
  // Variants: 'ghost' (border on hover only), 'outline' (always bordered),
  // and 'subtle' (borderless; hover fills with a faint wash + accent text —
  // matches the graph workspace '+' button, used for pane collapse arrows).
  //
  // Toggle mode: pass `pressed` to emit aria-pressed and style the active
  // state with the accent colour.
  //
  // Usage:
  //   <IconButton label="Refresh" onclick={handleClick}>
  //     <RefreshCw size={11} />
  //   </IconButton>

  import type { Snippet } from 'svelte';

  interface Props {
    /** Required: becomes aria-label AND native title tooltip. */
    label: string;
    size?: 'default' | 'small';
    variant?: 'ghost' | 'outline' | 'subtle';
    disabled?: boolean;
    /** When defined, renders aria-pressed and accent-highlights when true. */
    pressed?: boolean;
    /**
     * Disclosure toggles (button controls a popover/panel): renders
     * aria-expanded and accent-highlights when true. Use instead of
     * `pressed` for show/hide controls.
     */
    expanded?: boolean;
    onclick?: (e: MouseEvent) => void;
    children: Snippet;
  }

  const {
    label,
    size = 'default',
    variant = 'outline',
    disabled = false,
    pressed,
    expanded,
    onclick,
    children,
  }: Props = $props();

  // Runtime warning if label is somehow empty (belt-and-suspenders for JS
  // callers that skip TypeScript).
  $effect(() => {
    if (!label) {
      console.warn('IconButton: `label` prop is required for accessibility.');
    }
  });
</script>

<button
  type="button"
  class="icon-btn size-{size} variant-{variant}"
  class:pressed={pressed === true || expanded === true}
  aria-label={label}
  title={label}
  aria-pressed={pressed !== undefined ? pressed : undefined}
  aria-expanded={expanded !== undefined ? expanded : undefined}
  {disabled}
  {onclick}
>
  {@render children()}
</button>

<style>
  .icon-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
    line-height: 0;
    border-radius: 2px;
    /* Consistent focus ring across all primitives */
    outline: none;
  }

  /* Focus ring — identical across all interactive primitives */
  .icon-btn:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  /* Sizes */
  .size-default {
    width: 24px;
    height: 24px;
    padding: 4px 6px;
  }
  .size-small {
    width: 20px;
    height: 20px;
    padding: 3px 4px;
  }

  /* Variants */
  .variant-outline {
    border: 1px solid var(--border);
  }
  .variant-ghost {
    border: 1px solid transparent;
  }
  /* Borderless square; hover/expanded fills with a faint wash + accent text.
     Mirrors the graph workspace '+' button so pane collapse arrows match. */
  .variant-subtle {
    border: none;
    border-radius: 4px;
  }

  /* Hover — outline/ghost draw an accent border; subtle fills instead */
  .icon-btn.variant-outline:hover:not(:disabled),
  .icon-btn.variant-ghost:hover:not(:disabled) {
    color: var(--accent);
    border-color: var(--accent);
  }
  .icon-btn.variant-subtle:hover:not(:disabled) {
    color: var(--accent);
    background: rgba(255, 255, 255, 0.06);
  }

  /* Pressed / active toggle state */
  .icon-btn.variant-outline.pressed,
  .icon-btn.variant-ghost.pressed {
    color: var(--accent);
    border-color: var(--accent);
    background: rgba(0, 212, 170, 0.12);
  }
  .icon-btn.variant-subtle.pressed {
    color: var(--accent);
    background: rgba(255, 255, 255, 0.06);
  }

  /* Disabled — perceivable beyond opacity only */
  .icon-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    /* Explicitly maintain the perceived border even when disabled */
    pointer-events: none;
  }
</style>
