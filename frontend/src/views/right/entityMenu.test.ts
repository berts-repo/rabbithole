import { describe, expect, it, vi } from 'vitest';

vi.mock('$lib/contextMenu/actions', () => ({
  actCopyUrl: vi.fn(),
  actQueueCrawl: vi.fn(),
  actSendToFind: vi.fn(),
}));

import { buildEntityMenu, entityKindFor } from './entityMenu';

describe('entityKindFor', () => {
  it('maps onion-ish types to onion', () => {
    expect(entityKindFor('onion')).toBe('onion');
    expect(entityKindFor('Onion')).toBe('onion');
    expect(entityKindFor('onion_url')).toBe('onion');
    expect(entityKindFor('url')).toBe('onion');
  });

  it('maps handle/username to handle', () => {
    expect(entityKindFor('handle')).toBe('handle');
    expect(entityKindFor('username')).toBe('handle');
  });

  it('falls back to copy_only for everything else', () => {
    for (const t of ['email', 'btc', 'xmr', 'pgp', 'blob', 'random']) {
      expect(entityKindFor(t)).toBe('copy_only');
    }
  });
});

describe('buildEntityMenu', () => {
  it('builds a 3-item Find/Crawl/Copy menu for onion URLs', () => {
    const sections = buildEntityMenu('onion', 'http://example.onion');
    expect(sections).toHaveLength(1);
    expect(sections[0].items.map((i) => i.label)).toEqual([
      'Send to Find',
      'Send to Crawl',
      'Copy',
    ]);
  });

  it('builds a 2-item Find/Copy menu for handles', () => {
    const sections = buildEntityMenu('handle', '@alice');
    expect(sections[0].items.map((i) => i.label)).toEqual([
      'Send to Find',
      'Copy',
    ]);
  });

  it('builds a copy-only menu for everything else', () => {
    for (const t of ['email', 'btc', 'xmr', 'pgp', 'blob']) {
      const sections = buildEntityMenu(t, 'some-value');
      expect(sections[0].items.map((i) => i.label)).toEqual(['Copy']);
    }
  });
});
