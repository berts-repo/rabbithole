<script lang="ts">
  // CSP-safe hover tooltip — content is rendered via text interpolation
  // (textContent under the hood), never as raw HTML.

  interface Props {
    x: number;
    y: number;
    text: string;
  }

  let { x, y, text }: Props = $props();
</script>

<div
  class="tip"
  style:left="{x}px"
  style:top="{y}px"
  role="tooltip"
>
  {text}
</div>

<style>
  .tip {
    position: absolute;
    transform: translate(-50%, -100%);
    background: rgba(16, 17, 20, 0.95);
    border: 1px solid var(--border);
    color: var(--text);
    font-size: 11px;
    padding: 4px 8px;
    border-radius: 3px;
    pointer-events: none;
    max-width: 320px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    z-index: 6;
  }
</style>
