<script lang="ts">
  // Generic drag handle. Pointer-capture so dragging out of the bar
  // still tracks; consumer applies the delta to its pane size and
  // calls commit() on pointer-up.

  type Axis = 'col' | 'row';
  type Props = {
    axis: Axis;
    onDrag: (deltaPx: number) => void;
    onCommit?: () => void;
    label?: string;
  };
  const { axis, onDrag, onCommit, label }: Props = $props();

  let dragging = $state(false);
  let last = 0;

  function pointerdown(e: PointerEvent) {
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    dragging = true;
    last = axis === 'col' ? e.clientX : e.clientY;
    e.preventDefault();
  }

  function pointermove(e: PointerEvent) {
    if (!dragging) return;
    const cur = axis === 'col' ? e.clientX : e.clientY;
    const delta = cur - last;
    last = cur;
    onDrag(delta);
  }

  function pointerup(e: PointerEvent) {
    if (!dragging) return;
    dragging = false;
    (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    onCommit?.();
  }
</script>

<div
  class="splitter"
  class:col={axis === 'col'}
  class:row={axis === 'row'}
  class:dragging
  role="separator"
  aria-orientation={axis === 'col' ? 'vertical' : 'horizontal'}
  aria-label={label ?? 'Pane splitter'}
  onpointerdown={pointerdown}
  onpointermove={pointermove}
  onpointerup={pointerup}
  onpointercancel={pointerup}
>
  <span class="grip"></span>
</div>

<style>
  /* Wide enough to grab easily; a centered line + grip make it visible
     and signal draggability. The whole bar is the hit target. */
  .splitter {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    z-index: 5;
  }
  /* The left/right slots are row-direction flex, so a vertical (col)
     splitter sizes its width via flex-basis. The bottom slot is also
     row-direction, so a horizontal (row) splitter must instead grow along
     the main axis to span full width — flex-basis there would shrink it to
     a tiny nub (the original bottom-resize bug). */
  .col {
    flex: 0 0 8px;
    height: 100%;
    cursor: col-resize;
  }
  .row {
    flex: 1 1 auto;
    height: 8px;
    cursor: row-resize;
  }
  /* Center line — faint at rest, accent on hover/drag. */
  .splitter::before {
    content: '';
    position: absolute;
    background: var(--border);
    transition: background 100ms ease-out;
  }
  .col::before {
    width: 1px;
    height: 100%;
  }
  .row::before {
    height: 1px;
    width: 100%;
  }
  .splitter:hover::before,
  .splitter.dragging::before {
    background: var(--accent);
  }
  /* Grip — a short brighter bar centered on the line. */
  .grip {
    position: relative;
    background: var(--border);
    border-radius: 2px;
    transition: background 100ms ease-out;
  }
  .col .grip {
    width: 2px;
    height: 24px;
  }
  .row .grip {
    height: 2px;
    width: 24px;
  }
  .splitter:hover .grip,
  .splitter.dragging .grip {
    background: var(--accent);
  }
</style>
