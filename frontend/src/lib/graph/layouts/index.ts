// Graph layout registry.
//
// A layout is a transform that runs once and freezes — it assigns x/y to
// the fetched (non-stub) nodes of a graphology instance, then the
// diff-update and drag-to-move systems own those positions until the next
// explicit re-layout. Stubs are placed separately by
// positionStubsAroundParents() and never go through a layout.
//
// Four layouts are synchronous pure geometry; 'force' is asynchronous
// (ForceAtlas2 in a Web Worker — see force.ts). Adding a layout is a new
// file with a matching signature plus one entry below.

import type Graph from 'graphology';
import { radialLayout } from './radial';
import { hierarchicalLayout } from './hierarchical';
import { concentricLayout } from './concentric';
import { timelineLayout, type TimelineLegend } from './timeline';

export { runForceLayout } from './force';
export type { ForceHandle } from './force';
export type { TimelineLegend };

export type LayoutKind =
  | 'force'
  | 'radial'
  | 'hierarchical'
  | 'concentric'
  | 'timeline';

export type SyncLayoutKind = Exclude<LayoutKind, 'force'>;

export const LAYOUT_KINDS: readonly LayoutKind[] = [
  'force',
  'radial',
  'hierarchical',
  'concentric',
  'timeline',
];

export const LAYOUT_LABELS: Record<LayoutKind, string> = {
  force: 'Force',
  radial: 'Radial',
  hierarchical: 'Hierarchical',
  concentric: 'Concentric',
  timeline: 'Timeline',
};

// Layout functions may return metadata for the canvas (today only the
// timeline legend); a plain positional layout returns void.
export interface LayoutMeta {
  timeline?: TimelineLegend;
}

export type SyncLayoutFn = (g: Graph) => LayoutMeta | void;

export const SYNC_LAYOUTS: Record<SyncLayoutKind, SyncLayoutFn> = {
  radial: radialLayout,
  hierarchical: hierarchicalLayout,
  concentric: concentricLayout,
  timeline: timelineLayout,
};

export function isLayoutKind(v: unknown): v is LayoutKind {
  return typeof v === 'string' && (LAYOUT_KINDS as readonly string[]).includes(v);
}
