// Pure rename seam — types + helpers shared by the rename popover and the
// surfaces that open it (graph context menu, graph canvas, Page tab).
//
// Deliberately store-free and API-free so it can be imported directly in
// node-env Vitest (the popover can't be mounted, and `actions.ts` pulls in
// Svelte stores). The impure `renameTarget()` action lives in `actions.ts`
// and switches on the `RenameTarget` defined here.

// One discriminated target, mirroring the resource/domain split the rest of
// the app already keys on (domains.host TEXT vs resources/pages INTEGER).
// `page` is a typed slot — its endpoint goes live with the Label system; for
// now `renameTarget()` only services `domain`.
export type RenameTarget =
  | { kind: 'domain'; host: string }
  | { kind: 'page'; pageId: number };

// The per-surface modal-state shape, replacing the inline
// `{ kind: 'rename'; host; currentAlias }` each call site used to re-declare.
export interface RenameModal {
  kind: 'rename';
  x: number;
  y: number;
  target: RenameTarget;
  currentName: string | null;
}

// Unifies the modal SHAPE the three sites re-declare. Coordinate math stays
// per-surface (right-click coords vs graph→viewport projection vs button
// rect are genuinely surface-specific); callers pass the resolved anchor.
export function renameModal(
  target: RenameTarget,
  anchor: { x: number; y: number },
  currentName: string | null,
): RenameModal {
  return { kind: 'rename', x: anchor.x, y: anchor.y, target, currentName };
}

// Drives the popover's identity meta row + implicit title, replacing the
// hardwired "Domain" label so the same component renders for either target.
export function renameTargetIdentity(
  target: RenameTarget,
): { label: string; value: string } {
  if (target.kind === 'domain') return { label: 'Domain', value: target.host };
  return { label: 'Page', value: `#${target.pageId}` };
}
