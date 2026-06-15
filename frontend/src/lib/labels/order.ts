// Drag-reorder array move for the label rank list (item 11). The analyst's
// ordered list *is* the ranking (decision D5); both surfaces that let them
// drag it — the bottom-pane Labels tab (3a) and the Settings Labels tab (3e) —
// share this one move so neither drifts from the other. Kept store-free so
// vitest covers it directly.

// Move the item at `from` to `to` within a copy of `ids`, returning the new
// order. Out-of-range or no-op indices return the list unchanged.
export function reorderedIds(
  ids: readonly number[],
  from: number,
  to: number,
): number[] {
  if (
    from === to ||
    from < 0 ||
    to < 0 ||
    from >= ids.length ||
    to >= ids.length
  ) {
    return [...ids];
  }
  const next = [...ids];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}
