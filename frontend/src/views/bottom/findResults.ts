// Pure helpers for the Find results tab — kept out of the component so vitest
// can cover the snippet parsing without a Svelte runtime.

import type { KeywordResult } from '$lib/api';

export interface SnippetSegment {
  text: string;
  mark: boolean;
}

// Split a keyword snippet into highlighted / plain segments around the
// backend's `<mark>…</mark>` tags. SECURITY: the snippet embeds raw page text
// from untrusted onion sites and is NOT HTML-escaped server-side, so it must
// never reach the DOM via Svelte's raw-HTML directive. The component renders each segment's
// `text` as an auto-escaped text node and only wraps marked segments in a
// `<mark>` element — no raw page HTML can execute or load external resources.
export function parseSnippet(snippet: string): SnippetSegment[] {
  const segments: SnippetSegment[] = [];
  const re = /<mark>([\s\S]*?)<\/mark>/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(snippet)) !== null) {
    if (m.index > last) {
      segments.push({ text: snippet.slice(last, m.index), mark: false });
    }
    segments.push({ text: m[1], mark: true });
    last = m.index + m[0].length;
  }
  if (last < snippet.length) {
    segments.push({ text: snippet.slice(last), mark: false });
  }
  return segments;
}

// Stable list key — a search yields one immutable result array, but a page and
// one of its entities can share a node_id, so position disambiguates.
export function resultKey(r: KeywordResult, index: number): string {
  return `${r.type}:${r.node_id}:${index}`;
}
