// Resource lifecycle helpers — the single place the app reasons about a
// node's crawl state. Replaces the old `stub` boolean (schema-reset v3).
//
// A resource is "uncrawled" until it has been fetched at least once (i.e.
// has a current page_version). `unknown` / `known` / `dead` all render as
// halo placeholders and are excluded from layouts; only `crawled` carries
// real content.

import type { ResourceState } from '$lib/api';

export function isCrawled(node: { state: ResourceState }): boolean {
  return node.state === 'crawled';
}

export function isUncrawled(node: { state: ResourceState }): boolean {
  return node.state !== 'crawled';
}

// Human-readable lifecycle labels (right pane, badges, tooltips, filters).
export const STATE_LABEL: Record<ResourceState, string> = {
  unknown: 'Unknown',
  known: 'Known (uncrawled)',
  crawled: 'Crawled',
  dead: 'Dead',
};

export function stateLabel(state: ResourceState): string {
  return STATE_LABEL[state] ?? state;
}
