// Entity context menu — used by every right-pane surface that lists
// entities (Page tab's expanded details, Domain tab's entities list, and
// the cluster workspace Common tab). The per-type action set follows
// docs/specs/right-pane.md:97-103 / :164-172:
//
//   Onion URL              Send to Find · Send to Crawl · Copy
//   Handle                 Send to Find · Copy
//   Email/BTC/XMR/PGP/blob Copy
//
// Any type not in the first two buckets gets a plain copy-only menu, so a
// future entity type silently falls back to the safe path.

import {
  actCopyUrl,
  actQueueCrawl,
  actSendToFind,
} from '$lib/contextMenu/actions';
import type { MenuSection } from '$lib/contextMenu/sections';

export type EntityKind = 'onion' | 'handle' | 'copy_only';

export function entityKindFor(type: string): EntityKind {
  // Normalize for case-insensitive matching — backend stores
  // type-detector keys in lowercase but a future analyst-added entity
  // could break that convention.
  const t = type.toLowerCase();
  // ``i2p`` eepsite hosts are crawlable like onions — same Send to Find /
  // Send to Crawl / Copy action set (the 'onion' kind is just that bucket).
  if (t === 'onion' || t === 'onion_url' || t === 'url' || t === 'i2p') {
    return 'onion';
  }
  if (t === 'handle' || t === 'username') return 'handle';
  return 'copy_only';
}

export function buildEntityMenu(type: string, value: string): MenuSection[] {
  const kind = entityKindFor(type);
  if (kind === 'onion') {
    return [
      {
        items: [
          { label: 'Send to Find', onSelect: () => actSendToFind(value) },
          { label: 'Send to Crawl', onSelect: () => actQueueCrawl(value) },
          { label: 'Copy', onSelect: () => actCopyUrl(value) },
        ],
      },
    ];
  }
  if (kind === 'handle') {
    return [
      {
        items: [
          { label: 'Send to Find', onSelect: () => actSendToFind(value) },
          { label: 'Copy', onSelect: () => actCopyUrl(value) },
        ],
      },
    ];
  }
  return [
    {
      items: [{ label: 'Copy', onSelect: () => actCopyUrl(value) }],
    },
  ];
}
