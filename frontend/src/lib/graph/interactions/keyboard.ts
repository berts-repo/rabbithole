// Keyboard interaction policy for the graph canvas.
//
// classifyGraphKey turns a key event's facts into an intent; GraphCanvas
// owns the dispatch (which stores to poke, when to preventDefault). Pure
// — no DOM, no store reads — so the policy is testable without a canvas.

export type GraphKeyIntent = 'escape' | 'select-all' | 'focus-node' | 'none';

export interface GraphKeyFacts {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  // True when focus sits in a text-entry control (INPUT / TEXTAREA /
  // contenteditable). Typing must not be trapped — but Escape is exempt
  // and is classified before this guard, so it still exits draw-edge /
  // ego-focus / selection even from the ego-focus depth slider.
  inTextEntry: boolean;
}

export function classifyGraphKey(facts: GraphKeyFacts): GraphKeyIntent {
  if (facts.key === 'Escape') return 'escape';
  if (facts.inTextEntry) return 'none';
  if (
    (facts.ctrlKey || facts.metaKey) &&
    (facts.key === 'a' || facts.key === 'A')
  ) {
    return 'select-all';
  }
  if (
    (facts.key === 'f' || facts.key === 'F') &&
    !facts.ctrlKey &&
    !facts.metaKey &&
    !facts.altKey
  ) {
    return 'focus-node';
  }
  return 'none';
}
