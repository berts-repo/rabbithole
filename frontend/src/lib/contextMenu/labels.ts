// Pure label-apply seam (item 11) — the target types + modal shape shared by
// the label-picker popover and the surfaces that open it (graph context menu,
// right-pane Domain/Page tabs, future bottom-pane rows).
//
// Store-free and API-free, mirroring `rename.ts`, so it imports cleanly into
// node-env Vitest. The impure apply action (`setLabel`) lives in `actions.ts`
// and switches on the `LabelTarget` defined here.

// One discriminated target, mirroring the two typed join tables: resources
// keyed by INTEGER id (`resource_labels`), domains by TEXT host
// (`domain_labels`). A graph node is a resource; the Domain tab is a domain.
export type LabelTarget =
  | { kind: 'resource'; resourceId: number; name: string }
  | { kind: 'domain'; host: string };

// Per-surface modal state, mirroring `RenameModal` — the surface resolves the
// anchor coords and the target's current *direct* label ids (the via-domain
// ones aren't togglable here; they're detached from the domain, a different
// target).
export interface LabelPickerModal {
  kind: 'labelPicker';
  x: number;
  y: number;
  target: LabelTarget;
  currentIds: number[];
}

export function labelPickerModal(
  target: LabelTarget,
  anchor: { x: number; y: number },
  currentIds: number[],
): LabelPickerModal {
  return { kind: 'labelPicker', x: anchor.x, y: anchor.y, target, currentIds };
}

// The popover's identity meta row — what's being labeled.
export function labelTargetIdentity(
  target: LabelTarget,
): { label: string; value: string } {
  if (target.kind === 'domain') return { label: 'Domain', value: target.host };
  return { label: 'Page', value: target.name };
}

// Whether the picker should offer "Create & apply '<name>'" for the typed
// query: only when it's non-empty and doesn't already name an existing label
// (case-insensitive — the DB name is UNIQUE NOCASE). Returns the trimmed name
// to create, or null. Pure so the popover's gating is unit-testable.
export function labelCreateName(
  query: string,
  existingNames: readonly string[],
): string | null {
  const name = query.trim();
  if (name === '') return null;
  const lower = name.toLowerCase();
  return existingNames.some((n) => n.toLowerCase() === lower) ? null : name;
}
