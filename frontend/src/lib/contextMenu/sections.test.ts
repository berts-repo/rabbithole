import { describe, it, expect, vi } from 'vitest';
import {
  buildSingleTargetSections,
  buildMultiSelectSections,
  type MenuCapability,
  type MenuItem,
  type MenuSection,
  type MenuTarget,
  type SingleTargetMenuHandlers,
  type MultiSelectMenuHandlers,
} from './sections';

// Minimal MenuTarget factory — only the fields the builders read
// (state / flag_status / reviewed / domain) matter.
function makeTarget(over: Partial<MenuTarget> = {}): MenuTarget {
  return {
    state: 'crawled',
    flag_status: null,
    reviewed: false,
    domain: 'example.onion',
    ...over,
  };
}

function noopSingleHandlers(): SingleTargetMenuHandlers {
  return {
    copyUrl: () => {},
    openInTor: () => {},
    queueCrawl: () => {},
    saveSeedBookmark: () => {},
    flag: () => {},
    removeFlag: () => {},
    toggleReviewed: () => {},
    addMonitor: () => {},
    renameAlias: () => {},
    applyLabels: () => {},
    queueAnalysis: () => {},
    addToCollection: () => {},
    focus: () => {},
    hideFromGraph: () => {},
  };
}

function noopMultiHandlers(): MultiSelectMenuHandlers {
  return {
    addToCollection: () => {},
    drawEdge: () => {},
    crawlSelected: () => {},
    flagAll: () => {},
    markReviewedAll: () => {},
    queueAnalysis: () => {},
    hideAll: () => {},
    openAsTab: () => {},
  };
}

function allItems(sections: MenuSection[]): MenuItem[] {
  return sections.flatMap((s) => s.items);
}

function item(sections: MenuSection[], label: string): MenuItem {
  const found = allItems(sections).find((i) => i.label === label);
  if (!found) throw new Error(`menu item not found: ${label}`);
  return found;
}

function labels(sections: MenuSection[]): string[] {
  return allItems(sections).map((i) => i.label);
}

describe('buildSingleTargetSections', () => {
  it('groups items under the CRAWL/INVESTIGATION/ANALYSIS/GRAPH dividers', () => {
    const sections = buildSingleTargetSections(
      makeTarget(),
      { torArmed: true },
      noopSingleHandlers(),
    );
    expect(sections.map((s) => s.label)).toEqual([
      undefined,
      'Crawl',
      'Investigation',
      'Analysis',
      'Collection',
      'Graph',
    ]);
  });

  it('leads with "Rename alias…" as the top menu item', () => {
    const sections = buildSingleTargetSections(
      makeTarget(),
      { torArmed: true },
      noopSingleHandlers(),
    );
    expect(sections[0].items[0].label).toBe('Rename alias…');
  });

  it('disables "Rename alias…" with a reason on a domain-less target', () => {
    const sections = buildSingleTargetSections(
      makeTarget({ domain: null }),
      { torArmed: true },
      noopSingleHandlers(),
    );
    const rename = item(sections, 'Rename alias…');
    expect(rename.disabled).toBe(true);
    expect(rename.disabledReason).toBe('No domain');
  });

  it('offers "Collapse domain" only when a toggleCollapseDomain handler is wired', () => {
    const without = buildSingleTargetSections(makeTarget(), { torArmed: true }, noopSingleHandlers());
    expect(labels(without)).not.toContain('Collapse domain');

    const handlers = { ...noopSingleHandlers(), toggleCollapseDomain: () => {} };
    const withCollapse = buildSingleTargetSections(makeTarget(), { torArmed: true }, handlers);
    expect(labels(withCollapse)).toContain('Collapse domain');
  });

  it('flips Collapse → Expand when the domain is already folded', () => {
    const handlers = { ...noopSingleHandlers(), toggleCollapseDomain: () => {} };
    const sections = buildSingleTargetSections(
      makeTarget(),
      { torArmed: true, domainCollapsed: true },
      handlers,
    );
    expect(labels(sections)).toContain('Expand domain');
    expect(labels(sections)).not.toContain('Collapse domain');
  });

  it('disables the collapse item on a domain-less target', () => {
    const handlers = { ...noopSingleHandlers(), toggleCollapseDomain: () => {} };
    const sections = buildSingleTargetSections(
      makeTarget({ domain: null }),
      { torArmed: true },
      handlers,
    );
    const collapse = item(sections, 'Collapse domain');
    expect(collapse.disabled).toBe(true);
    expect(collapse.disabledReason).toBe('No domain');
  });

  it('disables "Open in Tor Browser" with a reason when Tor is not armed', () => {
    const sections = buildSingleTargetSections(
      makeTarget(),
      { torArmed: false },
      noopSingleHandlers(),
    );
    const tor = item(sections, 'Open in Tor Browser');
    expect(tor.disabled).toBe(true);
    expect(tor.disabledReason).toBe('Tor not connected');
  });

  it('enables "Open in Tor Browser" when Tor is armed', () => {
    const sections = buildSingleTargetSections(
      makeTarget(),
      { torArmed: true },
      noopSingleHandlers(),
    );
    expect(item(sections, 'Open in Tor Browser').disabled).toBe(false);
  });

  it('keeps "Send to Crawl" enabled on a crawled (non-stub) target and enables "Hide from Graph"', () => {
    const sections = buildSingleTargetSections(
      makeTarget({ state: 'crawled' }),
      { torArmed: true },
      noopSingleHandlers(),
    );
    const send = item(sections, 'Send to Crawl');
    expect(send.disabled).toBeFalsy();
    expect(item(sections, 'Hide from Graph').disabled).toBe(false);
  });

  it('keeps "Send to Crawl" enabled on a stub target and gates "Hide from Graph"', () => {
    const sections = buildSingleTargetSections(
      makeTarget({ state: 'known' }),
      { torArmed: true },
      noopSingleHandlers(),
    );
    const send = item(sections, 'Send to Crawl');
    expect(send.disabled).toBeFalsy();
    const hide = item(sections, 'Hide from Graph');
    expect(hide.disabled).toBe(true);
    expect(hide.disabledReason).toBe('Crawled nodes only');
  });

  it('offers three priority rows for an unflagged target', () => {
    const sections = buildSingleTargetSections(
      makeTarget({ flag_status: null }),
      { torArmed: true },
      noopSingleHandlers(),
    );
    expect(labels(sections)).toEqual(
      expect.arrayContaining(['Flag — High', 'Flag — Medium', 'Flag — Low']),
    );
    expect(labels(sections)).not.toContain('Remove Flag');
  });

  it('collapses to a single Remove row for a flagged target', () => {
    const sections = buildSingleTargetSections(
      makeTarget({ flag_status: 'flagged' }),
      { torArmed: true },
      noopSingleHandlers(),
    );
    expect(labels(sections)).toContain('Remove Flag');
    expect(labels(sections)).not.toContain('Flag — High');
  });

  it('reflects reviewed state in the toggle label', () => {
    const unreviewed = buildSingleTargetSections(
      makeTarget({ reviewed: false }),
      { torArmed: true },
      noopSingleHandlers(),
    );
    expect(labels(unreviewed)).toContain('Mark Reviewed');

    const reviewed = buildSingleTargetSections(
      makeTarget({ reviewed: true }),
      { torArmed: true },
      noopSingleHandlers(),
    );
    expect(labels(reviewed)).toContain('Mark Unreviewed');
  });

  it('routes each Flag priority row to handlers.flag with its priority', () => {
    const handlers = noopSingleHandlers();
    const flag = vi.fn();
    handlers.flag = flag;
    const sections = buildSingleTargetSections(
      makeTarget({ flag_status: null }),
      { torArmed: true },
      handlers,
    );
    void item(sections, 'Flag — High').onSelect();
    void item(sections, 'Flag — Medium').onSelect();
    void item(sections, 'Flag — Low').onSelect();
    expect(flag.mock.calls).toEqual([[1], [2], [3]]);
  });

  it('always offers "Add to Collection…" and routes it to the handler', () => {
    const handlers = noopSingleHandlers();
    const addToCollection = vi.fn();
    handlers.addToCollection = addToCollection;
    const sections = buildSingleTargetSections(
      makeTarget(),
      { torArmed: true, inCollection: false },
      handlers,
    );
    const add = item(sections, 'Add to Collection…');
    void add.onSelect();
    expect(addToCollection).toHaveBeenCalled();
  });

  it('appends "Remove from Collection" when inCollection and a handler are supplied', () => {
    const handlers = noopSingleHandlers();
    const removeFromCollection = vi.fn();
    handlers.removeFromCollection = removeFromCollection;
    const sections = buildSingleTargetSections(
      makeTarget(),
      { torArmed: true, inCollection: true },
      handlers,
    );
    const remove = item(sections, 'Remove from Collection');
    void remove.onSelect();
    expect(removeFromCollection).toHaveBeenCalled();
  });

  it('omits "Remove from Collection" outside collection context', () => {
    const handlers = noopSingleHandlers();
    handlers.removeFromCollection = vi.fn();
    const sections = buildSingleTargetSections(
      makeTarget(),
      { torArmed: true, inCollection: false },
      handlers,
    );
    expect(labels(sections)).not.toContain('Remove from Collection');
  });

  describe('capability filtering', () => {
    // The Search tab's intake set — an uncrawled result has no node, so the
    // graph- and content-bound verbs are withheld.
    const INTAKE: ReadonlySet<MenuCapability> = new Set([
      'copy',
      'openInTor',
      'crawl',
      'bookmark',
      'flag',
      'monitor',
      'analysis',
      'collection',
    ]);

    it('emits every item when no capability set is given (full menu)', () => {
      const sections = buildSingleTargetSections(
        makeTarget(),
        { torArmed: true },
        noopSingleHandlers(),
      );
      expect(labels(sections)).toEqual(
        expect.arrayContaining([
          'Rename alias…',
          'Focus',
          'Hide from Graph',
          'Mark Reviewed',
        ]),
      );
    });

    it('withholds graph- and content-bound verbs for an intake-only surface', () => {
      const sections = buildSingleTargetSections(
        makeTarget(),
        { torArmed: true, capabilities: INTAKE },
        noopSingleHandlers(),
      );
      const ls = labels(sections);
      expect(ls).not.toContain('Rename alias…');
      expect(ls).not.toContain('Mark Reviewed');
      expect(ls).not.toContain('Focus');
      expect(ls).not.toContain('Hide from Graph');
      // Intake verbs survive.
      expect(ls).toEqual(
        expect.arrayContaining([
          'Copy URL',
          'Open in Tor Browser',
          'Send to Crawl',
          'Flag — High',
          'Queue Analysis…',
          'Add to Collection…',
        ]),
      );
    });

    it('drops the Graph divider entirely when neither focus nor hide is offered', () => {
      const sections = buildSingleTargetSections(
        makeTarget(),
        { torArmed: true, capabilities: INTAKE },
        noopSingleHandlers(),
      );
      expect(sections.map((s) => s.label)).not.toContain('Graph');
    });

    it('keeps graph verbs when the set includes focus/hide (crawled result)', () => {
      const crawled = new Set<MenuCapability>([...INTAKE, 'rename', 'review', 'focus', 'hide']);
      const sections = buildSingleTargetSections(
        makeTarget(),
        { torArmed: true, capabilities: crawled },
        noopSingleHandlers(),
      );
      expect(labels(sections)).toEqual(
        expect.arrayContaining(['Focus', 'Hide from Graph', 'Rename alias…']),
      );
    });

    it('never shows "Add to Graph" in the default-all menu (graph/bottom pane)', () => {
      const handlers = noopSingleHandlers();
      handlers.addToGraph = vi.fn();
      const sections = buildSingleTargetSections(
        makeTarget(),
        { torArmed: true },
        handlers,
      );
      expect(labels(sections)).not.toContain('Add to Graph');
    });

    it('offers "Add to Graph" only when the capability and a handler are both present', () => {
      const handlers = noopSingleHandlers();
      const addToGraph = vi.fn();
      handlers.addToGraph = addToGraph;
      const sections = buildSingleTargetSections(
        makeTarget(),
        { torArmed: true, capabilities: new Set<MenuCapability>([...INTAKE, 'addToGraph']) },
        handlers,
      );
      const add = item(sections, 'Add to Graph');
      void add.onSelect();
      expect(addToGraph).toHaveBeenCalled();
    });

    it('withholds "Add to Graph" when the capability is set but no handler is supplied', () => {
      const sections = buildSingleTargetSections(
        makeTarget(),
        { torArmed: true, capabilities: new Set<MenuCapability>(['addToGraph']) },
        noopSingleHandlers(),
      );
      expect(labels(sections)).not.toContain('Add to Graph');
    });

    it('offers "Pin to Graph" for an unpinned uncrawled node with a togglePin handler', () => {
      const handlers = noopSingleHandlers();
      const togglePin = vi.fn();
      handlers.togglePin = togglePin;
      const sections = buildSingleTargetSections(
        makeTarget({ state: 'known', pinned: false }),
        { torArmed: true },
        handlers,
      );
      const pin = item(sections, 'Pin to Graph');
      void pin.onSelect();
      expect(togglePin).toHaveBeenCalled();
      expect(labels(sections)).not.toContain('Unpin from Graph');
    });

    it('shows "Unpin from Graph" for a pinned node', () => {
      const handlers = noopSingleHandlers();
      handlers.togglePin = vi.fn();
      const sections = buildSingleTargetSections(
        makeTarget({ state: 'known', pinned: true }),
        { torArmed: true },
        handlers,
      );
      expect(labels(sections)).toContain('Unpin from Graph');
      expect(labels(sections)).not.toContain('Pin to Graph');
    });

    it('never offers pin/unpin on a crawled node (always shown — pinning is moot)', () => {
      const handlers = noopSingleHandlers();
      handlers.togglePin = vi.fn();
      const sections = buildSingleTargetSections(
        makeTarget({ state: 'crawled' }),
        { torArmed: true },
        handlers,
      );
      expect(labels(sections)).not.toContain('Pin to Graph');
      expect(labels(sections)).not.toContain('Unpin from Graph');
    });

    it('omits pin/unpin when no togglePin handler is wired (e.g. search rows)', () => {
      const sections = buildSingleTargetSections(
        makeTarget({ state: 'known' }),
        { torArmed: true, capabilities: new Set<MenuCapability>([...INTAKE, 'addToGraph']) },
        noopSingleHandlers(),
      );
      expect(labels(sections)).not.toContain('Pin to Graph');
    });
  });
});

describe('buildMultiSelectSections', () => {
  it('returns null for a selection below 2 targets', () => {
    expect(buildMultiSelectSections([], noopMultiHandlers())).toBeNull();
    expect(
      buildMultiSelectSections([makeTarget()], noopMultiHandlers()),
    ).toBeNull();
  });

  it('puts the selection size in the count-bearing labels', () => {
    const targets = [makeTarget(), makeTarget(), makeTarget()];
    const sections = buildMultiSelectSections(targets, noopMultiHandlers())!;
    expect(labels(sections)).toContain('Add to Collection (3)');
    expect(labels(sections)).toContain('Flag All (3)');
  });

  it('offers "Open as graph tab" with the selection count, always enabled', () => {
    const targets = [makeTarget({ state: 'known' }), makeTarget({ state: 'known' })];
    const sections = buildMultiSelectSections(targets, noopMultiHandlers())!;
    const open = item(sections, 'Open as graph tab (2)');
    expect(open.disabled).toBeFalsy();
  });

  it('enables "Send to Crawl" with the full selection count on a mixed selection', () => {
    const targets = [
      makeTarget({ state: 'known' }),
      makeTarget({ state: 'known' }),
      makeTarget({ state: 'crawled' }),
    ];
    const sections = buildMultiSelectSections(targets, noopMultiHandlers())!;
    const send = item(sections, 'Send to Crawl (3)');
    expect(send.disabled).toBeFalsy();
    const review = item(sections, 'Mark Reviewed (1)');
    expect(review.disabled).toBe(false);
    expect(item(sections, 'Hide All (1)').disabled).toBe(false);
  });

  it('keeps "Send to Crawl" enabled when the selection has no stubs (re-crawl is allowed)', () => {
    const targets = [
      makeTarget({ state: 'crawled' }),
      makeTarget({ state: 'crawled' }),
    ];
    const sections = buildMultiSelectSections(targets, noopMultiHandlers())!;
    const send = item(sections, 'Send to Crawl (2)');
    expect(send.disabled).toBeFalsy();
  });

  it('disables crawled-only actions when the selection is all stubs', () => {
    const targets = [
      makeTarget({ state: 'known' }),
      makeTarget({ state: 'known' }),
    ];
    const sections = buildMultiSelectSections(targets, noopMultiHandlers())!;
    const review = item(sections, 'Mark Reviewed');
    expect(review.disabled).toBe(true);
    expect(review.disabledReason).toBe('Selection has no crawled nodes');
    const hide = item(sections, 'Hide All');
    expect(hide.disabled).toBe(true);
    expect(hide.disabledReason).toBe('Selection has no crawled nodes');
  });
});
