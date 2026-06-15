// Context-menu section builders.
//
// Pure: given a target (or set of targets), a small context object, and a
// set of action handlers, each builder returns the MenuSection[] the
// ContextMenu renderer consumes. No store reads, no Sigma, no async — so
// item-availability rules (disabled flags, disabled reasons, count-bearing
// labels) are unit-testable without mounting any surface.
//
// The builders are surface-neutral: graph nodes, bottom-pane rows, future
// right-pane rows, and search-result rows all feed the same `MenuTarget`
// shape in. Each surface owns its own *trigger* (right-click handler) and
// *positioning* (canvas vs DOM coords), then mounts the shared
// ContextMenu component with the sections this module produces.
//
// Action *implementations* (toasts, API calls, modal state) live in the
// caller and are passed in as target-bound handlers; this module owns only
// the menu's shape and gating policy.

import type { ResourceState } from '$lib/api';
import { isUncrawled } from '$lib/nodeState';

// `state`-bearing target → uncrawled? A target without a resolved node
// (`state` undefined, e.g. a bottom-pane no-node row) is treated as not
// uncrawled so URL-based actions stay enabled.
function targetUncrawled(target: { state?: ResourceState }): boolean {
  return target.state != null && isUncrawled({ state: target.state });
}

// Shared menu shape — consumed by the ContextMenu renderer for the
// single-target, multi-select, and analyst-edge variants. Sections render
// with a labelled divider above their items so the spec's "CRAWL /
// INVESTIGATION / ANALYSIS / GRAPH" grouping is preserved
// (explore-graph.md:117-166).
export interface MenuItem {
  label: string;
  onSelect: () => void | Promise<void>;
  disabled?: boolean;
  disabledReason?: string;
}

export interface MenuSection {
  label?: string;
  items: MenuItem[];
}

// The minimum set of fields a builder needs from a target. GraphNode is
// structurally compatible, so the graph adapter passes nodes directly with
// no conversion. Bottom-pane rows, right-pane rows, and search results
// build a MenuTarget from their own row data.
export interface MenuTarget {
  // Resource lifecycle state of the target's node, when it maps to one.
  // GraphNode is structurally compatible, so the graph adapter passes nodes
  // straight through; no-node rows leave it undefined.
  state?: ResourceState;
  flag_status?: string | number | null;
  reviewed?: boolean;
  domain?: string | null;
  // Whether this node is analyst-pinned (kept on the canvas regardless of the
  // show-uncrawled toggle). Drives the Pin/Unpin label; the graph adapter sets
  // it, other surfaces leave it undefined.
  pinned?: boolean;
}

// ---------------- Single-target menu ----------------

// Per-item capability tags. A surface declares the set it offers (see
// `SingleTargetMenuContext.capabilities`); the builder emits only items
// whose capability is in that set, then drops any section left empty.
// This is how surfaces opt out of verbs that don't apply to them — e.g.
// the Search tab hides the graph-only `focus`/`hide` on an uncrawled
// result row that has no node yet. Crawl-state gating (the `uncrawled`
// disabled flag on Hide) is orthogonal and still applies on top.
export type MenuCapability =
  | 'rename'
  | 'label'
  | 'copy'
  | 'openInTor'
  | 'crawl'
  | 'bookmark'
  | 'flag'
  | 'review'
  | 'monitor'
  | 'analysis'
  | 'collection'
  | 'addToGraph'
  | 'focus'
  | 'collapse'
  | 'hide';

export interface SingleTargetMenuContext {
  // Kill-switch armed — gates "Open in Tor Browser". The graph adapter
  // reads servicesStore.killSwitch.phase; the builder only sees the boolean.
  torArmed: boolean;
  // True when the menu is mounted from a collection-scoped surface (the
  // Collection sub-tab, or future cluster workspace). Surfaces an extra
  // "Remove from Collection" item.
  inCollection?: boolean;
  // Which menu capabilities this surface offers. Omit for the full menu
  // (the graph and bottom pane pass nothing → every item, unchanged).
  capabilities?: ReadonlySet<MenuCapability>;
  // True when the target's domain is currently folded on the active tab —
  // flips the Collapse item to Expand. The graph adapter reads
  // graphCollapseStore; other surfaces leave it undefined.
  domainCollapsed?: boolean;
}

// Target-bound action callbacks. The adapter builds this by closing each
// act*/open*Modal call over the right-clicked target.
export interface SingleTargetMenuHandlers {
  copyUrl: () => void | Promise<void>;
  openInTor: () => void | Promise<void>;
  queueCrawl: () => void | Promise<void>;
  saveSeedBookmark: () => void | Promise<void>;
  flag: (priority: number) => void | Promise<void>;
  removeFlag: () => void | Promise<void>;
  toggleReviewed: () => void | Promise<void>;
  addMonitor: () => void;
  renameAlias: () => void;
  applyLabels: () => void;
  queueAnalysis: () => void;
  addToCollection: () => void;
  focus: () => void;
  // Fold / unfold this target's whole domain into one summary node on the
  // active tab (Phase 3d, D7). A *summarize*, distinct from Hide. Graph surface
  // only — other surfaces omit the handler.
  toggleCollapseDomain?: () => void | Promise<void>;
  hideFromGraph: () => void | Promise<void>;
  removeFromCollection?: () => void | Promise<void>;
  // Materialize a not-yet-a-node target (an uncrawled Search result) as an
  // uncrawled graph node, without crawling/flagging/collecting it. Opt-in
  // only (see `addToGraph` capability) — surfaces whose rows are already
  // nodes (graph, bottom pane) never offer it, so the handler is optional.
  addToGraph?: () => void | Promise<void>;
  // Toggle this node's pin (graph surface only). The removal path for an
  // uncrawled pin, since Hide from Graph is crawled-only. Optional — surfaces
  // that don't carry a node id (search rows mint via addToGraph) omit it.
  togglePin?: () => void | Promise<void>;
}

// Sections for the single-target menu. Item labels follow
// explore-graph.md:117-136 — stateful items (Flag / Reviewed) carry their
// current state in the label. Hide from Graph still gates on crawl state
// (crawled-only); Send to Crawl is available on any target under Phase B's
// single-verb intake model so an analyst can re-crawl a known target.
export function buildSingleTargetSections(
  target: MenuTarget,
  ctx: SingleTargetMenuContext,
  handlers: SingleTargetMenuHandlers,
): MenuSection[] {
  const caps = ctx.capabilities;
  // No declared set → the full menu (graph / bottom pane). A surface that
  // declares its set gets only the verbs it opted into.
  const has = (c: MenuCapability): boolean => !caps || caps.has(c);
  const uncrawled = targetUncrawled(target);
  const isFlagged = !!target.flag_status;
  const isReviewed = !!target.reviewed;

  // Rename alias leads the menu — it's the most-reached single-target
  // action, so it sits as the top item above Copy URL / Open in Tor.
  const topItems: MenuItem[] = [];
  if (has('rename')) {
    topItems.push({
      label: 'Rename alias…',
      onSelect: handlers.renameAlias,
      disabled: !target.domain,
      disabledReason: 'No domain',
    });
  }
  if (has('label')) {
    // Categorize — apply/remove labels (item 11). High-frequency organising
    // action, so it sits in the top section beside rename.
    topItems.push({ label: 'Labels…', onSelect: handlers.applyLabels });
  }
  if (has('copy')) {
    topItems.push({ label: 'Copy URL', onSelect: handlers.copyUrl });
  }
  if (has('openInTor')) {
    topItems.push({
      label: 'Open in Tor Browser',
      onSelect: handlers.openInTor,
      disabled: !ctx.torArmed,
      disabledReason: 'Tor not connected',
    });
  }

  const crawlItems: MenuItem[] = [];
  if (has('crawl')) {
    crawlItems.push({ label: 'Send to Crawl', onSelect: handlers.queueCrawl });
  }
  if (has('bookmark')) {
    crawlItems.push({
      label: 'Save as Seed Bookmark',
      onSelect: handlers.saveSeedBookmark,
    });
  }

  const investigationItems: MenuItem[] = [];
  if (has('flag')) {
    // Unflagged → pick a priority; flagged → single Remove row. Full
    // lifecycle moves (investigating/done/dismissed) live in the F6 right
    // panel, which has the flag id the graph payload doesn't carry.
    investigationItems.push(
      ...(isFlagged
        ? [{ label: 'Remove Flag', onSelect: handlers.removeFlag }]
        : [
            { label: 'Flag — High', onSelect: () => handlers.flag(1) },
            { label: 'Flag — Medium', onSelect: () => handlers.flag(2) },
            { label: 'Flag — Low', onSelect: () => handlers.flag(3) },
          ]),
    );
  }
  if (has('review')) {
    investigationItems.push({
      label: isReviewed ? 'Mark Unreviewed' : 'Mark Reviewed',
      onSelect: handlers.toggleReviewed,
    });
  }
  if (has('monitor')) {
    investigationItems.push({ label: 'Add Monitor…', onSelect: handlers.addMonitor });
  }

  const analysisItems: MenuItem[] = [];
  if (has('analysis')) {
    analysisItems.push({ label: 'Queue Analysis…', onSelect: handlers.queueAnalysis });
  }

  // Add to Collection is always available; Remove from Collection only
  // when the menu opens from a collection-scoped surface (and the surface
  // supplied the remove handler).
  const collectionItems: MenuItem[] = [];
  if (has('collection')) {
    collectionItems.push({
      label: 'Add to Collection…',
      onSelect: handlers.addToCollection,
    });
    if (ctx.inCollection && handlers.removeFromCollection) {
      collectionItems.push({
        label: 'Remove from Collection',
        onSelect: handlers.removeFromCollection,
      });
    }
  }

  const graphItems: MenuItem[] = [];
  // Opt-in only: `addToGraph` is never part of the default-all menu (graph
  // and bottom-pane rows are already nodes). Shown only when a surface
  // explicitly lists the capability AND supplies a handler.
  if (caps?.has('addToGraph') && handlers.addToGraph) {
    graphItems.push({ label: 'Add to Graph', onSelect: handlers.addToGraph });
  }
  if (has('focus')) {
    graphItems.push({ label: 'Focus', onSelect: handlers.focus });
  }
  // Collapse / Expand this domain — fold every page of the site into one
  // summary node (a summarize, not a hide). Domain-bound, so disabled on a
  // target with no domain.
  if (has('collapse') && handlers.toggleCollapseDomain) {
    graphItems.push({
      label: ctx.domainCollapsed ? 'Expand domain' : 'Collapse domain',
      onSelect: handlers.toggleCollapseDomain,
      disabled: !target.domain,
      disabledReason: 'No domain',
    });
  }
  if (has('hide')) {
    graphItems.push({
      label: 'Hide from Graph',
      onSelect: handlers.hideFromGraph,
      disabled: uncrawled,
      disabledReason: 'Crawled nodes only',
    });
  }
  // Pin / Unpin — the keep-on-canvas control for uncrawled placeholders, and
  // the only removal path for one (Hide from Graph above is crawled-only).
  // Crawled nodes are always shown, so pinning them is meaningless — hence
  // uncrawled-only. Shown wherever the surface wires a togglePin handler.
  if (uncrawled && handlers.togglePin) {
    graphItems.push({
      label: target.pinned ? 'Unpin from Graph' : 'Pin to Graph',
      onSelect: handlers.togglePin,
    });
  }

  const sections: MenuSection[] = [
    { items: topItems },
    { label: 'Crawl', items: crawlItems },
    { label: 'Investigation', items: investigationItems },
    { label: 'Analysis', items: analysisItems },
    { label: 'Collection', items: collectionItems },
    { label: 'Graph', items: graphItems },
  ];
  // Drop any section a surface emptied out via its capability set, so no
  // labelled divider renders above zero items.
  return sections.filter((s) => s.items.length > 0);
}

// ---------------- Multi-select menu ----------------

// Selection-bound action callbacks. The adapter builds this by closing
// each act*/open*Modal call over the selected target set.
export interface MultiSelectMenuHandlers {
  addToCollection: () => void;
  drawEdge: () => void;
  crawlSelected: () => void | Promise<void>;
  flagAll: () => void | Promise<void>;
  markReviewedAll: () => void | Promise<void>;
  queueAnalysis: () => void;
  hideAll: () => void | Promise<void>;
  // Open the selection as its own graph tab (NodeSet Workspaces, item 4).
  openAsTab: () => void;
}

// Sections for the multi-select menu. Items follow explore-graph.md:
// 152-166 — items that don't apply to the current selection are disabled
// with a short reason rather than hidden, and counts in the labels match
// the selection. Returns null for a selection below 2 targets (the
// multi-select menu has no meaning there).
export function buildMultiSelectSections(
  targets: MenuTarget[],
  handlers: MultiSelectMenuHandlers,
): MenuSection[] | null {
  if (targets.length < 2) return null;
  const uncrawledCount = targets.reduce(
    (n, x) => n + (targetUncrawled(x) ? 1 : 0),
    0,
  );
  const crawledCount = targets.length - uncrawledCount;
  const hasCrawled = crawledCount > 0;
  return [
    {
      items: [
        {
          label: `Add to Collection (${targets.length})`,
          onSelect: handlers.addToCollection,
        },
        { label: 'Draw Edge…', onSelect: handlers.drawEdge },
      ],
    },
    {
      label: 'Crawl',
      items: [
        {
          label: `Send to Crawl (${targets.length})`,
          onSelect: handlers.crawlSelected,
        },
      ],
    },
    {
      label: 'Investigation',
      items: [
        { label: `Flag All (${targets.length})`, onSelect: handlers.flagAll },
        {
          label: `Mark Reviewed${hasCrawled ? ` (${crawledCount})` : ''}`,
          onSelect: handlers.markReviewedAll,
          disabled: !hasCrawled,
          disabledReason: 'Selection has no crawled nodes',
        },
      ],
    },
    {
      label: 'Analysis',
      items: [{ label: 'Queue Analysis…', onSelect: handlers.queueAnalysis }],
    },
    {
      label: 'Graph',
      items: [
        {
          label: `Open as graph tab (${targets.length})`,
          onSelect: handlers.openAsTab,
        },
        {
          label: `Hide All${hasCrawled ? ` (${crawledCount})` : ''}`,
          onSelect: handlers.hideAll,
          disabled: !hasCrawled,
          disabledReason: 'Selection has no crawled nodes',
        },
      ],
    },
  ];
}
