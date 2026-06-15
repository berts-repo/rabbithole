// Selection interaction rules for graph-canvas pointer gestures.
//
// Pure predicates: GraphCanvas owns the Sigma event wiring and the DOM
// type-narrowing; this module owns the "what does this gesture mean"
// policy so it stays testable without mounting the canvas.

// A node click is a multi-select gesture when any multi-select modifier
// is held. Ctrl/Cmd is the primary gesture (Figma / file-manager
// convention); Shift is kept as a cross-platform alternate. `ev` is null
// when the originating Sigma event was not backed by a MouseEvent.
export function isMultiSelectModifier(
  ev: { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean } | null,
): boolean {
  return !!(ev && (ev.ctrlKey || ev.metaKey || ev.shiftKey));
}

// Right-clicking a node opens the multi-select menu only when that node
// is part of an existing selection of 2 or more — otherwise the gesture
// points at the single node the analyst aimed at.
export function shouldOpenMultiMenu(
  multiCount: number,
  nodeIsSelected: boolean,
): boolean {
  return multiCount >= 2 && nodeIsSelected;
}
