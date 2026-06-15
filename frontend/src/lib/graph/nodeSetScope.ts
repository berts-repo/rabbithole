// NodeSet scope — maps a workspace node-set source to a visibility-scope
// predicate the visibilityController consumes (item 4, list-to-graph-tabs).
//
// A NodeSet tab shows the induced subgraph over a set of graph nodes drawn
// from a bottom-pane list (or a graph multi-selection). Two membership
// styles:
//
//   derived  — re-evaluated from the live payload/store on every compute, so
//              new matches appear automatically (domain pages, hidden nodes).
//   captured — a frozen node-id set taken at open time, used where membership
//              is not a stable graph-node attribute (a fingerprint cluster, a
//              filtered flag list, a graph selection).
//
// Pure TypeScript — no Svelte runtime — so vitest can cover it directly.

import type { ScopePredicate } from './controllers/visibilityController';

export type NodeSetSource =
  // derived: every node whose host matches
  | { kind: 'domain'; host: string }
  // captured: the flagged nodes currently shown in the Flags list
  | { kind: 'flag'; nodeIds: number[]; summary: string }
  // captured: the members of one fingerprint cluster
  | { kind: 'fingerprint'; nodeIds: number[]; summary: string }
  // derived-by-host: every node belonging to a bookmarked seed's host
  // (seeds are usually site roots, so the host subgraph is the useful scope)
  | { kind: 'bookmarks'; hosts: string[] }
  // derived: the nodes the visibility filters currently hide
  | { kind: 'hidden' }
  // captured: a graph multi-selection
  | { kind: 'selection'; nodeIds: number[] }
  // captured: the resources carrying one label (item 11) — "all resources
  // labeled X" as its own workspace tab
  | { kind: 'label'; labelId: number; nodeIds: number[]; summary: string };

export type NodeSetKind = NodeSetSource['kind'];

/** Hide-state access the `hidden` source needs to identify hidden nodes. */
export interface HiddenDeps {
  isHidden(domain: string | null | undefined): boolean;
  isNodeHidden(id: number | null | undefined): boolean;
}

export interface NodeSetScope {
  /** Allow-predicate over graph nodes — true keeps the node in scope. */
  predicate: ScopePredicate;
  /**
   * When true the controller must keep nodes it would normally hide, so the
   * `hidden` source can actually display them. False for every other source.
   */
  includeHidden: boolean;
}

/**
 * Build the visibility-scope predicate for a node-set source. `hiddenDeps` is
 * only consulted by the `hidden` source; pass the live domain-visibility
 * store accessors so it re-derives on every compute.
 */
export function buildNodeSetPredicate(
  source: NodeSetSource,
  hiddenDeps: HiddenDeps,
): NodeSetScope {
  switch (source.kind) {
    case 'domain': {
      const host = source.host;
      return {
        predicate: (_id, raw) => !!raw && raw.domain === host,
        includeHidden: false,
      };
    }
    case 'bookmarks': {
      const hosts = new Set(source.hosts);
      return {
        predicate: (_id, raw) => !!raw && !!raw.domain && hosts.has(raw.domain),
        includeHidden: false,
      };
    }
    case 'hidden': {
      return {
        predicate: (_id, raw) =>
          !!raw && (hiddenDeps.isHidden(raw.domain) || hiddenDeps.isNodeHidden(raw.id)),
        includeHidden: true,
      };
    }
    case 'flag':
    case 'fingerprint':
    case 'selection':
    case 'label': {
      const ids = new Set(source.nodeIds);
      return {
        predicate: (_id, raw) => !!raw && ids.has(raw.id),
        includeHidden: false,
      };
    }
  }
}

/**
 * Stable signature for a source, used to derive a tab id so reopening the same
 * source focuses (and refreshes) its existing tab instead of stacking
 * duplicates. Distinct selections / distinct flag filters have distinct
 * signatures; the singleton sources (hidden, bookmarks) collapse to one tab.
 */
export function nodeSetSignature(source: NodeSetSource): string {
  switch (source.kind) {
    case 'domain':
      return `domain:${source.host}`;
    case 'hidden':
      return 'hidden';
    case 'bookmarks':
      return 'bookmarks';
    case 'fingerprint':
      return `fingerprint:${source.summary}`;
    case 'flag':
      return `flag:${source.summary}`;
    case 'label':
      return `label:${source.labelId}`;
    case 'selection':
      return `selection:${[...source.nodeIds].sort((a, b) => a - b).join(',')}`;
  }
}
